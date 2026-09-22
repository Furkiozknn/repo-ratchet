# repo-ratchet

A ratchet only turns one way.

This is the engine that keeps every repository on the account moving forward instead of
merely being maintained. It measures what a repository can currently do, ranks where the
room is, and — the part that matters — **refuses to write down work that nobody verified**.

```sh
ratchet discover Furkiozknn          # ask GitHub what exists
ratchet survey                       # clone each one and measure it
ratchet queue                        # which repository to open next, and why
ratchet check ./some-repo            # run that repository's own checks, inside a fence
ratchet record some-repo --round 1 --outcome advanced \
    --summary "..." --before <sha> --after <sha> --verifications v.json
ratchet report --out KAYITLAR.md     # the work log
```

No dependencies. Python 3.11 standard library only.

## What it is not

It is not another audit. An audit produces a report and the report is the output; here the
report is a by-product and the output is a repository that does more than it did last week.

It is also not a checklist. A linter, a game and an MCP server do not have the same next
step, and a tool that pretends they do produces the same three suggestions for all of them.
So `ratchet` measures and ranks, and stops there. Deciding *what* to do with a repository is
a judgement made by whoever opens it, with the measurements as evidence rather than as
instructions. The queue says so in as many words: every entry is labelled `candidates`.

## The three rules it enforces in code

Everything else here is measurement. These three are the reason the engine can be trusted
across rounds, and they live in `ratchet/records.py` where they are enforced, not in a
convention somebody has to remember.

**1. `advanced` requires the commit to have actually moved.** A record whose `head_before`
equals its `head_after` is rejected. You cannot write down an improvement that left no trace.

**2. `advanced` requires a check that ran and returned what it was run to return.** A
`Verification` has no constructor that omits the exit code, so a check that never happened
cannot be recorded as though it had. A check also declares what it was run to prove:
`expect=0` is the ordinary case, and a non-zero `expect` marks a **negative control** — the
gate run against the thing it is supposed to catch, which passes by failing. Round 1 recorded
106 checks and 23 of them exited non-zero on purpose; those records predate `expect`, so the
log counts them without being able to say which they were, and "106 checks, 83 passed" read
as 23 failures. An `advanced` record still needs at least one check that had to succeed and
did: proving the gates bite is not proving the change works.

**3. `no-change` requires a stated reason.** "Nothing worth doing here" is a legitimate and
useful outcome — but it has to say what was looked at. A silent skip and a considered pass
look identical a month later, so the engine does not allow the silent one.

```python
>>> Record(round=1, repo="x", outcome="advanced",
...        head_before="a"*40, head_after="a"*40, summary="tidied up")
RecordError: x: outcome is 'advanced' but the commit did not move (aaaaaaaaaaaa)
```

## What it measures

Twelve signals, each returning a number **and the evidence behind it**. A signal that does
not apply returns `None` and stays `None` all the way through — "there is no test directory"
and "there are zero tests in the test directory" are different facts, and a tool that renders
both as `0` has destroyed the more useful one.

| Signal | What it answers |
| --- | --- |
| `languages` | what the repository is actually written in, by source bytes |
| `test_mass` | test bytes per source byte — works without running anything |
| `test_count` | declared test cases, counted per language — `None` rather than `0` when a repository's test files declare their cases in a form this cannot count |
| `undocumented_surface` | public Python/Rust symbols with no doc comment |
| `ci_breadth` | how many distinct runners the CI really exercises |
| `readme_commands` | the commands a first-time visitor will paste |
| `readme_depth` | how much that visitor is told at all |
| `todo_density` | unfinished business the code admits to |
| `largest_source_file` | where an architecture usually strains first |
| `declared_dependencies` | how much the project asks the world to install |
| `release_lag` | commits on the branch since the last tag |
| `metadata_present` | whether it carries the ecosystem's `project-meta.json` |

Some signals also report `headroom`, a 0–1 hint used only for ordering the queue. It is a
ranking input, never a verdict, and a signal is free to leave it unset.

## The fence around running other people's code

`ratchet check` has to run a repository's own test command to be able to say it passed. That
is the most dangerous thing here, so the fence is narrow and explicit:

- the verb must be in an allowlist of build and test entry points, or be declared by the
  target repository's own `ratchet.toml`;
- arguments that look like publishing or fetching (`publish`, `--token`, `push`, `curl`) are
  refused before anything starts;
