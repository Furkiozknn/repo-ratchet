"""Surveys end to end, the target list, the reports, and the command line."""

import json

import pytest

from ratchet import render, targets
from ratchet.cli import main
from ratchet.records import Ledger, Record, Verification
from ratchet.survey import load_all, save_all, take

PASS = Verification("pytest -q", 0, 0.5)


# --- survey ---------------------------------------------------------------


def test_a_survey_names_the_repository_and_the_commit(make_repo, head_of):
    root = make_repo("thing", {"a.py": "x = 1\n"}, git=True)
    s = take(root)
    assert s.repo == "thing"
    assert s.head == head_of(root)


def test_a_survey_of_a_plain_directory_has_no_commit(make_repo):
    assert take(make_repo("plain", {"a.py": "x = 1\n"})).head is None


def test_a_survey_holds_every_signal(make_repo):
    from ratchet import signals

    s = take(make_repo("full", {"a.py": "x = 1\n"}))
    assert len(s.signals) == len(signals.ALL)
    assert set(s.signals) == {fn(make_repo("probe", {})).name for fn in signals.ALL}


def test_opportunities_are_sorted_and_only_include_real_headroom(make_repo):
    s = take(make_repo("o", {"src/a.py": "x = 1\n" * 300}))
    assert all(o.headroom > 0 for o in s.opportunities)
    assert s.opportunities == sorted(s.opportunities, key=lambda o: -o.headroom)


def test_a_thorough_repository_has_less_headroom_than_a_bare_one(make_repo):
    bare = take(make_repo("bare", {"src/a.py": "def f():\n    return 1\n" * 100}))
    good = take(make_repo("good", {
        "src/a.py": 'def f():\n    """Doc."""\n    return 1\n',
        "tests/test_a.py": "def test_f():\n    assert True\n" * 20,
        "README.md": "# good\n" + ("plenty of prose. " * 400),
        "project-meta.json": '{"id": "good"}',
        ".github/workflows/ci.yml": "jobs:\n  a:\n    runs-on: ubuntu-latest\n  b:\n    runs-on: macos-latest\n  c:\n    runs-on: windows-latest\n",
    }))
    assert good.total_headroom < bare.total_headroom


def test_a_survey_survives_a_round_trip_through_disk(make_repo, tmp_path):
    s = take(make_repo("rt", {"a.py": "x = 1\n"}))
    p = tmp_path / "s.json"
    save_all(p, [s])
    back = load_all(p)
    assert len(back) == 1
    assert back[0].repo == "rt"
    assert back[0].total_headroom == s.total_headroom


def test_loading_a_missing_survey_file_is_empty_not_an_error(tmp_path):
    assert load_all(tmp_path / "nope.json") == []


def test_surveying_something_that_is_not_a_directory_is_an_error(tmp_path):
    with pytest.raises(NotADirectoryError):
        take(tmp_path / "nothing-here")


def test_a_broken_signal_does_not_lose_the_others(make_repo, monkeypatch):
    from ratchet import signals

    def boom(root):
        raise RuntimeError("nope")

    boom.__name__ = "boom"
    monkeypatch.setattr(signals, "ALL", (boom, signals.todo_density))
    s = take(make_repo("b", {"a.py": "x = 1  # TODO\n"}))
    assert s.signals["boom"]["value"] is None
    assert s.signals["todo_density"]["value"] == 1


# --- targets --------------------------------------------------------------


def test_the_denylist_puts_a_repository_out_of_range():
    t = targets.Target("kor", "main", "u", False, 100)
    assert t.in_range is False
    assert "out of the engine's reach" in t.skip_reason


def test_an_archived_repository_is_out_of_range():
    t = targets.Target("old", "main", "u", True, 100)
    assert t.in_range is False and "read-only" in t.skip_reason


def test_an_empty_repository_is_out_of_range():
    assert targets.Target("blank", "main", "u", False, 0).in_range is False


def test_a_normal_repository_is_in_range():
    t = targets.Target("fine", "main", "u", False, 42)
    assert t.in_range is True and t.skip_reason is None


def test_targets_load_from_a_saved_discovery(tmp_path):
    p = tmp_path / "t.json"
    p.write_text(json.dumps({"targets": [
        {"name": "b", "default_branch": "main", "clone_url": "u", "archived": False, "size_kb": 1},
        {"name": "a", "default_branch": "master", "clone_url": "u", "archived": True, "size_kb": 1},
    ]}), encoding="utf-8")
    got = targets.load_offline(str(p))
    assert [t.name for t in got] == ["a", "b"]
    assert got[0].archived is True


# --- reports --------------------------------------------------------------


def test_the_markdown_log_separates_rounds(tmp_path):
    recs = [
        Record(round=1, repo="one", outcome="advanced", head_before="a" * 40, head_after="b" * 40,
               summary="added tests", verifications=[PASS]),
        Record(round=1, repo="two", outcome="no-change", reason="nothing measured as open"),
        Record(round=2, repo="one", outcome="no-change", reason="already covered"),
    ]
    md = render.records_markdown(recs)
    assert "### Round 1" in md and "### Round 2" in md
    assert "added tests" in md and "nothing measured as open" in md
    assert "`pytest -q` → 0" in md


