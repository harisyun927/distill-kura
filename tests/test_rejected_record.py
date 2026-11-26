"""#710 PR-1: what the pipeline throws away leaves a record (observation only).

Two places used to lose it: a scribe whose answer failed the shape or the floor
("the scribe did not keep the shape" - a log line and nothing else), and a brain whose
reply was not a candidate list (only its first 200 characters survived, on the shelf).
These tests pin the records AND that the verdicts themselves did not move.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distill_kura.distill import Distiller                    # noqa: E402
from tests.test_extend_continue import (                      # noqa: E402
    LINES, SCRIBE, SPOT, build, journal, script)


def _read(d, name):
    p = os.path.join(d.still, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_a_scribe_that_breaks_the_shape_is_recorded_with_candidate_and_reply(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    prose = "Sure! Here is the memory you asked for, in plain prose with no fields."
    script(d, {"deserves to become a permanent memory": SPOT, "You write the final memory": prose})
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert not r.get("drafts")                       # the verdict is unchanged
    rows = _read(d, "rejected.jsonl")
    assert len(rows) == 1
    row = rows[0]
    assert row["candidate"]["topic"] == "archive-mirror"
    assert row["evidence"] and row["evidence"][0]["text"]
    assert row["attempts"][0]["shape"] is True
    assert row["attempts"][0]["surface"] == prose     # the whole answer, not a head
    assert row["source"] == "a.jsonl" and row["at"]


def test_a_floor_violation_is_recorded_with_its_reason(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    bad = SCRIBE.replace("The archive goes on the slow disk.",
                         "The archive goes on the slow disk, 9999 GB of it.")
    script(d, {"deserves to become a permanent memory": SPOT, "You write the final memory": bad})
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert not r.get("drafts")
    rows = _read(d, "rejected.jsonl")
    assert len(rows) == 1 and rows[0]["violations"]
    assert [a["attempt"] for a in rows[0]["attempts"]] == [1, 2]
    # the original reply survives next to the rebuilt surface (labels, preamble, tags)
    for a in rows[0]["attempts"]:
        assert a["raw"] == bad
        assert a["raw"] != a["surface"]


def test_an_extension_floor_violation_keeps_the_raw_reply(tmp_path):
    import time
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    src = tmp_path / "j.jsonl"
    src.write_text("{}\n")
    t = time.mktime((2026, 8, 20, 12, 0, 0, 0, 0, -1))
    os.utime(src, (t, t))
    d._current_source = str(src)
    from tests.test_extend_continue import OLD
    c = {"extends": OLD,"extends_why": "adds",
         "evidence": [{"class": "USER", "text": "move it tonight"}],
         "classes": ["USER"], "kind": "project"}
    raw = "Here you go.\nSECTION: notes\nBODY:\nnew fact, 9999 GB of it\n"
    d.scribe = lambda task, u, max_tokens=0: raw       # type: ignore[method-assign]
    obs: list = []
    assert d._compose_extension(c, observations=obs) is None
    assert obs[0]["raw"] == raw and obs[0]["raw"] != obs[0]["surface"]


def test_a_good_scribe_leaves_no_rejection(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    script(d, {"deserves to become a permanent memory": SPOT, "You write the final memory": SCRIBE})
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert r["drafts"] == ["archive-mirror"]
    assert _read(d, "rejected.jsonl") == []


def test_a_bad_brain_reply_is_recorded_whole_and_the_failure_keeps_its_head(tmp_path):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    long_prose = "I read the material and here is my summary. " * 40   # > 200 chars
    script(d, {"deserves to become a permanent memory": long_prose})
    from distill_kura.distill.sources import Segment
    found, failure = d.spot_checked([Segment("USER", "put the archive on the slow disk")])
    assert found == []
    assert failure["reason"] == "bad_reply" and len(failure["detail"]) <= 200
    rows = _read(d, "bad_replies.jsonl")
    assert len(rows) == 1 and rows[0]["reply"] == long_prose
    assert rows[0]["reply_chars"] == len(long_prose)


def test_an_empty_list_is_not_a_bad_reply(tmp_path):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    script(d, {"deserves to become a permanent memory": "[]"})
    from distill_kura.distill.sources import Segment
    found, failure = d.spot_checked([Segment("USER", "hello")])
    assert found == [] and failure is None
    assert _read(d, "bad_replies.jsonl") == []


def _scribe_down_then_prose(tmp_path, prose):
    """Shelve one candidate (the scribe raises), then let the scribe answer badly."""
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    script(d, {"deserves to become a permanent memory": SPOT})

    def down(task, user, max_tokens=0):
        raise OSError("scribe unreachable")
    d.scribe = down                                  # type: ignore[method-assign]
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert len(d.pending_compose.load()) == 1 and _read(d, "rejected.jsonl") == []
    d.scribe = lambda task, user, max_tokens=0: prose   # type: ignore[method-assign]
    return d


def test_a_shelved_candidate_that_fails_on_retry_is_recorded(tmp_path):
    prose = "Sure! Here is the memory you asked for, in plain prose with no fields."
    d = _scribe_down_then_prose(tmp_path, prose)
    out = d._work_pending()
    assert not out["drafts"] and d.pending_compose.load() == []   # verdict unchanged: dropped
    rows = _read(d, "rejected.jsonl")
    assert len(rows) == 1
    assert rows[0]["candidate"]["topic"] == "archive-mirror" and rows[0]["from_shelf"] is True
    assert rows[0]["evidence"] and rows[0]["attempts"][0]["surface"] == prose


def test_a_frozen_store_gets_no_record(tmp_path):
    from distill_kura.distill.sources import Segment
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    os.makedirs(d.still, exist_ok=True)
    store.write_policy = "frozen"
    long_prose = "I read the material and here is my summary. " * 40
    script(d, {"deserves to become a permanent memory": long_prose})
    found, failure = d.spot_checked([Segment("USER", "put the archive on the slow disk")])
    assert found == [] and failure["reason"] == "bad_reply"     # verdict unchanged
    d._record_rejected("rejected.jsonl", {"x": 1})
    assert _read(d, "bad_replies.jsonl") == [] and _read(d, "rejected.jsonl") == []


def test_a_dry_run_distiller_gets_no_record(tmp_path):
    from distill_kura.distill.sources import Segment
    reg, store = build(tmp_path)
    d = Distiller(reg, store, writes=False)
    os.makedirs(d.still, exist_ok=True)              # `_still` already exists
    script(d, {"deserves to become a permanent memory": "prose " * 60})
    d.spot_checked([Segment("USER", "hello there")])
    d._record_rejected("rejected.jsonl", {"x": 1})
    assert _read(d, "bad_replies.jsonl") == [] and _read(d, "rejected.jsonl") == []


# ── life-meta#1447 PR-B: what the max_items limit cut leaves a record ────────

def _spot_of(topics):
    q = "[USER] put the archive on the slow disk, and remember that"
    return json.dumps([{"topic": t, "kind": "project", "why": f"why {t}", "quotes": [q]}
                       for t in topics])


def _run_with(tmp_path, topics, answers_extra=None, passes=None):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    if passes:
        reg.raw["distill"]["coverage_passes"] = passes
    d = Distiller(reg, store)
    answers = dict(answers_extra or {})
    answers.update({"deserves to become a permanent memory": _spot_of(topics),
                    "You write the final memory": SCRIBE})
    script(d, answers)
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    return d, d.run(chunks=1)


def test_candidates_past_the_limit_are_recorded_with_topic_and_why(tmp_path):
    topics = ["t1", "t2", "t3", "t4", "t5", "t6"]
    d, _ = _run_with(tmp_path, topics)
    rows = _read(d, "cut_at_limit.jsonl")
    assert len(rows) == 1
    assert rows[0]["limit"] == 4 and rows[0]["kept"] == 4 and rows[0]["passes"] == 1
    assert [c["topic"] for c in rows[0]["cut"]] == ["t5", "t6"]
    assert rows[0]["cut"][0]["why"] == "why t5" and "quotes" not in rows[0]["cut"][0]
    m = _read(d, "metrics.jsonl")[-1]
    assert m["cut_at_limit"] == 2 and m["spot_passes"] == 1


def test_the_cut_record_does_not_change_the_batch(tmp_path):
    over, over_r = _run_with(tmp_path / "over", ["t1", "t2", "t3", "t4", "t5", "t6"])
    at, at_r = _run_with(tmp_path / "at", ["t1", "t2", "t3", "t4"])
    for k in ("drafts", "dropped", "covered", "seeds"):
        assert over_r.get(k) == at_r.get(k), k
    assert _read(at, "cut_at_limit.jsonl") == []      # nothing cut, nothing recorded
    assert _read(at, "metrics.jsonl")[-1]["cut_at_limit"] == 0
    from distill_kura.distill.sources import Segment
    segs = [Segment("USER", "put the archive on the slow disk, and remember that")]
    assert [c["topic"] for c in over.spot(segs)] == ["t1", "t2", "t3", "t4"]


def test_the_second_pass_cut_is_recorded_too(tmp_path):
    d, _ = _run_with(tmp_path, ["t1", "t2"], passes=2,
                     answers_extra={"WALKED PAST": _spot_of(["t2", "t3", "t4", "t5", "t6"])})
    rows = _read(d, "cut_at_limit.jsonl")
    assert len(rows) == 1 and rows[0]["passes"] == 2
    assert [c["topic"] for c in rows[0]["cut"]] == ["t5", "t6"]   # t2 is a repeat, not a cut


def test_a_dry_run_records_no_cut(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store, writes=False)
    script(d, {"deserves to become a permanent memory": _spot_of(["a", "b", "c", "d", "e"])})
    from distill_kura.distill.sources import Segment
    assert len(d.spot([Segment("USER", "put the archive on the slow disk")])) == 4
    assert _read(d, "cut_at_limit.jsonl") == []
