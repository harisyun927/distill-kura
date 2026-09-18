"""The retirement lane: what it proves, and — the load-bearing half — what it refuses.

The lane faces memories automatically, and `Store.retire` accepts what it writes on the
strength of a NONDIRECTIONAL relation, so a wrong direction here rewrites the map's
most-read line to say a living memory is dead. Every test below whose name starts "not"
is guarding a way that was actually possible before the code under it existed; the ones
marked (review) were found by Codex review of the first version, not by the dry run.
"""
from types import SimpleNamespace

from distill_kura.distill.retire_lane import MAX_NAMES, proven, run_lane

TITLES = {
    "old-way": "The old way",
    "new-way": "The new way",
    "pr2-handoff": "PR2 着手手順",
    "constitution-core": "憲法の核",
    "third-thing": "Third thing",
}


def user(text):
    return [SimpleNamespace(cls="USER", text=text)]


def pairs(out):
    return [(h["old"], h["new"]) for h in out if "old" in h]


def why(out):
    return [h["skipped"] for h in out if "skipped" in h]


# ── what it proves ──────────────────────────────────────────────────────────

def test_a_plain_japanese_instruction_proves_one_transition():
    out = proven(user("old-way はやめて、new-way に統合する。"), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_instead_of_names_the_successor_first_and_still_retires_the_other():
    """The pair is always (dying, successor). `instead of` is the one construction that
    writes the successor first, so position alone would read it backwards."""
    out = proven(user("Use new-way instead of old-way."), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_one_instruction_may_span_two_adjacent_sentences():
    """"OLD は…役目終わり。退役して、NEW に置き換える。" is two sentences and one
    instruction: one name each, and the construction beside the successor."""
    out = proven(user("pr2-handoff は PR2 完了で役目終わり。"
                      "退役して、constitution-core に置き換える。"), TITLES)
    assert pairs(out) == [("pr2-handoff", "constitution-core")]


# ── what it refuses ─────────────────────────────────────────────────────────

def test_not_the_same_sentence_read_backwards():
    """`find_transition` answers `superseded` for BOTH orderings of one quote — it is
    the caller that knows which name is dying."""
    out = proven(user("old-way はやめて、new-way に統合する。"), TITLES)
    assert ("new-way", "old-way") not in pairs(out)


def test_not_a_construction_that_does_not_fix_an_order():
    """(review) `switch to` / `now use` / `代わりに` / `今後は` / bare `instead` can all
    put the successor first. The first version called them old-first and would have
    written these backwards."""
    for text in ("Switch to new-way, not old-way.",
                 "new-way を old-way の代わりに使う。",
                 "Now use new-way, not old-way."):
        out = proven(user(text), TITLES)
        assert pairs(out) == [], text
        assert "direction not established by the construction" in why(out), text


def test_not_a_pair_whose_names_have_no_position():
    """(review) Named by title while the check looked only for the slug: both positions
    were -1, both orientations passed, and the two memories retired each other."""
    out = proven(user("Use The new way instead of The old way."), TITLES)
    assert ("new-way", "old-way") not in pairs(out)
    assert pairs(out) in ([], [("old-way", "new-way")])


def test_not_two_unrelated_sentences_sharing_a_line():
    """(review) Two names on one line is not one instruction. Here the retirement is in
    the first sentence and the second only mentions a memory."""
    out = proven(user("old-way is retired. new-way is nice."), TITLES)
    assert pairs(out) == []


def test_not_an_agents_own_words():
    """Only the human retires anything. The source decides the class; the lane obeys."""
    segs = [SimpleNamespace(cls="SELF", text="old-way はやめて、new-way に統合する。")]
    assert proven(segs, TITLES) == []


def test_not_a_mere_mention_of_two_memories():
    assert pairs(proven(user("old-way と new-way の違いを教えて。"), TITLES)) == []


def test_not_a_retirement_without_a_successor():
    assert pairs(proven(user("old-way はもうやめる。"), TITLES)) == []


def test_not_across_lines_of_a_multi_retirement_turn():
    """Five retirements in five lines carry ten names. Read as one quote, line 1's old
    memory pairs with line 5's successor."""
    out = proven(user("old-way はやめて、new-way に統合する。\n"
                      "pr2-handoff はやめて、constitution-core に統合する。"), TITLES)
    assert sorted(pairs(out)) == [("old-way", "new-way"),
                                  ("pr2-handoff", "constitution-core")]


def test_not_a_slug_that_merely_sits_inside_a_longer_slug():
    """A store holding both `new-way` and `new-way-v2`: naming the second must not read
    as naming the first."""
    titles = {**TITLES, "new-way-v2": "The newer way"}
    out = proven(user("old-way はやめて、new-way-v2 に置き換える。"), titles)
    assert pairs(out) == [("old-way", "new-way-v2")]


def test_a_list_of_names_is_skipped_loudly():
    titles = {f"memory-{i}": "" for i in range(MAX_NAMES + 2)}
    out = proven(user("やめて " + " ".join(titles) + " に置き換える。"), titles)
    assert pairs(out) == []
    assert "too many names" in why(out)


def test_the_same_transition_is_reported_once_per_pass():
    out = proven(user("old-way はやめて、new-way に統合する。\n"
                      "old-way はやめて、new-way に統合する。"), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_a_topic_shift_cannot_supply_the_successor():
    assert pairs(proven(user("old-way はやめる。ところで new-way の話だが。"), TITLES)) == []


def test_a_frozen_store_is_asked_before_the_first_byte():
    """(review) `Store.retire` refuses a frozen store, but by then the evidence file is
    on disk and the watermark is about to move. Nothing may write means nothing."""
    dis = SimpleNamespace(store=SimpleNamespace(name="s", write_policy="frozen"))
    r = run_lane(dis)
    assert r["ok"] is False and "frozen" in r["error"]
    assert r["faced"] == [] and r["segments"] == 0
