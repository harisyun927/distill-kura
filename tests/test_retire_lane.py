"""The retirement lane: what it proves, and — the load-bearing half — what it refuses.

The lane faces memories automatically, so a false positive here rewrites the map's
most-read line to say a living memory is dead. Every test below whose name starts "not"
is guarding a way that was actually possible before the code under it existed.
"""
from types import SimpleNamespace

from distill_kura.distill.retire_lane import MAX_NAMES, proven

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


def test_a_plain_japanese_instruction_proves_one_transition():
    out = proven(user("old-way はやめて、new-way に統合する。"), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_not_the_same_sentence_read_backwards():
    """`find_transition` answers `superseded` for BOTH orderings of one quote — it is
    the caller that knows which name is dying. Found by the lane's own dry run."""
    out = proven(user("old-way はやめて、new-way に統合する。"), TITLES)
    assert ("new-way", "old-way") not in pairs(out)


def test_instead_of_names_the_successor_first_and_still_retires_the_other():
    """The pair is always (dying, successor). "instead of" is the one construction that
    writes the successor first in the text, so position alone would read it backwards."""
    out = proven(user("Use new-way instead of old-way."), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_one_instruction_may_span_two_sentences_on_one_line():
    """"OLD は…役目終わり。退役して、NEW に置き換える。" is two sentences and one
    instruction. Sentence-only reading proved nothing here."""
    out = proven(user("pr2-handoff は PR2 完了で役目終わり。"
                      "退役して、constitution-core に置き換える。"), TITLES)
    assert pairs(out) == [("pr2-handoff", "constitution-core")]


def test_not_across_lines_of_a_multi_retirement_turn():
    """Five retirements in five lines carry ten names. Read as one quote, line 1's old
    memory pairs with line 5's successor."""
    out = proven(user("old-way はやめて、new-way に統合する。\n"
                      "pr2-handoff はやめて、constitution-core に統合する。"), TITLES)
    assert sorted(pairs(out)) == [("old-way", "new-way"),
                                  ("pr2-handoff", "constitution-core")]


def test_not_an_agents_own_words():
    """Only the human retires anything. The source decides the class; the lane obeys."""
    segs = [SimpleNamespace(cls="SELF", text="old-way はやめて、new-way に統合する。")]
    assert proven(segs, TITLES) == []


def test_not_a_mere_mention_of_two_memories():
    """Naming both is not saying a change — the construction is what says it."""
    assert pairs(proven(user("old-way と new-way の違いを教えて。"), TITLES)) == []


def test_not_a_retirement_without_a_successor():
    """`やめる` alone proves the old thing is over. A face with no successor is not a
    thing this store can write, so the lane stays silent."""
    assert pairs(proven(user("old-way はもうやめる。"), TITLES)) == []


def test_a_list_of_names_is_skipped_loudly():
    titles = {f"memory-{i}": "" for i in range(MAX_NAMES + 2)}
    text = "やめて " + " ".join(titles) + " に置き換える。"
    out = proven(user(text), titles)
    assert pairs(out) == []
    assert any(h.get("skipped") == "too many names" for h in out)


def test_the_same_transition_is_reported_once_per_pass():
    out = proven(user("old-way はやめて、new-way に統合する。\n"
                      "old-way はやめて、new-way に統合する。"), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_a_topic_shift_cannot_supply_the_successor():
    """Defence in depth behind the line unit: `find_transition` cuts the clause itself."""
    assert pairs(proven(user("old-way はやめる。ところで new-way の話だが。"), TITLES)) == []


def test_not_a_slug_that_merely_sits_inside_a_longer_slug():
    """A store holding both `new-way` and `new-way-v2`: naming the second must not read
    as naming the first. The relation refuses that pair anyway (`retired-only`), so this
    pins the layer above it — the candidate list and the position check."""
    titles = {**TITLES, "new-way-v2": "The newer way"}
    out = proven(user("old-way はやめて、new-way-v2 に置き換える。"), titles)
    assert pairs(out) == [("old-way", "new-way-v2")]
