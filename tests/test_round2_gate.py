"""The acceptance gate for Codex review round 2 — written by the reviewer, not the fixer.

This file is the contract. It is NOT yours to edit: if a change you make cannot pass it,
the change is wrong, not the gate. (One exception, stated in the brief: nothing.)

Two halves.

  · The REGRESSION half replays the five real instructions that made this lane exist
    (kura journals/evidence/retire-all5-2026-09-18.evidence.jsonl, copied verbatim).
    All five must still be proven, in the right direction, with nothing skipped. Every
    previous attempt to narrow the direction rule lost one of these silently.

  · The NARROWING half is the four findings of round 2. Each names a way the lane could
    write the map backwards or write where it promised not to.
"""
from types import SimpleNamespace

import pytest

from distill_kura.distill.retire_lane import _write_manifest, proven

# The store the five instructions are talking to. Titles are not what the quotes use —
# every one of them names its memories by slug — so they only have to not collide.
REAL = {
    "pr2-constitution-reset-handoff": "PR2 憲法リセット着手手順",
    "constitution-minimal-core": "憲法の最小核",
    "feedback-branch-update-via-github-ui": "GitHub UI でのブランチ更新",
    "project-lm-inbox-pending": "life-meta inbox の未処理",
    "project-handoff-ingest-pipeline": "handoff 取込パイプライン",
    "playwright-mcp-stale-lock": "Playwright MCP の残留ロック",
    "playwright-profile-lock-not-released-by-window": "プロファイルロックが窓で解放されない",
    "ask-next-flow-first-run": "ask-next の初回",
    "feedback-kanban-ai-facing-ask-next": "看板の AI 向け ask-next",
}

# Verbatim from the evidence journal. Do not reflow, retype or "tidy" these strings:
# the §12.5 in the second one ends a sentence at its decimal point, and that trap has
# already cost this lane one of the five once.
QUOTES = [
    "pr2-constitution-reset-handoff は PR2 完了で役目終わり。退役して、constitution-minimal-core に置き換える。",
    "feedback-branch-update-via-github-ui は §12.5 失効で役目終わり。退役して、constitution-minimal-core に置き換える。",
    "project-lm-inbox-pending は退役して、project-handoff-ingest-pipeline に置き換える。",
    "playwright-mcp-stale-lock はやめて、playwright-profile-lock-not-released-by-window に統合する。",
    "ask-next-flow-first-run はやめて、feedback-kanban-ai-facing-ask-next に統合する。",
]

EXPECTED = [
    ("pr2-constitution-reset-handoff", "constitution-minimal-core"),
    ("feedback-branch-update-via-github-ui", "constitution-minimal-core"),
    ("project-lm-inbox-pending", "project-handoff-ingest-pipeline"),
    ("playwright-mcp-stale-lock", "playwright-profile-lock-not-released-by-window"),
    ("ask-next-flow-first-run", "feedback-kanban-ai-facing-ask-next"),
]

TITLES = {
    "old-way": "The old way",
    "new-way": "The new way",
}


def user(*texts):
    return [SimpleNamespace(cls="USER", text=t) for t in texts]


def pairs(out):
    return [(h["old"], h["new"]) for h in out if "old" in h]


def why(out):
    return [h["skipped"] for h in out if "skipped" in h]


# ── the regression: the five that made the lane exist ───────────────────────

def test_the_five_real_instructions_are_all_proven_in_the_right_direction():
    out = proven(user(*QUOTES), REAL)
    assert sorted(pairs(out)) == sorted(EXPECTED)


def test_the_five_real_instructions_skip_nothing():
    """A narrowing that turns one of the five into a `skipped` has not narrowed, it has
    broken. The lane is allowed to refuse — just not these."""
    assert why(proven(user(*QUOTES), REAL)) == []


# ── round 2, finding 1: a bare retirement verb does not say which name is dying ──