- **nothing runs through a shell**, so a command cannot grow a `&&`, a pipe or a redirect it
  did not declare — the tail arrives as ordinary arguments to the first command, and there is
  a test that proves it;
- the environment is scrubbed to a handful of variables, the working directory is the
  checkout, and there is a timeout.

This is a fence, not a sandbox. It stops a typo and an obviously wrong command; it does not
contain a hostile repository. Keeping hostile repositories out of range is what the denylist
in `ratchet/targets.py` is for, and `kor` is in it.

## Rounds

A **round** is one pass over every repository. The engine will not open round *n+1* until
every surveyed repository has a record in round *n* — the whole point of a round is that
nothing gets revisited until everything has been visited once.

Within a round the queue orders by measured headroom, with one exception: a repository whose
commit has not moved since its last record sinks to the back. It already had a round at
exactly this code, so there is nothing new to find in it.

Records are append-only JSON Lines, one file per round under [`kayitlar/`](kayitlar/), so a
diff shows a round's work and nothing rewrites history.

## What round 1 found

Round 1 is closed: **27 repositories, 27 records, 106 checks recorded.** The engine
is not the point; what it finds is. A few of the entries, each with the check that
backs it in [`kayitlar/tur-01.jsonl`](kayitlar/) and the whole log in
[`KAYITLAR.md`](KAYITLAR.md):

- Wiring `godot-refcheck`'s own GitHub Action into four game repositories broke all
  four — and the wrong way round. The action read its counts out of prose that a
  project with **no findings** never prints, so under the runner's `bash -e` it
  failed on exactly the repositories that were clean. Fixed, with a gate that runs
  the action's own shell across clean and broken fixtures at every `fail-on` level.
- The project directory's generator crashed on any repository whose `summary` was
  `null`: `.get("summary", "")` returns `None` when the key is present and null.
  Every repository happened to have one, so it had never fired.
- Nothing in a 70-agent roster stopped two agents claiming the same trigger phrase,
  so the user could say the right sentence and get the wrong agent with every file
  still valid. Two real collisions, both closed.
- A vendoring script that began with `rm -rf vendor/` deleted the font the page
  loads, and nothing noticed: the font is declared with a fallback stack and
  `font-display: swap`, so the game kept loading, made no external request, logged
  no error, and quietly stopped being itself.
- A contract validator with a 106-check self-test that said "clean" — while eight
  of its nineteen enforcement points could be removed entirely without a single
  check failing. `type` was one of them.
- Running it on itself, four times: `test_count` read four shipped games as having
  no tests at all, because they hand-roll GDScript assertions rather than use a
  framework; `todo_density` counted the pattern it searches with;
  `undocumented_surface` missed every docstring that followed a multi-line
  signature; and `_walk` counted 27 other repositories as part of this one,
  because `.ratchet-work/` is where they get cloned.

The last one is the pattern worth naming: a measurement that is wrong inflates the
headroom of everything it touches, so the engine's own signals get corrected by the
rounds they misread.

## Round 2, in progress

Round 2 does not repeat round 1. Each entry builds on what the first round left
open in that repository, and the first four are in
[`kayitlar/tur-02.jsonl`](kayitlar/):

- `buradane` closes the gap round 1's executable migration document found on its
  first run: two OSM tags the frontend depended on and no backend schema produced.
- `masal` audits the screen the child actually reads. Lighthouse scored
  accessibility 100 — on the form it happens to open on; the reading screen had
  never been audited, and had two WCAG 2.1 AA contrast failures in it.
- `godot-refcheck` learned to judge the claim where it is written. None of the four
  games here has a `[connection]` block at all; they make 145 `.connect(` calls from
  GDScript instead, so the resolver was reading a file section most projects never
  write.
- This repository corrected its own measurement again: `<name>-test.js` is a test
  file, and a test file nobody can count cases in is not zero cases.

## Working on this repository

```sh
python3 -m pytest -q
```

130 tests. The suite builds throwaway repositories on disk — including real git ones, for the
signals that need history — so every measurement is tested against a repository it has never
seen. The record rules get the heaviest coverage, because a record that can lie is a record
that will.

## Where it fits

This is the engine behind the rest of [the ecosystem](https://furkiozknn.github.io/).
[`repo-vet`](https://github.com/Furkiozknn/repo-vet) checks whether a README's promises match
what is in the repository; this decides which repository to work on next and holds the memory
between rounds. They answer different questions and neither replaces the other.

## Licence

MIT — see [LICENSE](LICENSE).
