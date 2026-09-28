"""Running a repository's own checks, inside a fence.

The engine has to be able to say "the tests passed" and mean it, which means
it has to run them. Running someone else's build script is the most dangerous
thing this tool does, so the fence is explicit and narrow:

* the command has to start with a verb from :data:`ALLOWED`. A repository's
  own ``ratchet.toml`` chooses *which* commands run, never which verbs are
  allowed: the file comes from the checkout being measured, so letting it
  widen the fence would let the fenced code open its own gate;
* it runs with the checkout as its working directory and cannot be pointed
  outside it;
* it gets a timeout and a scrubbed environment;
* nothing is ever run with a shell, so a command cannot grow a ``&&`` or a
  redirect it did not declare - and that includes asking an allowed shell
  for one: ``bash -c "..."`` is refused, because its string would be parsed
  by the shell, past the verb check and the argument check both;
* stdin is closed, so a verb that would read a script from the terminal
  (``bash`` with no arguments) gets end-of-file instead of the session.

What this fence is not: a sandbox. It stops a typo and an obviously wrong
command, not a hostile repository. The denylist in :mod:`ratchet.targets` is
what keeps hostile repositories out of range in the first place.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

from .records import Verification

#: Command verbs the engine will run without being told to by the repository.
#: Every one of them is a build or test entry point, not a package installer
#: and not a network client.
ALLOWED = {
    "pytest", "python", "python3", "cargo", "go", "npm", "pnpm", "yarn",
    "make", "just", "bash", "sh", "node", "ruff", "mypy", "shellcheck",
    "uv", "uvx", "godot", "dotnet", "gradle",
}

#: Arguments that would take the command outside the checkout or turn it into
#: something other than a check.
FORBIDDEN_ARGS = ("--upload", "publish", "--token", "push", "curl", "wget")

DEFAULT_TIMEOUT = 900

#: Allowed verbs that are shells. Running a script file with them is a check;
#: handing them a command string with ``-c`` is a shell by another name.
SHELLS = {"bash", "sh"}

#: Shell options that take a separate value, so the value is not mistaken for
#: the script name when looking for ``-c``.
_SHELL_OPTS_WITH_VALUE = {"-o", "+o", "-O", "+O", "--rcfile", "--init-file"}


def _shell_inline_command(args: list[str]) -> str | None:
    """The option that makes a shell run a command string, if there is one.

    Options come before the script name; once the first operand is seen the
    rest are the script's own arguments and a ``-c`` there is harmless.
    """
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--" or not arg.startswith(("-", "+")) or arg in ("-", "+"):
            return None
        if arg in _SHELL_OPTS_WITH_VALUE:
            i += 2
            continue
        if not arg.startswith("--") and "c" in arg[1:]:
            return arg
        i += 1
    return None


class VerifyError(RuntimeError):
    """The command was refused before it ran."""


def _clean_env() -> dict[str, str]:
    """A minimal environment: enough to build, nothing borrowed from the session."""
    keep = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "CARGO_HOME", "RUSTUP_HOME")
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["CI"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def check_command(command: str, extra_allowed: set[str] | None = None) -> list[str]:
    """Parse and fence a command, or raise before anything runs."""
    parts = shlex.split(command)
    if not parts:
        raise VerifyError("empty command")
    verb = Path(parts[0]).name
    allowed = ALLOWED | (extra_allowed or set())
    if verb not in allowed:
        raise VerifyError(
            "%r is not a command this engine runs. Allowed verbs: %s"
            % (verb, ", ".join(sorted(allowed)))
        )
    if verb in SHELLS:
        inline = _shell_inline_command(parts[1:])
        if inline is not None:
            raise VerifyError(
                "%s %s runs a command string through a shell; put the check in a "
                "script file and run that instead" % (verb, inline)
            )
    for arg in parts[1:]:
        low = arg.lower()
        for bad in FORBIDDEN_ARGS:
            if bad in low:
                raise VerifyError("%r looks like publishing or fetching, not checking" % arg)
    return parts


def run(
    command: str,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT,
    note: str = "",
    extra_allowed: set[str] | None = None,
) -> Verification:
    """Run one check and return what happened, exit code and all.

    A command that could not start, or that ran out of time, comes back as a
    failed verification rather than an exception, because "the suite does not
    run" is itself something the round needs to record.
    """
    cwd = Path(cwd).resolve()
    if not cwd.is_dir():
        raise VerifyError("working directory does not exist: %s" % cwd)
    parts = check_command(command, extra_allowed)
    started = time.time()
    try:
        proc = subprocess.run(
            parts,
            cwd=str(cwd),
            env=_clean_env(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        code, out = proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        code, out = 124, "timed out after %ds" % timeout
    except OSError as ex:
        code, out = 127, "could not start: %s" % ex
    tail = "\n".join(out.strip().splitlines()[-25:])
    return Verification(
        command=command,
        exit_code=code,
        duration_s=round(time.time() - started, 2),
        note=note,
        output_tail=tail,
    )


#: How to check a repository when it has not said otherwise. The first entry
#: whose marker file exists is the one that gets run.
DEFAULT_CHECKS: tuple[tuple[str, str], ...] = (
    ("Cargo.toml", "cargo test"),
    ("pyproject.toml", "python3 -m pytest -q"),
    ("package.json", "npm test"),
    ("Makefile", "make test"),
)


def suggest(root: Path) -> list[str]:
    """What this repository's own check probably is.

    ``ratchet.toml`` in the repository wins: a project that says how it wants
    to be checked is always more reliable than a guess from a filename.
    """
    root = Path(root)
    cfg = root / "ratchet.toml"
    if cfg.is_file():
        found: list[str] = []
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("check") and "=" in line:
                value = line.split("=", 1)[1].strip()
                if value.startswith("[") :
                    found += [x.strip().strip("\"'") for x in value.strip("[]").split(",") if x.strip()]
                else:
                    found.append(value.strip("\"'"))
        if found:
            return [c for c in found if c]
    return [cmd for marker, cmd in DEFAULT_CHECKS if (root / marker).is_file()]
