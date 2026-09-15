"""`extend_mode = "continue"`: an EXTENDS verdict writes a NEW memory that links back.

The shape of the lie in `append` mode: a later journal's EXTENDS appends to a memory
another run already signed, and the pour replaces that memory's curation sentences
and curation mark with the newcomer's — the old memory now says, under the gate's
signature, things its own evidence never did. `continue` leaves the old file alone,
byte for byte, and records the relation as a `continues` edge instead.
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest   # noqa: E402

from distill_kura import edges                                 # noqa: E402
from distill_kura.distill import Distiller                    # noqa: E402
from distill_kura.distill.pipeline import CONTINUE_LINE       # noqa: E402
from distill_kura.registry import Registry                    # noqa: E402
from distill_kura.store import Store                          # noqa: E402
from distill_kura.thinker import Models                       # noqa: E402

OLD = "backup-plan"

LINES = [("user", "put the archive on the slow disk, and remember that"),
         ("tool", "/data 3.2T used 1.1T avail"),
         ("self", "I think we should also mirror it")]

SPOT = json.dumps([{"topic": "archive-mirror", "kind": "project",
                    "why": "where the archive lives",
                    "quotes": ["[USER] put the archive on the slow disk, and remember that"],
                    "tags": ["decision"],
                    "belongs_because": "保存先の判断を残す場所だから",
                    "keep": "どのディスクか", "may_fade": "細かい容量"}])

SCRIBE = ("SLUG: archive-mirror\nTITLE: Archive mirror\n"
          "DESC: the archive lives on the slow disk\n"
          "KEEP: どのディスクか\n"
          "BODY:\nThe archive goes on the slow disk.\n")


def journal(path, lines):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for who, text in lines:
            if who == "user":
                f.write(json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
            elif who == "tool":
                f.write(json.dumps({"type": "user", "message": {"content": [
                    {"type": "tool_result", "content": [{"type": "text", "text": text}]}]}}) + "\n")
            else:
                f.write(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
        f.write(json.dumps({"type": "user", "message": {"content": [{"type": "text", "text": "padding " * 2000}]}}) + "\n")


def build(tmp_path, mode=None):
    store = Store(name="main", path=str(tmp_path / "kura"), label="k", write_policy="distiller-only")
    store.init_files()
    # The memory an EXTENDS would have rewritten: signed curation, a manifest, tags.
    store.pour_verified(OLD, "backups are kept on the NAS", "Backups are kept on the NAS.",
                        meta={"evidence_manifest": "sha256:" + "a" * 64}, tags=["decision"],
                        annotations={"belongs_because": "the old reason", "keep": "the old keep",
                                     "may_fade": "the old detail"})
    models = Models.from_config({"thinker": {"url": "http://127.0.0.1:9/v1", "model": "none"}})
    dist = {"journals": {"claude": str(tmp_path / "journals")}, "language": "日本語"}
    if mode is not None:
        dist["extend_mode"] = mode
    reg = Registry(stores={"main": store}, modes={}, models=models, default="main",
                   raw={"distill": dist})
    return reg, store


def script(dis: Distiller, answers: dict) -> None:
    def pick(task, user, max_tokens=0):
        return next((v for k, v in answers.items() if k in task), "")
    dis.brain = pick          # type: ignore[method-assign]
    dis.scribe = pick         # type: ignore[method-assign]


def old_bytes(store) -> bytes:
    with open(store.file_of(OLD), "rb") as f:
        return f.read()


def a_draft(**kw):
    d = {"slug": "x", "title": "X", "description": "a trigger", "body": "the body",
         "kind": "project", "evidence": [{"class": "USER", "text": "they said so"}],
         "classes": ["USER"], "unverified_numbers": False, "judgement": False}
    d.update(kw)
    return d


# ── continue mode, end to end ────────────────────────────────────────────

def test_continue_mode_writes_a_new_memory_and_leaves_the_old_one_byte_identical(tmp_path):
    journal(str(tmp_path / "journals" / "a.jsonl"), LINES)
    reg, store = build(tmp_path, mode="continue")
    before = old_bytes(store)
    fm_before = store.frontmatter(OLD)
    d = Distiller(reg, store)
    assert d.extend_mode == "continue"
    script(d, {"deserves to become a permanent memory": SPOT,
               "You write the final memory": SCRIBE, "draw the last line": "POUR\nreason: fine"})
    d.novelty = lambda c, near: ("EXTENDS", "adds to it", OLD)   # type: ignore[method-assign]
    r = d.run(chunks=1)
    assert r["drafts"] == ["archive-mirror"]
    draft = open(os.path.join(d.drafts_dir, "archive-mirror.md"), encoding="utf-8").read()
    assert "EXTENDS:" not in draft
    assert d.drain()["poured"] == 1

    assert "archive-mirror" in store.slugs()
    body = store.read_exact("archive-mirror")
    line = next(l for l in body.splitlines() if "[[" in l)
    assert "続き" in line and f"[[{OLD}]]" in line
    assert CONTINUE_LINE.format(target=OLD) in body

    got = [(e["source"], e["target"], e["type"]) for e in edges.derive(store)["edges"]]
    assert ("archive-mirror", OLD, "continues") in got

    # the old memory: body, annotations, curation mark, origin — every byte
    assert old_bytes(store) == before
    assert store.frontmatter(OLD) == fm_before          # origin/evidence manifests unmoved


def test_continue_mode_pour_refuses_an_extends_draft(tmp_path):
    reg, store = build(tmp_path)
    before = old_bytes(store)
    d = Distiller(reg, store)
    p = d.stage(a_draft(slug=OLD, extends=OLD, title="", description="",
                        body="## 2026-09-15\nmore about backups"), "s.jsonl")
    name = os.path.basename(p)[:-3]
    d.extend_mode = "continue"          # the store was switched after this was staged
    r = d.pour(name)
    assert r["ok"] is False and "continue" in r["why"]
    assert old_bytes(store) == before
    assert os.path.exists(p)            # the draft is kept for a person to look at


# ── a new memory never overwrites one the store already holds ────────────

def test_continue_mode_stages_a_colliding_new_memory_under_a_free_name(tmp_path):
    reg, store = build(tmp_path, mode="continue")
    before = old_bytes(store)
    d = Distiller(reg, store)
    p = d.stage(a_draft(slug=OLD, body="a different fact entirely"), "s.jsonl")
    name = os.path.basename(p)[:-3]
    assert name == f"{OLD}-2"
    assert d.pour(name)["ok"] is True
    assert old_bytes(store) == before
    assert "a different fact entirely" in store.read_exact(f"{OLD}-2")


def test_continue_mode_pour_refuses_a_new_memory_draft_whose_name_is_taken(tmp_path):
    reg, store = build(tmp_path)
    before = old_bytes(store)
    d = Distiller(reg, store)
    p = d.stage(a_draft(slug=OLD, body="a different fact entirely"), "s.jsonl")   # append: no rename
    d.extend_mode = "continue"
    r = d.pour(os.path.basename(p)[:-3])
    assert r["ok"] is False and "already exists" in r["why"]
    assert old_bytes(store) == before


# ── append mode stays what it was ────────────────────────────────────────

def test_append_is_the_default_and_routes_extends_into_the_old_memory(tmp_path):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    assert d.extend_mode == "append"
    c = d._route_extends({"topic": "t"}, OLD, "adds")
    assert c["extends"] == OLD and "continues_from" not in c


def test_append_extension_heading_is_always_level_two(tmp_path):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    src = tmp_path / "j.jsonl"; src.write_text("{}\n")
    t = time.mktime((2026, 8, 20, 12, 0, 0, 0, 0, -1)); os.utime(src, (t, t))
    d._current_source = str(src)
    c = {"extends": OLD, "extends_why": "adds", "evidence": [{"class": "USER", "text": "move it tonight"}],
         "classes": ["USER"], "kind": "project"}
    # a SECTION line carrying the date but no `## ` used to become a bare body line
    d.scribe = lambda task, u, max_tokens=0: "SECTION: 2026-08-20 notes\nBODY:\nnew fact\n"   # type: ignore
    assert d._compose_extension(c)["body"].startswith("## 2026-08-20 notes\n")
    d.scribe = lambda task, u, max_tokens=0: "SECTION: ### 2026-08-20 notes\nBODY:\nnew fact\n"   # type: ignore
    assert d._compose_extension(c)["body"].startswith("## 2026-08-20 notes\n")


# ── a verdict that names no neighbour is not a relation ──────────────────

@pytest.mark.parametrize("mode", ["append", "continue"])
def test_an_unnamed_extends_or_covered_is_new_not_the_top_hit(tmp_path, mode):
    """The top recall hit used to stand in for the name the model left off the verdict
    line — so an EXTENDS rewrote, and a COVERED dropped a candidate against, a memory
    nobody chose."""
    reg, store = build(tmp_path, mode=mode)
    d = Distiller(reg, store)
    c = {"topic": "t", "why": "w", "evidence": [{"class": "USER", "text": "x"}]}
    for said in ("EXTENDS", "COVERED\nalready there", "EXTENDS some-other-slug"):
        d.brain = lambda task, u, max_tokens=0, said=said: said   # type: ignore
        verdict, why, target = d.novelty(c, {"walked": [OLD]})
        assert (verdict, target) == ("NEW", None), said
        assert "named no neighbour" in why
    d.brain = lambda task, u, max_tokens=0: f"EXTENDS {OLD}\nadds"   # type: ignore
    assert d.novelty(c, {"walked": [OLD]})[::2] == ("EXTENDS", OLD)


# ── config and prompts ───────────────────────────────────────────────────

def test_an_unknown_extend_mode_is_refused(tmp_path):
    reg, store = build(tmp_path, mode="rewrite")
    with pytest.raises(ValueError, match="extend_mode"):
        Distiller(reg, store)


def test_candidate_prompts_carry_the_store_language(tmp_path):
    reg, store = build(tmp_path)
    d = Distiller(reg, store)
    d.coverage_passes = 2
    tasks = []

    def capture(task, user, max_tokens=0):
        tasks.append(task)
        return "[]"                     # an explicit empty list still asks the coverage pass
    d.brain = capture          # type: ignore[method-assign]
    d.spot_checked([])
    assert len(tasks) == 2
    for task in tasks:                  # SPOT, then COVERAGE
        assert "日本語" in task and "{language}" not in task
