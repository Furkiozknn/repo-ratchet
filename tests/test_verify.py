"""The fence around running someone else's build.

These tests are about what does *not* run. A check that quietly runs a command
it should have refused is the failure mode that matters here.
"""

import json

import pytest

from ratchet import verify
from ratchet.verify import VerifyError


def test_a_command_outside_the_allowed_verbs_is_refused():
    with pytest.raises(VerifyError, match="not a command this engine runs"):
        verify.check_command("rm -rf /")


def test_an_empty_command_is_refused():
    with pytest.raises(VerifyError, match="empty command"):
        verify.check_command("   ")


def test_a_publishing_argument_is_refused():
    with pytest.raises(VerifyError, match="publishing or fetching"):
        verify.check_command("cargo publish --token abc")


def test_a_push_argument_is_refused():
    with pytest.raises(VerifyError, match="publishing or fetching"):
        verify.check_command("make push")


def test_an_allowed_verb_survives_with_its_arguments():
    assert verify.check_command("pytest -q tests/") == ["pytest", "-q", "tests/"]


def test_a_full_path_is_matched_on_its_basename():
    assert verify.check_command("/usr/bin/python3 -m pytest")[0] == "/usr/bin/python3"


def test_a_repository_can_widen_the_fence_for_itself():
    assert verify.check_command("myrunner --all", extra_allowed={"myrunner"})[0] == "myrunner"


def test_there_is_no_shell_so_a_chained_command_cannot_smuggle_a_second_one(tmp_path):
    # With a shell this would run `touch smuggled` after the check. Without
    # one the whole tail arrives as ordinary arguments to the first command,
    # which is the point: a check cannot grow a second half it did not declare.
    (tmp_path / "argv.py").write_text(
        "import sys, json\n"
        "open('argv.json', 'w').write(json.dumps(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    v = verify.run("python3 argv.py && touch smuggled", tmp_path)
    assert v.passed
    assert not (tmp_path / "smuggled").exists()
    assert json.loads((tmp_path / "argv.json").read_text()) == ["&&", "touch", "smuggled"]


def test_a_passing_command_is_recorded_as_passing(tmp_path):
    v = verify.run("python3 -c pass", tmp_path, note="smoke")
    assert v.passed and v.note == "smoke" and v.duration_s >= 0


def test_a_failing_command_keeps_its_exit_code(tmp_path):
    (tmp_path / "boom.py").write_text("raise SystemExit(3)\n", encoding="utf-8")
    v = verify.run("python3 boom.py", tmp_path)
    assert v.exit_code == 3 and not v.passed


def test_a_timeout_is_a_failed_verification_not_an_exception(tmp_path):
    (tmp_path / "slow.py").write_text("import time\ntime.sleep(5)\n", encoding="utf-8")
    v = verify.run("python3 slow.py", tmp_path, timeout=1)
    assert v.exit_code == 124 and "timed out" in v.output_tail


def test_a_missing_working_directory_is_refused(tmp_path):
    with pytest.raises(VerifyError, match="working directory does not exist"):
        verify.run("python3 -c pass", tmp_path / "nope")


def test_the_environment_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("RATCHET_SECRET", "hunter2")
    (tmp_path / "env.py").write_text(
        "import os, sys\nsys.exit(9 if 'RATCHET_SECRET' in os.environ else 0)\n", encoding="utf-8")
    v = verify.run("python3 env.py", tmp_path)
    assert v.exit_code == 0, v.output_tail


def test_output_tail_is_bounded(tmp_path):
    (tmp_path / "loud.py").write_text("for i in range(500):\n    print(i)\n", encoding="utf-8")
    v = verify.run("python3 loud.py", tmp_path)
    assert v.passed
    assert len(v.output_tail.splitlines()) <= 25


def test_suggest_reads_the_manifest(make_repo):
    root = make_repo("a", {"Cargo.toml": "[package]\nname='x'\n"})
    assert verify.suggest(root) == ["cargo test"]


def test_suggest_prefers_the_repositorys_own_config(make_repo):
    root = make_repo("b", {
        "pyproject.toml": "[project]\nname='x'\n",
        "ratchet.toml": 'check = ["python3 -m pytest -q", "ruff check ."]\n',
    })
    assert verify.suggest(root) == ["python3 -m pytest -q", "ruff check ."]


def test_suggest_accepts_a_single_string_check(make_repo):
    root = make_repo("c", {"ratchet.toml": 'check = "make test"\n'})
    assert verify.suggest(root) == ["make test"]


def test_suggest_is_empty_when_nothing_says_how(make_repo):
    root = make_repo("d", {"README.md": "x"})
    assert verify.suggest(root) == []


def test_a_verification_serialises_for_the_record(tmp_path):
    v = verify.run("python3 -c pass", tmp_path)
    assert json.loads(json.dumps(v.as_dict()))["exit_code"] == 0


# --- an allowed shell is still not a shell for hire -------------------------


@pytest.mark.parametrize("command", [
    'bash -c "pytest && touch smuggled"',
    "sh -c true",
    "sh -ec true",
    "bash -lc true",
    "bash -o pipefail -c true",
    "bash --norc -c true",
])
def test_a_shell_asked_for_a_command_string_is_refused(command):
    # `bash -c "..."` passes the verb check (bash is allowed) and the argument
    # check (the string is one argument), and then the shell parses it: the
    # `&&`, the pipe and a spelled-apart `cu''rl` all come back. It is the
    # shell the fence says nothing runs through.
    with pytest.raises(VerifyError, match="through a shell"):
        verify.check_command(command)


@pytest.mark.parametrize("command", [
    "bash run.sh",
    "bash -e run.sh",
    "sh -x run.sh",
    "bash run.sh -c passed-to-the-script",
    "bash -- -c",
])
def test_a_shell_running_a_script_file_is_still_a_check(command):
    assert verify.check_command(command)[0] in ("bash", "sh")


def test_a_refused_shell_command_never_runs(tmp_path):
    with pytest.raises(VerifyError):
        verify.run('bash -c "touch smuggled"', tmp_path)
    assert not (tmp_path / "smuggled").exists()


def test_a_check_gets_no_stdin(tmp_path):
    # A verb that reads its script from stdin (plain `bash`, `python3 -`)
    # must see end-of-file, not whatever terminal or pipe ratchet was given.
    (tmp_path / "stdin.py").write_text(
        "import sys\n"
        "sys.exit(0 if sys.stdin.read() == '' else 5)\n",
        encoding="utf-8",
    )
    # Drive it from a separate process whose own stdin is a live pipe: under
    # pytest fd 0 is often /dev/null already, which would hide the leak.
    import subprocess
    import sys
    from pathlib import Path

    driver = (
        "import sys; from ratchet import verify; "
        "v = verify.run('python3 stdin.py', sys.argv[1]); "
        "sys.exit(v.exit_code)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", driver, str(tmp_path)],
        input="bash would read this as a script\n", text=True, capture_output=True,
        cwd=str(Path(verify.__file__).resolve().parent.parent),
    )
    assert proc.returncode == 0, proc.stderr
