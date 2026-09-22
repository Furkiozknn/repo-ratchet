"""Turn a checkout into a survey: every measurement, plus where the room is.

A survey is deliberately not a score. Two repositories with the same total
headroom can need completely different work, and the ranking exists only to
decide which repository to open next - never what to do once it is open.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import signals as sig
from .signals import Signal

SCHEMA = 1


@dataclass
class Opportunity:
    """One place the measurements say there is room, with the evidence."""

    signal: str
    headroom: float
    note: str
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "signal": self.signal,
            "headroom": round(self.headroom, 3),
            "note": self.note,
            "evidence": self.evidence,
        }


@dataclass
class Survey:
    """Everything measured about one repository at one commit."""

    repo: str
    head: str | None
    taken_at: str
    signals: dict[str, dict]
    opportunities: list[Opportunity]
    schema: int = SCHEMA

    @property
    def total_headroom(self) -> float:
        return round(sum(o.headroom for o in self.opportunities), 3)

    def as_dict(self) -> dict:
        return {
            "schema": self.schema,
            "repo": self.repo,
            "head": self.head,
            "taken_at": self.taken_at,
            "total_headroom": self.total_headroom,
            "signals": self.signals,
            "opportunities": [o.as_dict() for o in self.opportunities],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Survey":
        return cls(
            repo=d["repo"],
            head=d.get("head"),
            taken_at=d.get("taken_at", ""),
            signals=d.get("signals", {}),
            opportunities=[
                Opportunity(o["signal"], o["headroom"], o.get("note", ""), o.get("evidence", []))
                for o in d.get("opportunities", [])
            ],
            schema=d.get("schema", SCHEMA),
        )


def head_commit(root: Path) -> str | None:
    """The commit the survey describes, so a record can be pinned to it."""
    if not (root / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def take(root: Path, repo: str | None = None) -> Survey:
    """Measure a checkout. Never executes anything inside it."""
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    name = repo or root.name
    collected: dict[str, dict] = {}
    opportunities: list[Opportunity] = []
    for fn in sig.ALL:
        try:
            s: Signal = fn(root)
        except Exception as ex:  # a broken measurement must not lose the rest
            s = Signal(fn.__name__, None, detail="measurement failed: %r" % ex)
        collected[s.name] = s.as_dict()
        if s.headroom:
            opportunities.append(Opportunity(s.name, s.headroom, s.detail, s.evidence[:6]))
    opportunities.sort(key=lambda o: -o.headroom)
    return Survey(
        repo=name,
        head=head_commit(root),
        taken_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        signals=collected,
        opportunities=opportunities,
    )


def load_all(path: Path) -> list[Survey]:
    """Read a surveys file written by :func:`save_all`."""
    path = Path(path)
    if not path.is_file():
        return []
    d = json.loads(path.read_text(encoding="utf-8"))
    return [Survey.from_dict(x) for x in d.get("surveys", [])]


def save_all(path: Path, surveys: list[Survey]) -> None:
    """Write surveys as one document, newest measurement wins per repository."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "schema": SCHEMA,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "surveys": [s.as_dict() for s in sorted(surveys, key=lambda s: s.repo)],
    }
    path.write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
