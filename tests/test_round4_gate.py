"""The acceptance gate for round 4 — written by the reviewer, not the fixer.

This file is the contract. It is NOT yours to edit: if a change you make cannot pass it,
the change is wrong, not the gate.

Three review rounds found thirteen holes in this lane, and every one of them came from
the same place: reading DIRECTION off the order and position of words in a free-form
sentence. Negation ("やめない"), a different subject ("予備サーバーは退役した"), a
heading mention, the passive, `instead of`, and one name nested inside another all defeat
that reading, and three independent implementers fell into the same holes.

So this round does not patch the reading. It removes it. The lane now carries exactly ONE
closed template, matched against the whole line:

    <old-slug> は [one sentence naming no memory。] (退役して|やめて)、<new-slug> (に置き換える|に統合する)[。]

Everything else is refused. A person who wants anything else retired says so with
`kura retire`, which was always the explicit door.

The regression half is the same five real instructions as every round before.
"""
from types import SimpleNamespace

import pytest

from distill_kura.distill.retire_lane import proven

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
    "new-way-v2": "The newer way",
    "third-thing": "Third thing",
}

REFUSED = "direction not established by the construction"


def user(*texts):
    return [SimpleNamespace(cls="USER", text=t) for t in texts]


def pairs(out):
    return [(h["old"], h["new"]) for h in out if "old" in h]


def why(out):
    return [h["skipped"] for h in out if "skipped" in h]


# ── the regression: the five that made the lane exist ───────────────────────

def test_the_five_real_instructions_are_all_proven_in_the_right_direction():
    assert sorted(pairs(proven(user(*QUOTES), REAL))) == sorted(EXPECTED)


def test_the_five_real_instructions_skip_nothing():
    assert why(proven(user(*QUOTES), REAL)) == []


# ── what the template carries ──────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "old-way はやめて、new-way に統合する。",
    "old-way は退役して、new-way に置き換える。",
    "old-way はやめて、new-way に置き換える。",       # the verbs are two free slots,
    "old-way は退役して、new-way に統合する。",        # not two fixed sentences
    "old-way は役目終わり。退役して、new-way に置き換える。",
    "old-way はやめて、new-way に統合する",            # the closing 。 is optional
])
def test_the_template_carries_its_own_forms(text):
    assert pairs(proven(user(text), TITLES)) == [("old-way", "new-way")], text


def test_a_slug_is_read_whole_not_as_a_prefix():
    out = proven(user("old-way はやめて、new-way-v2 に統合する。"), TITLES)
    assert pairs(out) == [("old-way", "new-way-v2")]


def test_each_line_is_its_own_instruction():
    out = proven(user("old-way はやめて、new-way に統合する。\n"
                      "third-thing は退役して、new-way-v2 に置き換える。"), TITLES)
    assert sorted(pairs(out)) == [("old-way", "new-way"), ("third-thing", "new-way-v2")]


# ── what it refuses: every hole the last three rounds found ───────────────
# None of these may produce a pair in EITHER direction. The reversed ones are the ones
# that wrote a living memory as dead.

@pytest.mark.parametrize("text", [
    # round 2
    "Use new-way; retire old-way.",
    "Use new-way and stop using old-way.",
    "new-way を使い、old-way はやめる。",
    "Regarding new-way: stop old-way and replace it with new-way.",
    # round 3
    "new-way については、old-way を new-way に変更する。",
    "old-way → new-way, not new-way → old-way.",
    "old-way は便利だ。画面を new-way に変更する。",
    # round 4 (found against round 3's fixes)
    "old-way は便利だ。作業は終わり。画面を new-way に変更する。",
    "old-way はやめない。画面を new-way に変更する。",
    "old-way は便利だ。予備サーバーは退役した。画面を new-way に変更する。",
    "old-way は退役しない。画面を new-way に変更する。",
    "Instead of replacing new-way, keep old-way.",
    # forms that used to be carried and deliberately are not any more
    "old-way is replaced with new-way.",
    "Use new-way instead of old-way.",
    "Instead of old-way, use new-way.",
    "old-way → new-way",
    "old-way を new-way に変更する。",
    "old-way に代えて new-way を使う。",
])
def test_nothing_outside_the_template_is_carried(text):
    assert pairs(proven(user(text), TITLES)) == [], text


def test_two_lines_that_contradict_each_other_do_not_retire_each_other():
    out = proven(user("old-way → new-way.\nold-way → new-way, not new-way → old-way."),
                 TITLES)
    assert ("new-way", "old-way") not in pairs(out)


def test_a_name_nested_inside_another_is_not_a_second_name():
    """「方針」sits inside「新方針」. Matching Japanese titles by containment made the
    nested name look like two occurrences and let the pair pass reversed. The template
    names memories by slug only, so this cannot arise — asserted, not assumed."""
    nest = {"a": "方針", "b": "新方針"}
    assert pairs(proven(user("方針を新方針に変更する。"), nest)) == []


def test_the_template_must_be_the_whole_line():
    """A valid instruction inside a longer line is not the person's whole ruling."""
    for text in ("念のため old-way はやめて、new-way に統合する。",
                 "old-way はやめて、new-way に統合する。ところで third-thing の話だが。"):
        assert pairs(proven(user(text), TITLES)) == [], text


def test_the_middle_sentence_may_not_name_a_memory():
    """The optional sentence between 「は」 and the verb is where the reason goes
    (「PR2 完了で役目終わり」). If it names another memory, the line is no longer
    about one pair."""
    text = "old-way は third-thing と同じく役目終わり。退役して、new-way に置き換える。"
    assert pairs(proven(user(text), TITLES)) == []


def test_titles_do_not_stand_in_for_slugs():
    assert pairs(proven(user("The old way はやめて、The new way に統合する。"), TITLES)) == []


def test_a_memory_cannot_succeed_itself():
    assert pairs(proven(user("old-way はやめて、old-way に統合する。"), TITLES)) == []


def test_a_name_that_is_not_in_the_store_is_not_retired():
    assert pairs(proven(user("old-way はやめて、no-such-memory に統合する。"), TITLES)) == []


# ── loud, not silent ───────────────────────────────────────────────────────

def test_a_line_naming_two_memories_outside_the_template_says_why():
    """Two memories in one line that is not the template is exactly the case a person
    should see, so they can say it with `kura retire` instead."""
    out = proven(user("Use new-way; retire old-way."), TITLES)
    assert pairs(out) == []
    assert REFUSED in why(out)


def test_ordinary_talk_is_not_logged():
    """A line naming one memory, or none, is not an attempted instruction. Logging every
    such line would bury the ones that matter."""
    for text in ("old-way の件、あとで見ておいて。", "今日は暑い。"):
        assert why(proven(user(text), TITLES)) == [], text


def test_only_the_person_retires_anything():
    segs = [SimpleNamespace(cls="SELF", text="old-way はやめて、new-way に統合する。")]
    assert proven(segs, TITLES) == []
