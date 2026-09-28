# Changelog

The version is the one in `pyproject.toml` and `ratchet/__init__.py`. Nothing has been tagged
yet; the first tag will be `v0.2.0`.

## v0.2.0 — 2026-09-25

What two rounds of running the engine against 27 real repositories changed in it, plus a
security pass over the parts that touch other people's code.

### The fence and the surveyor

- **`bash -c` / `sh -c` is refused.** An allowed shell handed a command string is a shell by
  another name: the string got past the verb check and the argument check and was then parsed
  by the shell, `&&`, pipes and all. Running a script file (`bash -e check.sh`) is still a
  check. *Breaking* only for a `ratchet.toml` or `--command` that relied on `-c`.
- A check's stdin is closed, so a verb that would read a script from the terminal gets
  end-of-file instead of the session.
- A symlink that leads out of the checkout is no longer measured. `readme_commands` and
  `todo_density` keep the lines they find as evidence, and the weekly round commits surveys
  publicly, so a link to a file elsewhere on the machine could copy its lines into the survey.
  Links that stay inside the checkout are still followed.
- A repository name read back from `durum/depolar.json` has to be a GitHub repository name
  before it becomes a directory that `survey --refresh` deletes and re-clones. `../x` is out of
  range as `invalid name`. The clone URL goes after `--`.

### Measurements

- `test_count` counts hand-rolled GDScript cases and JavaScript runners, recognises
  `<name>-test.js`, and reports `None` or a lower bound instead of `0` when a test file
  declares its cases in a form it cannot count.
- `todo_density` only counts markers inside comments, so it no longer finds the pattern it
  searches with.
- `undocumented_surface` reads docstrings with `ast.get_docstring`, so a multi-line signature
  no longer hides one.
- `_walk` skips dotted directories, so `.ratchet-work/` (where other repositories get cloned)
  is not counted as part of this one.

### Records

- `Verification.expect` marks a negative control: a check that was run to fail and did. An
  `advanced` record still needs at least one check that had to succeed and did.
- The work log counts repositories, not records, so a repository opened twice in a round is
  one repository.

### Command line

- `ratchet discover` passes on GitHub's own reason for a refusal ("API rate limit exceeded")
  and suggests `GITHUB_TOKEN` when none is set.
- `ratchet survey --path .` names the survey after the directory instead of leaving it blank.
- `ratchet queue | head` no longer prints `[Errno 32] Broken pipe`.

### CI

- The suite runs on Linux, macOS and Windows with Python 3.11–3.14, and prints its
  `N passed` line.
- The self-check installs the package with `pip install .` and uses the installed `ratchet`,
  and checks that the fence refuses both `rm -rf /` and `bash -c "rm -rf /"`.
- The weekly round passes its `only` input through the environment instead of into the script.
- `actions/checkout` and `actions/setup-python` moved off the deprecated Node 20 versions (v7).

163 tests.

## v0.1.0

Never tagged; kept for the record of what the first version was.

- Twelve signals that measure a repository without executing anything inside it, each
  returning a value, the evidence behind it, and `None` rather than a guess when the
  measurement does not apply.
- Work records with three rules enforced in code: `advanced` needs the commit to have moved,
  `advanced` needs a check that ran and exited zero, and `no-change` needs a stated reason.
- A fenced check runner: allowlisted verbs, no shell, scrubbed environment, timeout, and a
  `ratchet.toml` so a repository can say how it wants to be checked.
- Rounds: the queue orders by measured headroom, a repository leaves the queue once it has a
  record in the round, a repository whose commit has not moved sinks to the back, and the
  next round cannot open until the current one has covered everything.
- Discovery straight from the GitHub API, with a denylist that no survey can override.
- `ratchet discover | survey | queue | check | record | report`.
- 103 tests.