def test_an_empty_log_says_so():
    assert "No rounds recorded yet" in render.records_markdown([])


def test_the_json_log_counts_outcomes_and_checks():
    recs = [
        Record(round=1, repo="one", outcome="advanced", head_before="a" * 40, head_after="b" * 40,
               summary="x", verifications=[PASS, Verification("ruff", 1)]),
        Record(round=1, repo="two", outcome="blocked", reason="needs an account"),
    ]
    d = json.loads(render.records_json(recs))
    r = d["rounds"][0]
    assert r == {"round": 1, "repositories": 2, "records": 2, "advanced": 1,
                 "no_change": 0, "blocked": 1, "checks_run": 2, "checks_passed": 1}


def test_a_round_that_opens_one_repository_twice_still_counts_it_once():
    # Round 2 did this: verifying godot-refcheck's own entry against the
    # corpus found five false positives, so the repository was opened again
    # in the same round. Counting records said "5 repositories" in a round of
    # four - the engine misreporting itself.
    recs = [
        Record(round=2, repo="one", outcome="advanced", head_before="a" * 40,
               head_after="b" * 40, summary="first pass", verifications=[PASS]),
        Record(round=2, repo="one", outcome="advanced", head_before="b" * 40,
               head_after="c" * 40, summary="the correction", verifications=[PASS]),
        Record(round=2, repo="two", outcome="no-change", reason="nothing open"),
    ]
    d = json.loads(render.records_json(recs))["rounds"][0]
    assert d["repositories"] == 2 and d["records"] == 3

    md = render.records_markdown(recs)
    assert "2 repositories over 3 records" in md
    # Both records still get their own row: the correction is not hidden.
    assert md.count("| [one](") == 2


# --- command line ---------------------------------------------------------


def test_cli_survey_of_a_path_prints_the_measurements(make_repo, capsys):
    root = make_repo("cli", {"a.py": "x = 1\n"})
    assert main(["survey", "--path", str(root), "--repo", "cli"]) == 0
    out = capsys.readouterr().out
    assert "cli @" in out and "total headroom" in out


def test_cli_check_runs_and_reports_the_exit_code(make_repo, capsys, tmp_path):
    root = make_repo("chk", {"pyproject.toml": "[project]\nname='x'\n"})
    out_file = tmp_path / "v.json"
    code = main(["check", str(root), "--command", "python3 -c pass", "--out", str(out_file)])
    assert code == 0
    assert json.loads(out_file.read_text())[0]["exit_code"] == 0


def test_cli_check_refuses_a_command_outside_the_fence(make_repo, capsys):
    root = make_repo("chk2", {"a.py": "x\n"})
    assert main(["check", str(root), "--command", "rm -rf /"]) == 2
    assert "refused" in capsys.readouterr().err


def test_cli_record_refuses_an_unbacked_claim(tmp_path, capsys):
    code = main([
        "--records", str(tmp_path), "record", "r", "--round", "1",
        "--outcome", "advanced", "--summary", "x",
        "--before", "a" * 40, "--after", "b" * 40,
    ])
    assert code == 2
    assert "no verification that had to" in capsys.readouterr().err


def test_cli_record_writes_a_backed_claim(tmp_path, capsys):
    v = tmp_path / "v.json"
    v.write_text(json.dumps([PASS.as_dict()]), encoding="utf-8")
    code = main([
        "--records", str(tmp_path), "record", "r", "--round", "1",
        "--outcome", "advanced", "--summary", "raised the test count",
        "--before", "a" * 40, "--after", "b" * 40, "--verifications", str(v),
    ])
    assert code == 0
    assert Ledger(tmp_path).read(1)[0].summary == "raised the test count"


def test_cli_queue_without_surveys_explains_itself(tmp_path, capsys):
    assert main(["--state", str(tmp_path), "queue"]) == 2
    assert "run `ratchet survey`" in capsys.readouterr().err


def test_cli_queue_next_prints_one_name(make_repo, tmp_path, capsys):
    s = take(make_repo("q", {"src/a.py": "x = 1\n" * 200}))
    save_all(tmp_path / "olcumler.json", [s])
    assert main(["--state", str(tmp_path), "--records", str(tmp_path / "k"), "queue", "--next"]) == 0
    assert capsys.readouterr().out.strip() == "q"


def test_cli_report_writes_a_file(tmp_path):
    led = Ledger(tmp_path / "k")
    led.append(Record(round=1, repo="one", outcome="no-change", reason="nothing open"))
    out = tmp_path / "log.md"
    assert main(["--records", str(tmp_path / "k"), "report", "--out", str(out)]) == 0
    assert "nothing open" in out.read_text()
