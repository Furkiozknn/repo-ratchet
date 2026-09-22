"""Deciding which repository to open next - and nothing beyond that.

The queue answers one question: of the repositories that have not had this
round yet, which one has the most measured room? It does not answer what to
do once the repository is open, and it is written so that it cannot: an entry
carries the evidence and the word "candidates", never a task list.

The rule that keeps rounds from repeating themselves lives here too. A
repository is finished for a round once it has a record in that round, and a
repository whose commit has not moved since its last record is deprioritised
rather than re-examined, because nothing about it has changed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .records import Ledger, Record
from .survey import Survey


@dataclass
class Entry:
    """One repository's place in the queue, with the reason it is there."""

    repo: str
    headroom: float
    reason: str
    candidates: list[str] = field(default_factory=list)
    last_round: int | None = None
    head: str | None = None
    unchanged_since_last_record: bool = False

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "headroom": round(self.headroom, 3),
            "reason": self.reason,
            "candidates": self.candidates,
            "last_round": self.last_round,
            "head": self.head,
            "unchanged_since_last_record": self.unchanged_since_last_record,
        }


def build(
    surveys: list[Survey],
    ledger: Ledger,
    round_n: int | None = None,
    skipped: dict[str, str] | None = None,
) -> tuple[int, list[Entry], list[Entry]]:
    """Return ``(round, queue, finished)`` for the round now in progress.

    ``queue`` is ordered by measured headroom, highest first, with any
    repository whose commit has not moved since its last record pushed to the
    back: it has already had a round at exactly this code.
    """
    round_n = round_n or ledger.current_round()
    done = ledger.done_in_round(round_n)
    skipped = skipped or {}

    queue: list[Entry] = []
    finished: list[Entry] = []
    for s in surveys:
        if s.repo in skipped:
            continue
        last: Record | None = ledger.last_for(s.repo)
        unchanged = bool(last and last.head_after and s.head and last.head_after == s.head)
        entry = Entry(
            repo=s.repo,
            headroom=s.total_headroom,
            reason=_reason(s, last, unchanged),
            candidates=["%s (%.2f) - %s" % (o.signal, o.headroom, o.note) for o in s.opportunities[:5]],
            last_round=last.round if last else None,
            head=s.head,
            unchanged_since_last_record=unchanged,
        )
        (finished if s.repo in done else queue).append(entry)

    queue.sort(key=lambda e: (e.unchanged_since_last_record, -e.headroom, e.repo))
    finished.sort(key=lambda e: e.repo)
    return round_n, queue, finished


def _reason(s: Survey, last: Record | None, unchanged: bool) -> str:
    if not s.opportunities:
        return "no measurement shows room; open it to confirm, not to change it"
    top = s.opportunities[0]
    base = "%s is where the measurements say there is most room (%s)" % (top.signal, top.note)
    if unchanged and last:
        return base + "; unchanged since round %d, so look before touching" % last.round
    return base


def advance_round(ledger: Ledger, surveys: list[Survey]) -> tuple[bool, str]:
    """Is the current round finished, and may the next one start?

    A round is finished when every surveyed repository has a record in it.
    The engine refuses to open a new round early, because the point of a round
    is that it covers everything once before anything is revisited.
    """
    current = ledger.current_round()
    done = ledger.done_in_round(current)
    outstanding = sorted({s.repo for s in surveys} - done)
    if outstanding:
        return False, "round %d still has %d repositories outstanding: %s" % (
            current, len(outstanding), ", ".join(outstanding[:8]) + ("..." if len(outstanding) > 8 else "")
        )
    return True, "round %d covered all %d repositories; round %d may begin" % (
        current, len(done), current + 1
    )