def test_a_bare_english_retirement_verb_establishes_no_direction():
    """`retire old-way` puts the dying thing AFTER the verb; `old-way をやめる` puts it
    before. Reading both as old-first retires the survivor: "Use new-way; retire
    old-way." would have written new-way as superseded by old-way."""
    out = proven(user("Use new-way; retire old-way."), TITLES)
    assert pairs(out) == []
    assert "direction not established by the construction" in why(out)


@pytest.mark.parametrize("text", [
    "Use new-way and stop using old-way.",
    "We are done with old-way; new-way from here.",
    "Drop old-way, new-way is the one.",
])
def test_the_other_bare_english_verbs_too(text):
    assert pairs(proven(user(text), TITLES)) == [], text


def test_the_japanese_retirement_verb_still_carries_its_own_order():
    """`やめる` / `廃止` DO fix an order — 旧 → 構文 → 新 — and two of the five real
    instructions rest on nothing else. Refusing the whole family was the tempting fix
    and it is the wrong one."""
    assert pairs(proven(user("old-way はやめて、new-way に統合する。"), TITLES)) == [
        ("old-way", "new-way")]


def test_and_refuses_the_same_japanese_sentence_read_backwards():
    out = proven(user("new-way を使い、old-way はやめる。"), TITLES)
    assert pairs(out) == []


# ── round 2, finding 2: direction belongs to the matched construction ───────

def test_position_comes_from_the_occurrence_that_joins_the_construction():
    """The successor is named twice — once in a heading clause before everything, once
    where it belongs. Taking the FIRST occurrence puts new-way ahead of old-way and the
    pair passes reversed."""
    text = "Regarding new-way: stop old-way and replace it with new-way."
    out = proven(user(text), TITLES)
    assert ("new-way", "old-way") not in pairs(out)


def test_a_construction_cannot_lend_its_order_to_names_outside_it():
    """`replace … with` fixes where the two names stand RELATIVE TO ITSELF (old inside
    the span, new after it). Names that stand nowhere near it borrow nothing."""
    out = proven(user("old-way and please replace the file with care and new-way"),
                 TITLES)
    assert pairs(out) == []


# ── round 2, finding 3: the manifest is not written through a substitution ──

def test_the_manifest_is_not_written_when_the_store_no_longer_resolves(tmp_path):
    """`Store.retire` checks the substitution, but by then the lane has already written
    its evidence file — through the symlink, outside the store. The check has to happen
    before the first byte of the manifest."""
    class Substituted:
        name = "stub"
        path = str(tmp_path)

        def _substitution_refusal(self):
            return {"ok": False, "error": "store 'stub' no longer resolves to the "
                                          "directory it was opened on"}

    assert _write_manifest(Substituted(), "q", "src.jsonl", "k", 1) is None
    assert not (tmp_path / "_evidence").exists()


def test_the_manifest_is_still_written_on_an_honest_store(tmp_path):
    class Honest:
        name = "stub"
        path = str(tmp_path)

        def _substitution_refusal(self):
            return None

    digest = _write_manifest(Honest(), "q", "src.jsonl", "k", 1)
    assert digest and (tmp_path / "_evidence" / f"{digest}.json").exists()


# ── round 2, finding 4: the candidate universe is every slug ────────────────

def test_the_candidates_are_built_from_the_slug_set_not_the_title_map():
    """`titles()` is title → slug, so two memories that share an index title collapse to
    one and the loser is invisible to the lane forever while the watermark walks past
    its instruction. Slugs are the universe; a title is an extra way to be named."""
    from distill_kura.distill.retire_lane import _candidates

    class TwoSlugsOneTitle:
        def slug_set(self):
            return frozenset({"slug-a", "slug-b"})

        def titles(self):
            return {"a shared title": "slug-b"}

    c = _candidates(TwoSlugsOneTitle())
    assert set(c) == {"slug-a", "slug-b"}
    assert c["slug-b"] == "a shared title"
