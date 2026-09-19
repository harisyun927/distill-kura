"""The verified transition relation — proposed ≠ proven.

Every test is named for the failure it prevents. The relation is pure and knows
nothing about the model's proposal on purpose: what writes `現在は [[new]]` into
canonical is an exact whole-line match of the one closed template
(`distill_kura.distill.transition.template`), or nothing. Free text — however
plausible, however explicit it reads to a person — is never proof of a direction
(round A′, 2026-09-19); it can still be reference information (`retired-only`).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distill_kura.distill.transition import (                     # noqa: E402
    find_transition, parse_instruction,
)


def _t(text, old=("old-way", "the old way"), new=("new-way", "the new way"), topic=""):
    return find_transition([{"class": "USER", "text": text}],
                           {"slug": old[0], "title": old[1]},
                           {"slug": new[0], "title": new[1], "topic": topic})


def test_a_by_the_way_clause_never_supplies_the_successor():
    """The whole defect in one line: "old-way はやめよう。ところで別件で GPU 温度…"
    must never make the GPU memory old-way's successor."""
    r = _t("old-way はもうやめよう。ところで別件で GPU 温度の記録を取ろう",
           new=("gpu-temperature", "GPU 温度の記録"))
    assert r is not None and r["kind"] == "retired-only" and r["new"] is None


def test_naming_both_memories_without_a_construction_proves_nothing():
    """Two names in one sentence is a mention, not a ruling."""
    assert _t("old-way と new-way はどちらもよく使う") is None
    assert _t("old-way and new-way are both fine") is None


def test_a_transition_is_never_stitched_across_two_quotes():
    r = find_transition([{"class": "USER", "text": "old-way はもうやめる"},
                         {"class": "USER", "text": "今後は new-way で行く"}],
                        {"slug": "old-way", "title": "the old way"},
                        {"slug": "new-way", "title": "the new way"})
    assert r is not None and r["kind"] == "retired-only"


def test_only_user_class_evidence_can_prove_a_transition():
    ev = [{"class": c, "text": "old-way はやめて、new-way に統合する。"}
          for c in ("TOOL", "SELF", "ACT")]
    assert find_transition(ev, {"slug": "old-way", "title": "the old way"},
                           {"slug": "new-way", "title": "the new way"}) is None


def test_a_paraphrase_of_the_old_memory_is_not_its_name():
    """Exact slug or exact index title only — a model's paraphrase cannot retire."""
    assert _t("the way we used to do it is over, now use new-way") is None


# ── free text alone never proves succession any more (round A′) ────────────────────
# Every one of these fooled the old construction-table reading in some review round.
# None of them may come back `superseded`; at most they are `retired-only`.

@pytest.mark.parametrize("text", [
    "old-way はやめて、今後は new-way で行く",
    "old-way に代えて new-way を使う",
    "old-way → new-way",
    "we replaced old-way with new-way",
    "stop using old-way, now use new-way",
    "switch to new-way, old-way is done",
    "old-way は終わり。the new way が後継になる。",   # title-word successor
])
def test_free_text_alone_never_proves_succession(text):
    r = _t(text)
    assert r is None or r["kind"] != "superseded", text


# ── the closed template: positive cases ─────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "old-way はやめて、new-way に統合する。",
    "old-way は退役して、new-way に置き換える。",
    "old-way はやめて、new-way に置き換える。",
    "old-way は退役して、new-way に統合する。",
    "old-way はやめて、new-way に統合する",            # the closing 。 is optional
])
def test_the_closed_template_proves_succession(text):
    r = _t(text)
    assert r and r["kind"] == "superseded" and r["old"] == "old-way" \
        and r["new"] == "new-way", text
    assert r["quote"] == text


def test_the_template_with_a_reason_sentence_proves_succession():
    text = "old-way は用途消失で役目終わり。退役して、new-way に置き換える。"
    r = _t(text)
    assert r and r["kind"] == "superseded" and r["new"] == "new-way"


# ── the closed template: negative cases ─────────────────────────────────────────────

def test_swapped_slugs_prove_only_the_reverse():
    text = "old-way はやめて、new-way に統合する。"
    forward = _t(text)
    assert forward and forward["kind"] == "superseded" and forward["new"] == "new-way"
    reverse = find_transition([{"class": "USER", "text": text}],
                              {"slug": "new-way", "title": "the new way"},
                              {"slug": "old-way", "title": "the old way"})
    assert reverse is None or reverse["kind"] != "superseded"


def test_a_store_slug_that_folds_to_the_same_spelling_makes_the_slot_ambiguous():
    # The pour path and `Store.retire` hand `find_transition` only the (old, new)
    # pair; the store may still hold `Old` beside `old`. With the store's slugs
    # passed as `known`, the slot names both — i.e. neither exactly — and is refused
    # for either spelling. Without a collision the same call still proves.
    text = "Old はやめて、new-way に統合する。"
    for old in ("old", "Old"):
        r = find_transition([{"class": "USER", "text": text}],
                            {"slug": old, "title": ""}, {"slug": "new-way", "title": ""},
                            known={"Old", "old", "new-way", "third"})
        assert r is None or r["kind"] != "superseded"
    r = find_transition([{"class": "USER", "text": text}],
                        {"slug": "Old", "title": ""}, {"slug": "new-way", "title": ""},
                        known={"Old", "new-way", "third"})
    assert r and r["kind"] == "superseded" and r["old"] == "Old"


