"""`kura dream-propose` (life-meta#1363 PR-2), pinned on a small fixture: a stale and a
wrong score become proposals in the fixed line shape with verbatim evidence; a score
whose quote is nowhere in the utterance index becomes `needs-human`; running twice
does not grow the file; a line a person moved off `pending` survives; and nothing but
`_still/dream-proposals.jsonl` is written. No model, no network.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distill_kura.cli import main          # noqa: E402
from distill_kura import dream             # noqa: E402
from distill_kura.dream import propose     # noqa: E402
from distill_kura.store import Store       # noqa: E402

KEYS = {"date", "case_id", "verdict", "slug", "kind", "proposed", "evidence", "status"}


def jl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")
    return str(path)


def fixture(tmp_path):
    st = Store(name="m", path=str(tmp_path / "m"))
    st.init_files()
    st.remember("market-calendar", "市場の予定の置き場",
                "市場の予定は営業カレンダーに入れる。\n裁定日: 2026-09-01")
    st.remember("labor-cost", "人件費の振り分け",
                "息子のバイト代は賀陽住研の人件費。\n裁定日: 2026-09-11")
    scores = jl(tmp_path / "scores.jsonl", [
        {"id": "d12", "type": "decision", "verdict": "stale",
         "slugs": ["market-calendar"], "note": "10/8 の別カレンダーが無い"},
        {"id": "o03", "type": "overturn", "verdict": "wrong", "slugs": ["labor-cost"]},
        {"id": "x01", "type": "number", "verdict": "stale", "slugs": ["labor-cost"]},
        {"id": "c01", "type": "decision", "verdict": "correct", "slugs": ["labor-cost"]},
    ])
    cases = jl(tmp_path / "cases.jsonl", [
        {"id": "d12", "traps": ["営業カレンダー"], "answer": "市場用に別カレンダーを作る",
         "quote": ["共有カレンダーもう1個作って、色変えた方が分かりやすい"]},
        {"id": "o03", "traps": ["賀陽住研"], "answer": "カタクル",
         "quote": ["あれ何回も言ってますけど、カタクルで"]},
        {"id": "x01", "traps": ["x"], "answer": "y", "quote": ["どこにも無い発言です"]},
    ])
    utter = jl(tmp_path / "utter.jsonl", [
        {"ts": "2026-10-08T09:00:00Z", "file": "conv-a.jsonl", "line": 4,
         "text": "前置き\n共有カレンダーもう1個作って、色変えた方が分かりやすいと思う\n後ろ"},
        {"ts": "2026-09-22T01:00:00Z", "file": "conv-b.jsonl", "line": 9,
         "text": "あれ何回も言ってますけど、カタクルで。お願いします"},
    ])
    return st, scores, cases, utter


def rows(st):
    with open(os.path.join(st.still, "dream-proposals.jsonl"), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def test_proposals_take_the_fixed_shape_with_verbatim_evidence(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    r = propose(st, scores, utter, cases, "2026-11-08")
    assert r["scored"] == 3 and r["written"] == 3        # `correct` is not proposed for
    got = {p["case_id"]: p for p in rows(st)}
    stale, wrong = got["d12"], got["o03"]
    for p in (stale, wrong):
        assert set(p) == KEYS and p["status"] == "pending" and p["date"] == "2026-11-08"
        assert p["evidence"] and set(p["evidence"][0]) == {"source", "quote"}
    assert stale["kind"] == "annotate" and stale["slug"] == "market-calendar"
    assert stale["evidence"][0] == {
        "source": "conv-a.jsonl:4",
        "quote": "共有カレンダーもう1個作って、色変えた方が分かりやすいと思う"}
    assert "市場用に別カレンダーを作る" in stale["proposed"]
    assert "市場の予定は営業カレンダーに入れる。" in stale["proposed"]  # where it differs
    assert wrong["kind"] == "replace" and wrong["verdict"] == "wrong"
    assert wrong["evidence"][0]["quote"] == "あれ何回も言ってますけど、カタクルで。お願いします"


def test_no_evidence_is_needs_human_with_a_reason_only(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    propose(st, scores, utter, cases, "2026-11-08")
    h = {p["case_id"]: p for p in rows(st)}["x01"]
    assert h["kind"] == "needs-human" and h["reason"] and h["status"] == "pending"
    assert "proposed" not in h and "evidence" not in h


def test_missing_memory_or_case_is_needs_human(tmp_path):
    st, _, _, utter = fixture(tmp_path)
    scores = jl(tmp_path / "s2.jsonl", [
        {"id": "d12", "type": "decision", "verdict": "stale", "slugs": ["gone"]},
        {"id": "o03", "type": "overturn", "verdict": "wrong", "slugs": ["labor-cost"]},
        {"id": "z", "type": "decision", "verdict": "wrong", "slugs": []},
    ])
    propose(st, scores, utter, None, "2026-11-08")       # no --cases: nothing to quote
    assert {p["kind"] for p in rows(st)} == {"needs-human"}
    assert len(rows(st)) == 3


def test_twice_does_not_grow_and_decided_lines_survive(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    propose(st, scores, utter, cases, "2026-11-07")
    first = rows(st)
    first[0]["status"] = "accepted"                     # a person decided this one
    jl(tmp_path / "m" / "_still" / "dream-proposals.jsonl", first)
    propose(st, scores, utter, cases, "2026-11-08")
    again = rows(st)
    assert len(again) == 4                              # 3 pending + the accepted one
    assert sum(p["status"] == "pending" for p in again) == 3
    assert all(p["date"] == "2026-11-08" for p in again if p["status"] == "pending")
    propose(st, scores, utter, cases, "2026-11-08")
    assert len(rows(st)) == 4


def test_only_the_proposals_file_is_written(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)

    def snapshot():
        out = {}
        for root, _, files in os.walk(st.path):
            for f in files:
                p = os.path.join(root, f)
                out[p] = open(p, "rb").read()
        return out
    before = snapshot()
    propose(st, scores, utter, cases, "2026-11-08")
    after = snapshot()
    changed = {p for p in after if before.get(p) != after[p]} | (set(before) - set(after))
    assert changed == {os.path.join(st.still, "dream-proposals.jsonl"),
                       os.path.join(st.still, "dream-proposals.lock")}


def test_cli_exit_codes(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f"""
[stores.m]
path = "{(tmp_path / 'm').as_posix()}"
[models.thinker]
url = "http://127.0.0.1:9/v1"
model = "none"
""", encoding="utf-8")
    base = ["-c", str(cfg), "-s", "m", "dream-propose", "--utter", utter, "--cases", cases]
    assert main(base + ["--scores", scores, "--date", "2026-11-08"]) == 0
    empty = jl(tmp_path / "none.jsonl", [{"id": "c", "verdict": "correct", "slugs": []}])
    assert main(base + ["--scores", empty]) == 2


def test_frozen_store_gets_no_proposals_file(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    st.write_policy = "frozen"
    still = os.path.join(st.path, "_still")
    had = os.path.exists(still)
    import pytest
    with pytest.raises(ValueError, match="frozen"):
        propose(st, scores, utter, cases, "2026-11-08")
    assert os.path.exists(still) == had
    assert not os.path.exists(os.path.join(st.still, "dream-proposals.jsonl"))
    assert not os.path.exists(os.path.join(st.still, "dream-proposals.jsonl.tmp"))


def test_long_quote_is_kept_whole(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    long_q = "一行目の言葉です\n二行目の言葉です\n三行目の言葉です\n四行目の言葉です"
    cases = jl(tmp_path / "cases2.jsonl", [
        {"id": "d12", "traps": ["営業カレンダー"], "answer": "別", "quote": [long_q]}])
    utter = jl(tmp_path / "utter2.jsonl", [
        {"ts": "2026-10-08T09:00:00Z", "file": "c.jsonl", "line": 1, "text": "前\n" + long_q + "\n後"}])
    propose(st, scores, utter, cases, "2026-11-08")
    ev = [r for r in rows(st) if r["case_id"] == "d12"][0]["evidence"][0]["quote"]
    assert ev == long_q


def test_proposals_are_read_and_written_inside_the_store_lock(tmp_path, monkeypatch):
    import contextlib
    st, scores, cases, utter = fixture(tmp_path)
    log = []

    @contextlib.contextmanager
    def fake_lock(still):
        log.append("enter")
        try:
            yield
        finally:
            log.append("exit")
    monkeypatch.setattr(dream, "_locked", fake_lock)
    real_read, real_replace = dream._read_jsonl, os.replace
    monkeypatch.setattr(dream, "_read_jsonl",
                        lambda p: (log.append("read:" + os.path.basename(p)), real_read(p))[1])
    monkeypatch.setattr(dream.os, "replace",
                        lambda a, b: (log.append("replace"), real_replace(a, b))[1])
    propose(st, scores, utter, cases, "2026-11-08")
    propose(st, scores, utter, cases, "2026-11-09")
    second = log[len(log) - 1 - log[::-1].index("enter"):]
    assert second[0] == "enter" and second[-1] == "exit"
    assert "read:dream-proposals.jsonl" in second and "replace" in second
    assert second.index("read:dream-proposals.jsonl") < second.index("replace") < len(second) - 1
