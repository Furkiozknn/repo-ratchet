"""Turning surveys, queue and records into something a person reads.

Two audiences: a person skimming the repository, and the ecosystem's own
metadata pipeline. Both get the same numbers from the same objects, so a
report cannot drift from the records it describes.
"""

from __future__ import annotations

import json

from .plan import Entry
from .records import Record
from .survey import Survey


def queue_text(round_n: int, queue: list[Entry], finished: list[Entry]) -> str:
    """The queue as a terminal reads it."""
    lines = ["round %d - %d waiting, %d already recorded" % (round_n, len(queue), len(finished)), ""]
    if not queue:
        lines.append("  nothing waiting: every surveyed repository has a record in this round.")
    for i, e in enumerate(queue, 1):
        flag = "  (unchanged since its last record)" if e.unchanged_since_last_record else ""
        lines.append("%2d. %-28s headroom %5.2f%s" % (i, e.repo, e.headroom, flag))
        lines.append("    %s" % e.reason)
        for c in e.candidates[:3]:
            lines.append("      - %s" % c)
        lines.append("")
    if finished:
        lines.append("recorded this round: " + ", ".join(e.repo for e in finished))
    return "\n".join(lines) + "\n"


def survey_text(s: Survey) -> str:
    """One repository's measurements, in full."""
    lines = ["%s @ %s" % (s.repo, (s.head or "no git")[:12]), "taken %s" % s.taken_at, ""]
    for name, d in sorted(s.signals.items()):
        value = d.get("value")
        shown = "-" if value is None else (
            json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else str(value)
        )
        unit = (" " + d["unit"]) if d.get("unit") else ""
        lines.append("  %-24s %s%s" % (name, shown, unit))
        if d.get("detail"):
            lines.append("      %s" % d["detail"])
    lines.append("")
    lines.append("  total headroom %.2f across %d signals" % (s.total_headroom, len(s.opportunities)))
    for o in s.opportunities:
        lines.append("    %-24s %.2f  %s" % (o.signal, o.headroom, o.note))
    return "\n".join(lines) + "\n"


def records_markdown(records: list[Record]) -> str:
    """The work log, as the repository's own README-facing table."""
    if not records:
        return "_No rounds recorded yet._\n"
    rounds: dict[int, list[Record]] = {}
    for r in records:
        rounds.setdefault(r.round, []).append(r)

    out: list[str] = []
    for n in sorted(rounds):
        rs = sorted(rounds[n], key=lambda r: r.at)
        advanced = [r for r in rs if r.outcome == "advanced"]
        checks = sum(len(r.verifications) for r in rs)
        passed = sum(1 for r in rs for v in r.verifications if v.passed)
        out.append("### Round %d" % n)
        out.append("")
        out.append("%d repositories, %d advanced, %d checks run of which %d passed."
                   % (len(rs), len(advanced), checks, passed))
        out.append("")
        out.append("| Repository | Outcome | What changed / why not | Verified by |")
        out.append("| --- | --- | --- | --- |")
        for r in rs:
            what = r.summary if r.outcome == "advanced" else r.reason
            checks_cell = "<br>".join(
                "`%s` → %d" % (v.command, v.exit_code) for v in r.verifications
            ) or "—"
            out.append("| [%s](https://github.com/Furkiozknn/%s) | %s | %s | %s |"
                       % (r.repo, r.repo, r.outcome, what.replace("|", "\\|"), checks_cell))
        out.append("")
    return "\n".join(out) + "\n"


def records_json(records: list[Record]) -> str:
    """The work log as data, for the hub and for the next round."""
    by_round: dict[str, dict] = {}
    for r in records:
        b = by_round.setdefault(str(r.round), {
            "round": r.round, "repositories": 0, "advanced": 0,
            "no_change": 0, "blocked": 0, "checks_run": 0, "checks_passed": 0,
        })
        b["repositories"] += 1
        b[{"advanced": "advanced", "no-change": "no_change", "blocked": "blocked"}[r.outcome]] += 1
        b["checks_run"] += len(r.verifications)
        b["checks_passed"] += sum(1 for v in r.verifications if v.passed)
    return json.dumps({
        "schema": 1,
        "rounds": [by_round[k] for k in sorted(by_round, key=int)],
        "records": [r.as_dict() for r in records],
    }, indent=1, ensure_ascii=False) + "\n"
