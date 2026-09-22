"""The work records: what was done, at which commit, and how it was checked.

This module is the reason the engine can run for more than one round. A round
that leaves no record is a round that will be repeated, and a record that
claims work nobody verified is worse than no record at all - so the rules are
enforced here, in code, not in a convention:

* ``advanced`` requires the commit to have actually moved **and** at least one
  verification that ran and exited zero.
* ``no-change`` requires a stated reason. "Nothing to do" is a finding, and a
  finding has to say what was looked at.
* a verification is a command someone ran, with its exit code. There is no way
  to write one without an exit code, so a verification that did not happen
  cannot be recorded as if it had.

Records are append-only JSON Lines, one file per round, so a diff shows a
round's work and nothing rewrites history.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

SCHEMA = 1

ADVANCED = "advanced"
NO_CHANGE = "no-change"
BLOCKED = "blocked"
OUTCOMES = (ADVANCED, NO_CHANGE, BLOCKED)


class RecordError(ValueError):
    """A record was asked to claim something it cannot back up."""


@dataclass
class Verification:
    """A command that was actually run, and what it returned.

    `expect` exists because round 1 ran 98 checks and 20 of them were
    *supposed* to fail. A gate is not a gate until you have watched it close:
    every one of those twenty is a negative control - the old action.yml on
    the fixture it used to break on, the audit against a server that really
    does exfiltrate a key, the vendor script with its deletion put back. With
    only an exit code to go on, the log could not tell those apart from a
    check that simply failed, and the report was reduced to saying how many
    exited zero.

    So a check declares what it was run to prove. `expect=0` is the ordinary
    case and stays the default; `expect=1` says "this had to fail, and it
    did". Rule 2 is unchanged in substance: an `advanced` record still needs
    at least one check that was required to succeed and did - a record made
    entirely of negative controls proves the gates bite, not that the change
    works.
    """

    command: str
    exit_code: int
    duration_s: float = 0.0
    note: str = ""
    output_tail: str = ""
    #: The exit code this check was run to see. 0 unless it is a negative
    #: control, in which case it is the non-zero code that means "the gate
    #: closed".
    expect: int = 0

    @property
    def passed(self) -> bool:
        """Did the check return what it was run to return?"""
        return self.exit_code == self.expect

    @property
    def negative_control(self) -> bool:
        return self.expect != 0

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Record:
    """One repository, one round, one outcome."""

    round: int
    repo: str
    outcome: str
    head_before: str | None = None
    head_after: str | None = None
    summary: str = ""
    reason: str = ""
    verifications: list[Verification] = field(default_factory=list)
    headroom_before: float | None = None
    headroom_after: float | None = None
    at: str = ""
    schema: int = SCHEMA

    def __post_init__(self) -> None:
        if not self.at:
            self.at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.validate()

    def validate(self) -> None:
        """Refuse a record that claims more than it can show."""
        if self.outcome not in OUTCOMES:
            raise RecordError("outcome must be one of %s, got %r" % (OUTCOMES, self.outcome))
        if not self.repo:
            raise RecordError("a record needs a repository name")
        if self.round < 1:
            raise RecordError("rounds start at 1")
        if self.outcome == ADVANCED:
            if not self.summary.strip():
                raise RecordError("an advanced record has to say what changed")
            if not self.head_before or not self.head_after:
                raise RecordError("an advanced record needs the commit before and after")
            if self.head_before == self.head_after:
                raise RecordError(
                    "%s: outcome is 'advanced' but the commit did not move (%s)"
                    % (self.repo, self.head_before[:12])
                )
            if not any(v.passed and not v.negative_control for v in self.verifications):
                raise RecordError(
                    "%s: outcome is 'advanced' but no verification that had to "
                    "succeed ran and succeeded" % self.repo
                )
        if self.outcome in (NO_CHANGE, BLOCKED) and not self.reason.strip():
            raise RecordError("a %r record has to say why" % self.outcome)

    @property
    def verified(self) -> bool:
        return any(v.passed for v in self.verifications)

    def as_dict(self) -> dict:
        d = asdict(self)
        d["verifications"] = [v.as_dict() for v in self.verifications]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Record":
        return cls(
            round=d["round"],
            repo=d["repo"],
            outcome=d["outcome"],
            head_before=d.get("head_before"),
            head_after=d.get("head_after"),
            summary=d.get("summary", ""),
            reason=d.get("reason", ""),
            verifications=[Verification(**v) for v in d.get("verifications", [])],
            headroom_before=d.get("headroom_before"),
            headroom_after=d.get("headroom_after"),
            at=d.get("at", ""),
            schema=d.get("schema", SCHEMA),
        )


class Ledger:
    """Every record ever written, one JSON Lines file per round."""

    def __init__(self, root: Path):
        self.root = Path(root)

    def path_for(self, round_n: int) -> Path:
        return self.root / ("tur-%02d.jsonl" % round_n)

    def append(self, record: Record) -> Path:
        """Add a record. Validation already ran in the constructor."""
        record.validate()
        p = self.path_for(record.round)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return p

    def read(self, round_n: int | None = None) -> list[Record]:
        """Records for one round, or every record if no round is given."""
        out: list[Record] = []
        if not self.root.is_dir():
            return out
        files = (
            [self.path_for(round_n)] if round_n is not None
            else sorted(self.root.glob("tur-*.jsonl"))
        )
        for p in files:
            if not p.is_file():
                continue
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                out.append(Record.from_dict(json.loads(line)))
        return out

    def rounds(self) -> list[int]:
        """Which rounds have any records at all."""
        if not self.root.is_dir():
            return []
        found = []
        for p in sorted(self.root.glob("tur-*.jsonl")):
            try:
                found.append(int(p.stem.split("-")[1]))
            except (IndexError, ValueError):
                continue
        return sorted(set(found))

    def current_round(self) -> int:
        """The round in progress: the highest one with records, or 1."""
        rs = self.rounds()
        return rs[-1] if rs else 1

    def done_in_round(self, round_n: int) -> set[str]:
        """Repositories already dealt with in this round, whatever the outcome."""
        return {r.repo for r in self.read(round_n)}

    def last_for(self, repo: str) -> Record | None:
        """The most recent record for a repository, across every round."""
        best: Record | None = None
        for r in self.read():
            if r.repo != repo:
                continue
            if best is None or (r.round, r.at) >= (best.round, best.at):
                best = r
        return best
