"""life-meta#1447 PR-C: a sentence the scribe cannot fix does not sink its memory.

The brain's curation sentences (belongs_because / keep / may_fade) used to ride in the
surface the floor reads even though the scribe can never edit them, so one unbacked
number there failed both attempts. Now the scribe's line is the only one for a key it
wrote; a key it left out takes the brain's sentence only if that sentence passes the
same floor alone, and is left empty otherwise.

Written adversarially: what must still NOT get through is any stored sentence the floor
did not read, and any unbacked claim in the scribe's OWN sentences.
"""
from __future__ import annotations

import glob
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distill_kura.distill import Distiller                    # noqa: E402
from distill_kura.store import ANNOTATION_KEYS                 # noqa: E402
from tests.test_extend_continue import (                      # noqa: E402
    LINES, SCRIBE, SPOT, build, journal, script)

BARE = SCRIBE.replace("KEEP: どのディスクか\n", "")          # the scribe wrote no sentences
BAD = {"keep": "9999 GB のディスク",                          # unbacked number
       "may_fade": "「ぜんぶ消してしまえと言った」",            # invented quotation
       "belongs_because": "[[no-such-memory]] の続きだから"}   # dead link
GOOD = {"keep": "どのディスクか", "may_fade": "細かい容量",
        "belongs_because": "保存先の判断を残す場所だから"}


def _cand(**ann):
    c = json.loads(SPOT)[0]
    for k in ANNOTATION_KEYS:
        c.pop(k, None)
    c.update(ann)
    c.update({"evidence": [{"class": "USER", "text": LINES[0][1]}], "classes": ["USER"]})
    return c


def _compose(tmp_path, c, scribe):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    script(d, {"You write the final memory": scribe})
    obs: list = []
    return d.compose(c, {"walked": []}, [], obs), obs


def _read(d, name):
    p = os.path.join(d.still, name)
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def test_an_unbacked_number_in_the_writers_own_sentence_still_fails(tmp_path):
    bad = SCRIBE.replace("KEEP: どのディスクか", "KEEP: 9999 GB のディスク")
    out, obs = _compose(tmp_path, _cand(**GOOD), bad)
    assert out is None
    assert [o["attempt"] for o in obs] == [1, 2] and all(o["violations"] for o in obs)
    assert all(x["from"] == ["writer:keep"] for o in obs for x in o["origins"])


def test_the_writers_sentence_cannot_hide_behind_a_clean_brain_sentence(tmp_path):
    # the brain's keep is clean; the scribe's is not — the scribe's is what is read
    bad = SCRIBE.replace("KEEP: どのディスクか", "KEEP: 9999 GB のディスク")
    out, _ = _compose(tmp_path, _cand(keep="どのディスクか"), bad)
    assert out is None


def test_a_bad_brain_sentence_is_not_stored_and_the_memory_passes(tmp_path):
    out, obs = _compose(tmp_path, _cand(keep=BAD["keep"]), BARE)
    assert out is not None and out["slug"] == "archive-mirror"
    assert "keep" not in out["annotations"]
    assert "9999" not in json.dumps(out["annotations"]) and "9999" not in out["body"]
    assert list(out["annotations_dropped"]) == ["keep"]
    assert out["annotations_dropped"]["keep"]          # and why
    assert len(obs) == 1                               # no retry was spent on it
    assert "9999" not in obs[0]["surface"]


def test_each_kind_of_violation_in_a_brain_sentence_is_dropped_per_key(tmp_path):
    out, _ = _compose(tmp_path, _cand(**BAD), BARE)
    assert out is not None and out["annotations"] == {}
    assert set(out["annotations_dropped"]) == set(ANNOTATION_KEYS)
    # one bad key does not take the clean ones with it
    out, _ = _compose(tmp_path / "mixed", _cand(keep=GOOD["keep"], may_fade=BAD["may_fade"]),
                      BARE)
    assert out["annotations"] == {"keep": GOOD["keep"]}
    assert list(out["annotations_dropped"]) == ["may_fade"]


def test_the_writers_line_replaces_the_brains_for_its_key_unread(tmp_path):
    out, obs = _compose(tmp_path, _cand(keep=BAD["keep"]), SCRIBE)
    assert out["annotations"] == {"keep": "どのディスクか"}
    assert "annotations_dropped" not in out           # superseded, not refused
    assert "9999" not in obs[-1]["surface"]


def test_nothing_stored_escapes_the_floor(tmp_path):
    """Every combination of brain sentence (absent / clean / bad) and scribe line
    (absent / present): whatever ends up in `annotations` was inside the surface the
    whole floor passed, on the attempt that produced the memory."""
    n = 0
    for i, (brain, scribe) in enumerate(itertools.product(
            [{}, GOOD, BAD, {"keep": GOOD["keep"], "may_fade": BAD["may_fade"]}],
            [BARE, SCRIBE])):
        out, obs = _compose(tmp_path / str(i), _cand(**brain), scribe)
        assert out is not None
        assert obs[-1]["violations"] == []
        for k, v in out["annotations"].items():
            assert v in obs[-1]["surface"], (k, v)
            assert v not in BAD.values(), (k, v)
        n += 1
    assert n == 8


def test_end_to_end_the_draft_and_manifest_carry_no_bad_sentence(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    spot = json.loads(SPOT)
    spot[0]["keep"] = BAD["keep"]
    script(d, {"deserves to become a permanent memory": json.dumps(spot, ensure_ascii=False),
               "You write the final memory": BARE})
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert r["drafts"] == ["archive-mirror"]
    assert _read(d, "rejected.jsonl") == []
    draft = open(glob.glob(os.path.join(d.drafts_dir, "*.md"))[0], encoding="utf-8").read()
    assert "9999" not in draft and "KEEP:" not in draft
    mans = [json.load(open(p, encoding="utf-8"))
            for p in glob.glob(os.path.join(d._evidence_dir(), "*.json"))]
    assert len(mans) == 1
    assert "keep" not in mans[0]["annotations"]
    assert list(mans[0]["annotations_dropped"]) == ["keep"]


def test_a_memory_that_dropped_nothing_keeps_the_old_manifest_shape(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    script(d, {"deserves to become a permanent memory": SPOT,
               "You write the final memory": SCRIBE})
    d.novelty = lambda c, near: ("NEW", "", None)   # type: ignore[method-assign]
    assert d.run(chunks=1)["drafts"] == ["archive-mirror"]
    for p in glob.glob(os.path.join(d._evidence_dir(), "*.json")):
        assert "annotations_dropped" not in json.load(open(p, encoding="utf-8"))
