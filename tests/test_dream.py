"""`kura dream-propose` (life-meta#1363 PR-2), pinned on a small fixture: a stale and a
wrong score become proposals in the fixed line shape with verbatim evidence — both as
`supersede` (a new memory plus "retire the old"), and `annotate` only when the case has
no answer; a score
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
from distill_kura.store import Store, write_slug  # noqa: E402

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
    assert stale["slug"] == "market-calendar"
    assert stale["evidence"][0] == {
        "source": "conv-a.jsonl:4",
        "quote": "共有カレンダーもう1個作って、色変えた方が分かりやすいと思う"}
    assert wrong["verdict"] == "wrong"
    assert wrong["evidence"][0]["quote"] == "あれ何回も言ってますけど、カタクルで。お願いします"


def test_stale_becomes_a_new_memory_that_supersedes_the_old(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    propose(st, scores, utter, cases, "2026-11-08")
    p = {r["case_id"]: r for r in rows(st)}["d12"]
    assert p["kind"] == "supersede"
    assert set(p["proposed"]) == {"new_memory", "retire_old", "why"}
    new = p["proposed"]["new_memory"]
    assert new["slug"] == "market-calendar-2026-11-08-d12"
    assert new["title"] == "市場用に別カレンダーを作る"
    assert new["body"].startswith("正: 市場用に別カレンダーを作る。")
    assert "共有カレンダーもう1個作って、色変えた方が分かりやすいと思う" in new["body"]
    assert "conv-a.jsonl:4" in new["body"] and "d12" in new["body"]
    assert p["proposed"]["retire_old"] == "market-calendar"
    assert "市場の予定は営業カレンダーに入れる。" in p["proposed"]["why"]  # where it differs
    assert "10/8 の別カレンダーが無い" in p["proposed"]["why"]
    # the old memory itself is untouched: no in-place rewrite is proposed or made
    assert "営業カレンダーに入れる" in st.read_exact("market-calendar")


def test_wrong_becomes_a_new_memory_that_supersedes_the_old(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    propose(st, scores, utter, cases, "2026-11-08")
    p = {r["case_id"]: r for r in rows(st)}["o03"]
    assert p["kind"] == "supersede"
    assert p["proposed"]["new_memory"]["slug"] == "labor-cost-2026-11-08-o03"
    assert p["proposed"]["new_memory"]["title"] == "カタクル"
    assert "あれ何回も言ってますけど、カタクルで。お願いします" in p["proposed"]["new_memory"]["body"]
    assert p["proposed"]["retire_old"] == "labor-cost"
    assert "息子のバイト代は賀陽住研の人件費。" in p["proposed"]["why"]


def test_no_answer_but_a_quote_is_annotate(tmp_path):
    st, scores, _, utter = fixture(tmp_path)
    cases = jl(tmp_path / "cases3.jsonl", [
        {"id": "o03", "traps": ["賀陽住研"],
         "quote": ["あれ何回も言ってますけど、カタクルで"]}])
    propose(st, scores, utter, cases, "2026-11-08")
    p = {r["case_id"]: r for r in rows(st)}["o03"]
    assert p["kind"] == "annotate"
    assert set(p["proposed"]) == {"note", "quote"}
    assert "息子のバイト代は賀陽住研の人件費。" in p["proposed"]["note"]
    assert "あれ何回も言ってますけど、カタクルで。お願いします" in p["proposed"]["quote"]
    assert "conv-b.jsonl:9" in p["proposed"]["quote"]


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


def test_a_store_swapped_for_a_symlink_gets_no_proposals_file(tmp_path, monkeypatch):
    """Codex P2 on distill-kura#8: a Store opened on `scratch`, then `scratch` swapped
    for a symlink to another (frozen) store's directory. The policy on the object is
    still scratch's, so the frozen check alone let one slug-less wrong score write
    `_still/` and its lock into the other store. Refused like every other write door
    (`_substitution_refusal`), before any directory or lock is made."""
    import pytest
    (tmp_path / "frozen").mkdir()
    (tmp_path / "scratch").mkdir()
    st = Store(name="scratch", path=str(tmp_path / "scratch"))
    os.rmdir(tmp_path / "scratch")
    try:
        os.symlink(tmp_path / "frozen", tmp_path / "scratch", target_is_directory=True)
    except (OSError, NotImplementedError) as e:
        # Windows without Developer Mode / SeCreateSymbolicLinkPrivilege: a directory
        # junction needs no privilege and realpath() follows it the same way.
        try:
            import _winapi
            _winapi.CreateJunction(str(tmp_path / "frozen"), str(tmp_path / "scratch"))
        except (ImportError, OSError, AttributeError):
            pytest.skip(f"os.symlink is not permitted here and no junction either: {e}")
    scores = jl(tmp_path / "scores.jsonl", [{"id": "w1", "verdict": "wrong"}])
    utter = jl(tmp_path / "utter.jsonl", [])
    with pytest.raises(ValueError, match="no longer resolves"):
        propose(st, scores, utter, None, "2026-11-08")
    # the CLI door: the same refusal, a non-zero exit
    from distill_kura import cli
    monkeypatch.setattr(cli, "_store", lambda reg, sel: st)
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f'[stores.m]\npath = "{(tmp_path / "frozen").as_posix()}"\n',
                   encoding="utf-8")
    with pytest.raises(SystemExit) as ex:
        main(["-c", str(cfg), "-s", "m", "dream-propose", "--scores", scores,
              "--utter", utter])
    assert ex.value.code not in (0, None) and "no longer resolves" in str(ex.value.code)
    assert os.listdir(tmp_path / "frozen") == []      # no _still, no lock, no tmp


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


def test_two_cases_on_one_memory_get_different_successor_slugs(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    scores = jl(tmp_path / "s2.jsonl", [
        {"id": "o05", "type": "overturn", "verdict": "wrong", "slugs": ["labor-cost"]},
        {"id": "o06", "type": "overturn", "verdict": "stale", "slugs": ["labor-cost"]}])
    cases = jl(tmp_path / "c2.jsonl", [
        {"id": i, "traps": ["賀陽住研"], "answer": "カタクル",
         "quote": ["あれ何回も言ってますけど、カタクルで"]} for i in ("o05", "o06")])
    propose(st, scores, utter, cases, "2026-11-08")
    slugs = [r["proposed"]["new_memory"]["slug"] for r in rows(st)]
    assert slugs == ["labor-cost-2026-11-08-o05", "labor-cost-2026-11-08-o06"]


def test_successor_slug_that_exists_gets_a_numeric_suffix(tmp_path):
    st, scores, cases, utter = fixture(tmp_path)
    st.remember("labor-cost-2026-11-08-o03", "既存", "既にある記憶")
    propose(st, scores, utter, cases, "2026-11-08")
    p = {r["case_id"]: r for r in rows(st)}["o03"]
    assert p["proposed"]["new_memory"]["slug"] == "labor-cost-2026-11-08-o03-2"


def _one_case(tmp_path, cid, tag):
    scores = jl(tmp_path / f"s-{tag}.jsonl", [
        {"id": cid, "type": "overturn", "verdict": "wrong", "slugs": ["labor-cost"]}])
    cases = jl(tmp_path / f"c-{tag}.jsonl", [
        {"id": cid, "traps": ["賀陽住研"], "answer": f"カタクル（{cid}）",
         "quote": ["あれ何回も言ってますけど、カタクルで"]}])
    return scores, cases


def test_successor_left_by_an_earlier_run_is_reserved(tmp_path):
    """Codex P2 on distill-kura#8: `case_1` and `Case-1` are one name after
    `write_slug`. Run in two separate runs, the second used to start from an empty
    `taken` and propose the same successor again — two pending lines, applying both
    overwrites the first. The name on file is reserved now, so the second gets -2."""
    st, _, _, utter = fixture(tmp_path)
    s1, c1 = _one_case(tmp_path, "case_1", "a")
    s2, c2 = _one_case(tmp_path, "Case-1", "b")
    propose(st, s1, utter, c1, "2026-11-08")
    propose(st, s2, utter, c2, "2026-11-08")
    got = {r["case_id"]: r["proposed"]["new_memory"]["slug"] for r in rows(st)}
    assert got == {"case_1": "labor-cost-2026-11-08-case-1",
                   "Case-1": "labor-cost-2026-11-08-case-1-2"}
    assert len(rows(st)) == 2


def test_rerunning_one_case_keeps_its_successor_name(tmp_path):
    """The pending line a run replaces is the same proposal, updated: its successor name
    is not reserved against itself, so a rerun neither grows the file nor renames it."""
    st, scores, cases, utter = fixture(tmp_path)
    propose(st, scores, utter, cases, "2026-11-08")
    first = {r["case_id"]: r["proposed"]["new_memory"]["slug"]
             for r in rows(st) if r["kind"] == "supersede"}
    n = len(rows(st))
    propose(st, scores, utter, cases, "2026-11-08")
    again = {r["case_id"]: r["proposed"]["new_memory"]["slug"]
             for r in rows(st) if r["kind"] == "supersede"}
    assert again == first == {"d12": "market-calendar-2026-11-08-d12",
                              "o03": "labor-cost-2026-11-08-o03"}
    assert len(rows(st)) == n


def _study_case(tmp_path, old_name):
    """A long-form `_study/<old_name>` memory and one wrong case on it."""
    st, _, _, utter = fixture(tmp_path)
    d = tmp_path / "m" / "_study"
    d.mkdir(exist_ok=True)
    (d / f"{old_name}.md").write_text(
        "---\nname: old\ndescription: 人件費の古い記録\n---\n息子のバイト代は賀陽住研の人件費。\n",
        encoding="utf-8")
    old = f"_study/{old_name}"
    assert st.read_exact(old)
    scores = jl(tmp_path / "s3.jsonl", [
        {"id": "C1", "type": "overturn", "verdict": "wrong", "slugs": [old]}])
    cases = jl(tmp_path / "c3.jsonl", [
        {"id": "C1", "traps": ["賀陽住研"], "answer": "カタクル",
         "quote": ["あれ何回も言ってますけど、カタクルで"]}])
    propose(st, scores, utter, cases, "2026-11-08")
    (p,) = [r for r in rows(st) if r["case_id"] == "C1"]
    return st, old, p


def _applies_as_proposed(st, p, old):
    new = p["proposed"]["new_memory"]["slug"]
    # the name `kura remember` will store it under is the name proposed …
    assert write_slug(new) == new
    st.remember(new, "後継", p["proposed"]["new_memory"]["body"])
    # … so `kura retire` finds both the new memory and the old one by the proposed names
    assert st.resolve_exact(new) == new
    assert p["proposed"]["retire_old"] == old
    assert st.resolve_exact(old) == old
    return new


def test_study_memory_successor_is_the_name_the_store_writes(tmp_path):
    st, old, p = _study_case(tmp_path, "old")
    assert p["kind"] == "supersede"
    assert _applies_as_proposed(st, p, old) == "study-old-2026-11-08-c1"


def test_successor_of_a_name_with_capitals_and_spaces_is_normalised_too(tmp_path):
    st, old, p = _study_case(tmp_path, "Old Note")
    assert _applies_as_proposed(st, p, old) == "study-old-note-2026-11-08-c1"


def test_successor_collision_is_judged_on_the_normalised_name(tmp_path):
    st, old, _ = _study_case(tmp_path, "old")
    st.remember("study-old-2026-11-08-c1", "既存", "既にある記憶")
    scores = jl(tmp_path / "s4.jsonl", [
        {"id": "C1", "type": "overturn", "verdict": "wrong", "slugs": [old]}])
    cases = jl(tmp_path / "c4.jsonl", [
        {"id": "C1", "traps": ["賀陽住研"], "answer": "カタクル",
         "quote": ["あれ何回も言ってますけど、カタクルで"]}])
    propose(st, scores, str(tmp_path / "utter.jsonl"), cases, "2026-11-08")
    (p,) = [r for r in rows(st) if r["case_id"] == "C1"]
    assert p["proposed"]["new_memory"]["slug"] == "study-old-2026-11-08-c1-2"
