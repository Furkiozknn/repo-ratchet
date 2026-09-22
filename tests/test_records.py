"""The record rules are the whole point, so they are tested hardest.

Every one of these tests is about something the engine must refuse to write
down, because a record that can lie is a record that will.
"""

import json

import pytest

from ratchet.records import ADVANCED, Ledger, Record, RecordError, Verification

PASS = Verification("pytest -q", 0, 1.2)
FAIL = Verification("pytest -q", 1, 1.2)


def advanced(**kw):
    base = dict(
        round=1, repo="r", outcome="advanced",
        head_before="a" * 40, head_after="b" * 40,
        summary="did a thing", verifications=[PASS],
    )
    base.update(kw)
    return Record(**base)


def test_an_advanced_record_needs_the_commit_to_have_moved():
    with pytest.raises(RecordError, match="did not move"):
        advanced(head_after="a" * 40)


def test_an_advanced_record_needs_a_passing_check():
    with pytest.raises(RecordError, match="no verification that had to"):
        advanced(verifications=[FAIL])


def test_an_advanced_record_needs_any_check_at_all():
    with pytest.raises(RecordError, match="no verification that had to"):
        advanced(verifications=[])


def test_an_advanced_record_needs_a_summary():
    with pytest.raises(RecordError, match="say what changed"):
        advanced(summary="   ")


def test_an_advanced_record_needs_both_commits():
    with pytest.raises(RecordError, match="commit before and after"):
        advanced(head_before=None)


def test_a_no_change_record_needs_a_reason():
    with pytest.raises(RecordError, match="has to say why"):
        Record(round=1, repo="r", outcome="no-change")


def test_a_no_change_record_is_fine_with_a_reason_and_no_checks():
    r = Record(round=1, repo="r", outcome="no-change", reason="read it; nothing measured as open")
    assert r.verified is False


def test_a_blocked_record_needs_a_reason():
    with pytest.raises(RecordError, match="has to say why"):
        Record(round=1, repo="r", outcome="blocked")


def test_an_unknown_outcome_is_refused():
    with pytest.raises(RecordError, match="outcome must be one of"):
        Record(round=1, repo="r", outcome="improved", summary="x")


def test_rounds_start_at_one():
    with pytest.raises(RecordError, match="rounds start at 1"):
        advanced(round=0)


def test_a_record_needs_a_repository():
    with pytest.raises(RecordError, match="needs a repository name"):
        advanced(repo="")


def test_a_valid_advanced_record_survives_a_round_trip():
    r = advanced()
    back = Record.from_dict(json.loads(json.dumps(r.as_dict())))
    assert back.summary == r.summary
    assert back.verifications[0].passed


def test_the_ledger_appends_one_line_per_record(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced(repo="one"))
    led.append(advanced(repo="two"))
    lines = (tmp_path / "tur-01.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    assert {json.loads(x)["repo"] for x in lines} == {"one", "two"}


def test_the_ledger_keeps_rounds_in_separate_files(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced(repo="one", round=1))
    led.append(advanced(repo="one", round=2))
    assert (tmp_path / "tur-01.jsonl").is_file()
    assert (tmp_path / "tur-02.jsonl").is_file()
    assert led.rounds() == [1, 2]


def test_done_in_round_counts_every_outcome(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced(repo="one"))
    led.append(Record(round=1, repo="two", outcome="no-change", reason="nothing open"))
    assert led.done_in_round(1) == {"one", "two"}


def test_current_round_is_the_highest_one_with_records(tmp_path):
    led = Ledger(tmp_path)
    assert led.current_round() == 1
    led.append(advanced(round=3))
    assert led.current_round() == 3


def test_last_for_returns_the_newest_round(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced(repo="one", round=1, summary="first"))
    led.append(advanced(repo="one", round=2, summary="second"))
    assert led.last_for("one").summary == "second"


def test_last_for_is_none_when_the_repository_is_new(tmp_path):
    assert Ledger(tmp_path).last_for("never-seen") is None


def test_reading_an_empty_directory_is_not_an_error(tmp_path):
    assert Ledger(tmp_path / "missing").read() == []


# ---------------------------------------------------------------------------
# A check that was run to fail
# ---------------------------------------------------------------------------


def test_a_negative_control_passes_when_it_fails():
    v = Verification(command="the gate against a broken fixture", exit_code=1, expect=1)
    assert v.passed is True
    assert v.negative_control is True


def test_a_negative_control_that_succeeds_has_not_passed():
    """The gate did not close. That is the finding."""
    v = Verification(command="the gate against a broken fixture", exit_code=0, expect=1)
    assert v.passed is False


def test_an_ordinary_check_is_unchanged():
    assert Verification(command="pytest", exit_code=0).passed is True
    assert Verification(command="pytest", exit_code=1).passed is False
    assert Verification(command="pytest", exit_code=0).negative_control is False


def test_negative_controls_alone_cannot_back_an_advanced_record():
    """Proving the gates bite is not proving the change works."""
    with pytest.raises(RecordError, match="no verification that had to"):
        Record(
            round=1, repo="x", outcome=ADVANCED, summary="tightened a gate",
            head_before="a" * 40, head_after="b" * 40,
            verifications=[Verification(command="old fixture", exit_code=1, expect=1)],
        )


def test_one_ordinary_passing_check_alongside_them_is_enough():
    r = Record(
        round=1, repo="x", outcome=ADVANCED, summary="tightened a gate",
        head_before="a" * 40, head_after="b" * 40,
        verifications=[
            Verification(command="old fixture", exit_code=1, expect=1),
            Verification(command="pytest -q", exit_code=0),
        ],
    )
    assert r.outcome == ADVANCED


def test_records_written_before_expect_existed_still_load():
    """Round 1's 98 checks carry no `expect`; they must keep their meaning."""
    v = Verification(**{"command": "pytest", "exit_code": 0, "duration_s": 0.0,
                        "note": "", "output_tail": ""})
    assert v.expect == 0
    assert v.passed is True
