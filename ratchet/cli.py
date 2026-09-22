"""The command line: discover, survey, queue, check, record, report.

Each verb does one thing and leaves a file behind, so a round can be picked up
where it was left - including by a different process on a different day.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__, plan, render, targets, verify
from .records import Ledger, Record
from .survey import Survey, load_all, save_all, take

DEFAULT_STATE = Path(os.environ.get("RATCHET_STATE", "durum"))
DEFAULT_RECORDS = Path(os.environ.get("RATCHET_RECORDS", "kayitlar"))


def _surveys_path(state: Path) -> Path:
    return state / "olcumler.json"


def _targets_path(state: Path) -> Path:
    return state / "depolar.json"


# --------------------------------------------------------------------------


def cmd_discover(args: argparse.Namespace) -> int:
    """Ask GitHub which repositories exist and write the list, skip reasons and all."""
    tg = targets.discover(args.owner)
    state = Path(args.state)
    state.mkdir(parents=True, exist_ok=True)
    body = {
        "owner": args.owner,
        "targets": [
            {
                "name": t.name, "default_branch": t.default_branch,
                "clone_url": t.clone_url, "archived": t.archived,
                "size_kb": t.size_kb, "description": t.description,
                "skip_reason": t.skip_reason,
            }
            for t in tg
        ],
    }
    _targets_path(state).write_text(json.dumps(body, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    in_range = [t for t in tg if t.in_range]
    print("%d repositories on %s, %d in range" % (len(tg), args.owner, len(in_range)))
    for t in tg:
        if not t.in_range:
            print("  skipped %-26s %s" % (t.name, t.skip_reason))
    return 0


def _clone(t: targets.Target, into: Path, depth: int) -> Path | None:
    """Make a fresh checkout. A clone that fails is reported, not raised."""
    dest = into / t.name
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    cmd = ["git", "clone", "--quiet", "--branch", t.default_branch]
    if depth:
        cmd += ["--depth", str(depth)]
    cmd += [t.clone_url, str(dest)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        print("  could not clone %s: %s" % (t.name, (r.stderr or "").strip()[:160]), file=sys.stderr)
        return None
    return dest


def cmd_survey(args: argparse.Namespace) -> int:
    """Measure every repository in range, or one checkout already on disk."""
    state = Path(args.state)
    if args.path:
        s = take(Path(args.path), repo=args.repo)
        print(render.survey_text(s), end="")
        if args.save:
            existing = {x.repo: x for x in load_all(_surveys_path(state))}
            existing[s.repo] = s
            save_all(_surveys_path(state), list(existing.values()))
        return 0

    tp = _targets_path(state)
    if not tp.is_file():
        print("no %s - run `ratchet discover` first" % tp, file=sys.stderr)
        return 2
    tg = [t for t in targets.load_offline(str(tp)) if t.in_range]
    if args.only:
        wanted = {x.strip() for x in args.only.split(",")}
        tg = [t for t in tg if t.name in wanted]
    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    out: dict[str, Survey] = {x.repo: x for x in load_all(_surveys_path(state))}
    for t in tg:
        dest = work / t.name
        if not dest.is_dir() or args.refresh:
            dest = _clone(t, work, args.depth) or dest
        if not dest.is_dir():
            continue
        s = take(dest, repo=t.name)
        out[t.name] = s
        print("%-28s headroom %5.2f  %s" % (
            t.name, s.total_headroom,
            ", ".join(o.signal for o in s.opportunities[:3]) or "nothing measured as open"))
    save_all(_surveys_path(state), list(out.values()))
    print("\n%d surveys in %s" % (len(out), _surveys_path(state)))
    return 0


def cmd_queue(args: argparse.Namespace) -> int:
    """Print which repository to open next, the evidence, and whether the round can close."""
    state = Path(args.state)
    surveys = load_all(_surveys_path(state))
    if not surveys:
        print("no surveys yet - run `ratchet survey`", file=sys.stderr)
        return 2
    skipped = {}
    tp = _targets_path(state)
    if tp.is_file():
        skipped = {t.name: t.skip_reason for t in targets.load_offline(str(tp)) if t.skip_reason}
    ledger = Ledger(Path(args.records))
    round_n, queue, finished = plan.build(surveys, ledger, args.round, skipped)
    if args.json:
        print(json.dumps({
            "round": round_n,
            "queue": [e.as_dict() for e in queue],
            "finished": [e.as_dict() for e in finished],
        }, indent=1, ensure_ascii=False))
        return 0
    if args.next:
        if not queue:
            print("")
            return 1
        print(queue[0].repo)
        return 0
    print(render.queue_text(round_n, queue, finished), end="")
    ok, msg = plan.advance_round(ledger, surveys)
    print(("\n" + msg) if not ok else "\n%s" % msg)
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    """Run a repository's own checks inside the fence and keep the exit codes."""
    root = Path(args.path)
    cmds = [args.command] if args.command else verify.suggest(root)
    if not cmds:
        print("nothing to run: no ratchet.toml and no recognised manifest in %s" % root, file=sys.stderr)
        return 2
    failed = 0
    results = []
    for c in cmds:
        try:
            v = verify.run(c, root, timeout=args.timeout, note=args.note)
        except verify.VerifyError as ex:
            print("refused: %s" % ex, file=sys.stderr)
            return 2
        results.append(v)
        print("%-40s exit %d in %.1fs" % (c, v.exit_code, v.duration_s))
        if not v.passed:
            failed += 1
            print(v.output_tail)
    if args.out:
        Path(args.out).write_text(
            json.dumps([v.as_dict() for v in results], indent=1, ensure_ascii=False) + "\n",
            encoding="utf-8")
    return 1 if failed else 0


