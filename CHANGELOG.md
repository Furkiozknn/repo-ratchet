# Changelog

## v0.1.0

First release.

- Twelve signals that measure a repository without executing anything inside it, each
  returning a value, the evidence behind it, and `None` rather than a guess when the
  measurement does not apply.
- Work records with three rules enforced in code: `advanced` needs the commit to have moved,
  `advanced` needs a check that ran and exited zero, and `no-change` needs a stated reason.
- A fenced check runner: allowlisted verbs, no shell, scrubbed environment, timeout, and a
  `ratchet.toml` escape hatch so a repository can say how it wants to be checked.
- Rounds: the queue orders by measured headroom, a repository leaves the queue once it has a
  record in the round, a repository whose commit has not moved sinks to the back, and the
  next round cannot open until the current one has covered everything.
- Discovery straight from the GitHub API, with a denylist that no survey can override.
- `ratchet discover | survey | queue | check | record | report`.
- 103 tests.
