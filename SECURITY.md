# Security policy

## What this tool does that can hurt

`repo-ratchet` does two things with other people's code, and they carry different risk:

- **`ratchet survey` reads.** It clones a repository and measures its files. It never
  executes anything inside it, and it only reads files that resolve inside the checkout:
  a symlink that leads out of the checkout is not followed, because surveys are committed
  publicly and some signals keep the lines they found as evidence.
- **`ratchet check` runs.** It executes the repository's own test command. That is what
  the fence in [`ratchet/verify.py`](ratchet/verify.py) is for: allowlisted verbs, no shell
  (including no `bash -c`), refused publishing/fetching arguments, a scrubbed environment
  without tokens, closed stdin, and a timeout.

**The fence is not a sandbox.** An allowed verb such as `python3` or `npm test` runs
whatever the repository's test suite contains, with your user's permissions. The fence
stops a typo and an obviously wrong command; it does not contain a hostile repository.
Only run `ratchet check` on code you would run yourself, or run it in a throwaway VM or
container. The denylist in [`ratchet/targets.py`](ratchet/targets.py) keeps repositories
out of range entirely.

`ratchet discover` sends `GITHUB_TOKEN`/`GH_TOKEN` to `api.github.com` only. The token is
not passed to anything `ratchet check` runs.

## In scope

- a command that gets past the fence when it should be refused (a verb, an argument, or a
  shell reached some other way);
- a survey that reads, executes or writes anything outside the checkout it measures;
- a token or other secret reaching a check's environment, a survey, a record or a log;
- a crafted `durum/*.json` or `kayitlar/*.jsonl` that makes the engine delete or write
  outside its work directory.

## Reporting

Please report privately through
[GitHub Security Advisories](https://github.com/Furkiozknn/repo-ratchet/security/advisories/new)
rather than a public issue. Include the command or repository layout that reproduces it
and what you expected the fence or survey to do. There is no bounty; you will get an answer
and credit in the changelog if you want it.

Only the latest commit on `main` is supported.