def cmd_record(args: argparse.Namespace) -> int:
    """Write down what this round did, or refuse if the claim is not backed."""
    verifications = []
    if args.verifications:
        raw = json.loads(Path(args.verifications).read_text(encoding="utf-8"))
        from .records import Verification
        verifications = [Verification(**v) for v in raw]
    try:
        rec = Record(
            round=args.round,
            repo=args.repo,
            outcome=args.outcome,
            head_before=args.before,
            head_after=args.after,
            summary=args.summary or "",
            reason=args.reason or "",
            verifications=verifications,
            headroom_before=args.headroom_before,
            headroom_after=args.headroom_after,
        )
    except ValueError as ex:
        print("refused: %s" % ex, file=sys.stderr)
        return 2
    p = Ledger(Path(args.records)).append(rec)
    print("recorded %s/%s in %s" % (rec.repo, rec.outcome, p))
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    """Render every record as the work log, in markdown or as data."""
    ledger = Ledger(Path(args.records))
    records = ledger.read()
    if args.json:
        text = render.records_json(records)
    else:
        text = render.records_markdown(records)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, encoding="utf-8")
        print("wrote %s (%d records)" % (args.out, len(records)))
    else:
        print(text, end="")
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The whole command line, in one place."""
    p = argparse.ArgumentParser(
        prog="ratchet",
        description="Keep raising what each repository can do, one round at a time.",
    )
    p.add_argument("-V", "--version", action="version", version="repo-ratchet %s" % __version__)
    p.add_argument("--state", default=str(DEFAULT_STATE), help="where surveys and the repository list live")
    p.add_argument("--records", default=str(DEFAULT_RECORDS), help="where the work records live")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="ask GitHub which repositories exist")
    d.add_argument("owner")
    d.set_defaults(fn=cmd_discover)

    s = sub.add_parser("survey", help="measure what each repository currently is")
    s.add_argument("--path", help="survey one checkout on disk instead of cloning")
    s.add_argument("--repo", help="name to record for --path")
    s.add_argument("--only", help="comma separated repository names")
    s.add_argument("--workdir", default=".ratchet-work", help="where clones go")
    s.add_argument("--depth", type=int, default=0, help="git clone depth, 0 for full (needed for release_lag)")
    s.add_argument("--refresh", action="store_true", help="re-clone even if the checkout is there")
    s.add_argument("--save", action="store_true", help="with --path, add the result to the survey file")
    s.set_defaults(fn=cmd_survey)

    q = sub.add_parser("queue", help="which repository to open next, and why")
    q.add_argument("--round", type=int)
    q.add_argument("--json", action="store_true")
    q.add_argument("--next", action="store_true", help="print only the next repository name")
    q.set_defaults(fn=cmd_queue)

    c = sub.add_parser("check", help="run a repository's own checks, inside the fence")
    c.add_argument("path")
    c.add_argument("--command", help="run this instead of the repository's usual check")
    c.add_argument("--timeout", type=int, default=verify.DEFAULT_TIMEOUT)
    c.add_argument("--note", default="")
    c.add_argument("--out", help="write the verifications as JSON, ready for `ratchet record`")
    c.set_defaults(fn=cmd_check)

    r = sub.add_parser("record", help="write what this round did to a repository")
    r.add_argument("repo")
    r.add_argument("--round", type=int, required=True)
    r.add_argument("--outcome", required=True, choices=("advanced", "no-change", "blocked"))
    r.add_argument("--before", help="commit before the round")
    r.add_argument("--after", help="commit after the round")
    r.add_argument("--summary", help="what changed (required for advanced)")
    r.add_argument("--reason", help="why nothing changed (required for no-change/blocked)")
    r.add_argument("--verifications", help="JSON file from `ratchet check --out`")
    r.add_argument("--headroom-before", type=float, dest="headroom_before")
    r.add_argument("--headroom-after", type=float, dest="headroom_after")
    r.set_defaults(fn=cmd_record)

    rep = sub.add_parser("report", help="render the work log")
    rep.add_argument("--json", action="store_true")
    rep.add_argument("--out")
    rep.set_defaults(fn=cmd_report)

    return p


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code rather than raising at the user."""
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (RuntimeError, OSError) as ex:
        print("ratchet: %s" % ex, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
