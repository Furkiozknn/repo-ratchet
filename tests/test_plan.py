"""The queue: which repository is next, and what stops a round repeating itself."""

import pytest

from ratchet.plan import advance_round, build
from ratchet.records import Ledger, Record, Verification
from ratchet.survey import Opportunity, Survey

PASS = Verification("pytest -q", 0, 0.1)


def survey(repo, headroom_pairs, head="a" * 40):
    return Survey(
        repo=repo, head=head, taken_at="2026-01-01T00:00:00Z", signals={},
        opportunities=[Opportunity(n, h, "note for %s" % n) for n, h in headroom_pairs],
    )


def advanced(repo, round_n=1, after="b" * 40):
    return Record(round=round_n, repo=repo, outcome="advanced",
                  head_before="a" * 40, head_after=after,
                  summary="x", verifications=[PASS])


def test_the_queue_is_ordered_by_measured_headroom(tmp_path):
    surveys = [survey("low", [("a", 0.1)]), survey("high", [("a", 0.9)]), survey("mid", [("a", 0.5)])]
    _, queue, _ = build(surveys, Ledger(tmp_path))
    assert [e.repo for e in queue] == ["high", "mid", "low"]


def test_a_repository_recorded_this_round_leaves_the_queue(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced("done"))
    _, queue, finished = build([survey("done", [("a", 0.9)]), survey("todo", [("a", 0.1)])], led)
    assert [e.repo for e in queue] == ["todo"]
    assert [e.repo for e in finished] == ["done"]


def test_a_no_change_record_also_finishes_a_repository_for_the_round(tmp_path):
    led = Ledger(tmp_path)
    led.append(Record(round=1, repo="quiet", outcome="no-change", reason="read it, nothing open"))
    _, queue, finished = build([survey("quiet", [("a", 0.9)])], led)
    assert queue == [] and [e.repo for e in finished] == ["quiet"]


def test_an_unchanged_repository_sinks_to_the_back(tmp_path):
    led = Ledger(tmp_path)
    # recorded in round 1 and the commit has not moved since
    led.append(advanced("stale", round_n=1, after="c" * 40))
    surveys = [survey("stale", [("a", 0.9)], head="c" * 40), survey("fresh", [("a", 0.2)])]
    _, queue, _ = build(surveys, led, round_n=2)
    assert [e.repo for e in queue] == ["fresh", "stale"]
    assert queue[-1].unchanged_since_last_record is True


def test_a_repository_that_moved_since_its_record_is_not_marked_stale(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced("moved", round_n=1, after="c" * 40))
    _, queue, _ = build([survey("moved", [("a", 0.9)], head="d" * 40)], led, round_n=2)
    assert queue[0].unchanged_since_last_record is False


def test_skipped_repositories_never_enter_the_queue(tmp_path):
    _, queue, finished = build(
        [survey("archived-one", [("a", 0.9)]), survey("live", [("a", 0.1)])],
        Ledger(tmp_path),
        skipped={"archived-one": "archived"},
    )
    assert [e.repo for e in queue] == ["live"]
    assert finished == []


def test_an_entry_carries_the_evidence_not_a_task(tmp_path):
    _, queue, _ = build([survey("r", [("test_mass", 0.8), ("readme_depth", 0.4)])], Ledger(tmp_path))
    e = queue[0]
    assert "test_mass" in e.reason
    assert any("test_mass" in c for c in e.candidates)
    assert e.headroom == pytest.approx(1.2)


def test_a_repository_with_no_measured_room_says_so(tmp_path):
    _, queue, _ = build([survey("r", [])], Ledger(tmp_path))
    assert "no measurement shows room" in queue[0].reason


def test_a_round_cannot_advance_while_anything_is_outstanding(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced("one"))
    ok, msg = advance_round(led, [survey("one", []), survey("two", [])])
    assert ok is False and "two" in msg


def test_a_round_advances_once_every_repository_has_a_record(tmp_path):
    led = Ledger(tmp_path)
    led.append(advanced("one"))
    led.append(Record(round=1, repo="two", outcome="no-change", reason="nothing open"))
    ok, msg = advance_round(led, [survey("one", []), survey("two", [])])
    assert ok is True and "round 2 may begin" in msg