def test_a_title_in_place_of_a_slug_does_not_prove():
    r = _t("the old way はやめて、new-way に統合する。")
    assert r is None or r["kind"] != "superseded"


def test_the_template_embedded_in_a_longer_line_does_not_prove():
    r = _t("念のため old-way はやめて、new-way に統合する。")
    assert r is None or r["kind"] != "superseded"


# ── the closed ENGLISH template (PR-A, 2026-09-19) ──────────────────────────────────

@pytest.mark.parametrize("text", [
    "retire old-way, replaced by new-way.",
    "retire old-way, replaced by new-way",          # trailing . optional
    "Retire Old-Way, Replaced By New-Way.",          # _norm folds case before matching
])
def test_the_closed_english_template_proves_succession(text):
    r = _t(text)
    assert r and r["kind"] == "superseded" and r["old"] == "old-way" \
        and r["new"] == "new-way", text


def test_the_closed_english_template_does_not_prove_the_reverse():
    text = "retire old-way, replaced by new-way."
    forward = _t(text)
    assert forward and forward["kind"] == "superseded"
    reverse = find_transition([{"class": "USER", "text": text}],
                              {"slug": "new-way", "title": "the new way"},
                              {"slug": "old-way", "title": "the old way"})
    assert reverse is None or reverse["kind"] != "superseded"


@pytest.mark.parametrize("text", [
    "retire the old-way, replaced by new-way.",
    "old-way is retired, replaced by new-way.",
    "retire old-way, replaced by new-way and third.",
    "retire old-way replaced by new-way.",
    "retire old-way, not replaced by new-way.",
    "please retire old-way, replaced by new-way.",
    "retire old-way, replaced by new-way. thanks",
    "retire old-way, superseded by new-way.",
])
def test_english_free_text_and_variants_never_prove_succession(text):
    r = _t(text)
    assert r is None or r["kind"] != "superseded", text


def test_an_english_name_collision_makes_the_slot_ambiguous():
    text = "retire Old, replaced by new-way."
    r = find_transition([{"class": "USER", "text": text}],
                        {"slug": "Old", "title": ""}, {"slug": "new-way", "title": ""},
                        known={"Old", "old", "new-way"})
    assert r is None or r["kind"] != "superseded"


def test_two_lines_each_prove_their_own_pair_japanese_and_english():
    quote = ("old-way はやめて、new-way に統合する。\n"
             "retire third-thing, replaced by fourth-thing.")
    r1 = find_transition([{"class": "USER", "text": quote}],
                         {"slug": "old-way", "title": "the old way"},
                         {"slug": "new-way", "title": "the new way"})
    assert r1 and r1["kind"] == "superseded" and r1["new"] == "new-way"
    r2 = find_transition([{"class": "USER", "text": quote}],
                         {"slug": "third-thing", "title": "Third thing"},
                         {"slug": "fourth-thing", "title": "Fourth thing"})
    assert r2 and r2["kind"] == "superseded" and r2["new"] == "fourth-thing"


def test_two_lines_each_prove_their_own_pair():
    quote = ("old-way はやめて、new-way に統合する。\n"
             "third-thing は退役して、fourth-thing に置き換える。")
    r1 = find_transition([{"class": "USER", "text": quote}],
                         {"slug": "old-way", "title": "the old way"},
                         {"slug": "new-way", "title": "the new way"})
    assert r1 and r1["kind"] == "superseded" and r1["new"] == "new-way"
    r2 = find_transition([{"class": "USER", "text": quote}],
                         {"slug": "third-thing", "title": "Third thing"},
                         {"slug": "fourth-thing", "title": "Fourth thing"})
    assert r2 and r2["kind"] == "superseded" and r2["new"] == "fourth-thing"


# ── a decomposition that is not unique proves nothing (Codex P2, transition.py:114) ─
# When the store's OWN slugs are built out of other slugs, the closed English
# template's alternation can read one line two ways: `retire a, replaced by b,
# replaced by c.` is both (old=a, new="b, replaced by c") and
# (old="a, replaced by b", new=c). Neither reading may win silently.

def test_an_ambiguous_english_decomposition_proves_neither_reading():
    names = {"a", "a, replaced by b", "b, replaced by c", "c"}
    line = "retire a, replaced by b, replaced by c."
    assert parse_instruction(line, names) is None
    r = find_transition([{"class": "USER", "text": line}],
                        {"slug": "a", "title": ""},
                        {"slug": "b, replaced by c", "title": ""}, known=names)
    assert r is None or r["kind"] != "superseded"


def test_the_same_line_proves_when_the_decomposition_is_unique():
    names = {"a", "b, replaced by c"}
    line = "retire a, replaced by b, replaced by c."
    assert parse_instruction(line, names) == ("a", "b, replaced by c", None)


def test_an_ambiguous_japanese_decomposition_proves_neither_reading():
    names = {"x", "x はやめて、y", "y", "z", "y はやめて、z"}
    line = "x はやめて、y はやめて、z に統合する。"
    assert parse_instruction(line, names) is None
    r = find_transition([{"class": "USER", "text": line}],
                        {"slug": "x", "title": ""},
                        {"slug": "y はやめて、z", "title": ""}, known=names)
    assert r is None or r["kind"] != "superseded"


def test_the_same_japanese_line_proves_when_the_decomposition_is_unique():
    names = {"x", "y はやめて、z"}
    line = "x はやめて、y はやめて、z に統合する。"
    assert parse_instruction(line, names) == ("x", "y はやめて、z", None)
