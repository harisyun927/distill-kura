"""The retirement lane: what it proves, and — the load-bearing half — what it refuses.

The lane faces memories automatically, and `Store.retire` accepts what it writes on the
strength of a NONDIRECTIONAL relation, so a wrong direction here rewrites the map's
most-read line to say a living memory is dead. Every test below whose name starts "not"
is guarding a way that was actually possible before the code under it existed; the ones
marked (review) were found by Codex review of the first version, not by the dry run.

The block at the bottom (marked "round 2") is this fixer's own coverage of the four
findings `tests/test_round2_gate.py` grades against — added alongside the gate, not
instead of it, since the gate is not mine to edit.
"""
import os
from types import SimpleNamespace

from distill_kura.distill.retire_lane import (MAX_NAMES, _candidates,
                                              _write_manifest, proven, run_lane)

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
    """Rewritten for round 4 (was: asserted this still retired old-way). `instead of` is
    not one of the two fixed verb slots the closed template carries, so the line is now
    refused outright rather than read positionally."""
    out = proven(user("Use new-way instead of old-way."), TITLES)
    assert pairs(out) == []


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


# ── round 2, my own coverage of the four findings (the gate is not mine to edit) ──

def test_ni_henkou_needs_old_to_precede_new_not_just_both_before_the_verb():
    """`に変更` / `に置き換え` put BOTH names before the construction ("old を new に変更
    する"), so the slot table alone cannot tell old from new the way an asymmetric slot
    pair (before/after) can — it needs the extra "old's occurrence precedes new's" check.
    Without it, "new-way を old-way に変更する。" (which actually changes new-way INTO
    old-way) would read the same as the honest sentence and retire the wrong one."""
    # Rewritten for round 4: `に変更` is outside the closed template (only `に置き換える`
    # / `に統合する` are carried), so the honest sentence is now refused too — the
    # `backwards` assert below is untouched, since it never claimed a pair either way.
    honest = proven(user("old-way を new-way に変更する。"), TITLES)
    assert pairs(honest) == []

    backwards = proven(user("new-way を old-way に変更する。"), TITLES)
    assert ("old-way", "new-way") not in pairs(backwards)


def test_a_span_only_speaks_for_the_occurrence_beside_it_not_a_stray_earlier_one():
    """`やめて…で行く` fixes old-before/new-inside relative to ITS OWN span. A quote that
    names the successor once, far outside any construction's span, and then again where
    the construction actually reaches must still be read off the second occurrence —
    same shape as the gate's `replace … with` case, exercised here against a different
    construction so the span logic is not just proven for one table entry."""
    # Rewritten for round 4: `やめて…で行く` and the leading aside are both outside the
    # closed template (which requires the line's own start to be `<old-slug> は`), so
    # this is now refused rather than read off the span nearest the construction.
    text = "new-way か、それは置いといて、old-way はやめて new-way で行く。"
    out = proven(user(text), TITLES)
    assert pairs(out) == []


def test_write_manifest_leaves_existing_evidence_untouched_when_refused(tmp_path):
    """Containment is checked before the first byte, and that has to mean before ANY
    filesystem side effect — including one that would look harmless next to files
    already there. Pre-seed `_evidence` with an unrelated file and confirm a refused
    write adds nothing beside it (the gate only checks that `_evidence/` is absent for
    an empty store; this checks a non-empty one is not touched either)."""
    ev_dir = tmp_path / "_evidence"
    ev_dir.mkdir()
    (ev_dir / "already-there.json").write_text("{}", encoding="utf-8")

    class Substituted:
        name = "stub"
        path = str(tmp_path)

        def _substitution_refusal(self):
            return {"ok": False, "error": "no longer resolves"}

    assert _write_manifest(Substituted(), "q", "src.jsonl", "k", 1) is None
    assert sorted(p.name for p in ev_dir.iterdir()) == ["already-there.json"]


def test_a_titled_slug_that_collides_with_another_is_still_a_candidate():
    """(mine, alongside the gate's own version of this finding) Three slugs, two of them
    sharing one index title: `store.titles()` alone can name only one slug per title, so
    the collision must not cost a THIRD, unrelated slug its place either — `_candidates`
    has to be built from the whole `slug_set()`, not patched per collision."""
    class ThreeSlugsTwoShareATitle:
        def slug_set(self):
            return frozenset({"slug-a", "slug-b", "slug-c"})

        def titles(self):
            return {"shared title": "slug-b", "solo title": "slug-c"}

    c = _candidates(ThreeSlugsTwoShareATitle())
    assert set(c) == {"slug-a", "slug-b", "slug-c"}
    assert c["slug-a"] == ""              # no title reaches it; the slug still counts
    assert c["slug-b"] == "shared title"
    assert c["slug-c"] == "solo title"


def test_cli_retire_lane_on_a_frozen_store_creates_no_drafts_directory(tmp_path):
    """The CLI's own frozen check has to fire before `_distiller()` runs, because
    `Distiller.__init__` ends with `os.makedirs(self.drafts_dir, exist_ok=True)` — a
    write, unconditional, on the store it is handed. `Store.init_files()` already makes
    `_still` itself (so that alone cannot tell the two branches apart); `_still/drafts`
    only exists once a `Distiller` has been built, so its absence here is the CLI's
    frozen check firing before that construction, driven through `cli.main` rather than
    `run_lane` directly so a regression that moves the check elsewhere shows up too."""
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from distill_kura import cli
    from distill_kura.store import Store

    f = Store(name="f", path=str(tmp_path / "f"), label="f")
    f.init_files()
    assert not (tmp_path / "f" / "_still" / "drafts").exists()   # sanity: not there yet
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f"""
default = "f"
[stores.f]
path = "{f.path}"
write_policy = "frozen"
""", encoding="utf-8")

    code = cli.main(["-c", str(cfg), "-s", "f", "retire-lane", "--dry-run"])
    assert code == 1


# ── round 4, my own coverage of the closed template (the gate is not mine to edit) ──

def test_the_four_verb_combinations_are_all_carried():
    """The two verb slots are independent — front (退役して|やめて) and back (に置き換
    える|に統合する) — and all four pairings carry the same pair."""
    for text in ("old-way はやめて、new-way に統合する。",
                 "old-way は退役して、new-way に置き換える。",
                 "old-way はやめて、new-way に置き換える。",
                 "old-way は退役して、new-way に統合する。"):
        out = proven(user(text), TITLES)
        assert pairs(out) == [("old-way", "new-way")], text


def test_a_reason_sentence_between_は_and_the_verb_is_carried():
    """The optional middle sentence carries no name of its own — it is where the reason
    goes ("PR2 完了で役目終わり"). Round 5 narrowed the reason clause to exclude
    は/が/を/、 (see `test_a_reason_that_names_a_third_thing_via_particles_is_refused`
    below), so this uses a reason with none of them rather than the original
    "仕事を終えたので役目終わり" (which contains を)."""
    out = proven(user("old-way は契約終了で役目終わり。"
                      "退役して、new-way に置き換える。"), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_the_template_must_match_the_whole_line_not_a_fragment_of_it():
    """A closed template matched against a fragment of a longer line is not the whole
    ruling — leading or trailing text outside the template refuses the line entirely,
    even when the template itself, read alone, would have been valid."""
    for text in ("メモ: old-way はやめて、new-way に統合する。",
                 "old-way はやめて、new-way に統合する。以上。"):
        assert pairs(proven(user(text), TITLES)) == [], text


# ── round 5: the four remaining holes ───────────────────────────────────────

def test_a_reason_that_names_a_third_thing_via_particles_is_refused():
    """The middle sentence is where the REASON goes, not a second ruling. A reason
    clause carrying its own subject/object marker or a comma can smuggle a different
    instruction past the containment check (it never literally names a candidate slug,
    so the old, unrestricted `[^。\\n]+。` reason group let it through and old-way was
    retired even though the actual instruction was to retire the SPARE SERVER, not
    old-way). The reason clause is now restricted to a single closed phrase — no
    は/が/を/、, ending in 役目終わり — so this whole line fails the template and, since
    it names two candidates outside the template, is refused loudly rather than
    misread."""
    text = "old-way は残すが、予備サーバーは役目終わり。退役して、new-way に置き換える。"
    out = proven(user(text), TITLES)
    assert pairs(out) == []
    assert "direction not established by the construction" in why(out)


def test_taiyaku_and_ni_tougou_are_recognised_by_the_independent_relation():
    """`Store.retire` re-runs `find_transition` as an independent, nondirectional
    sanity receipt on the pair the template already decided. Round 4 added `退役して` /
    `に統合する` to the closed template without teaching the general relation the same
    two words, so every retirement using them came back `kind: None` — an accepted gap,
    but a silent one. `_RETIREMENT` and `_REPLACEMENT` now carry `退役` and `に統合`, so
    the receipt actively CONFIRMS what the template found instead of merely not
    contradicting it."""
    from distill_kura.distill.transition import find_transition

    text = "old-way は退役して、new-way に統合する。"
    r = find_transition([{"class": "USER", "text": text}],
                        {"slug": "old-way", "title": TITLES["old-way"]},
                        {"slug": "new-way", "title": TITLES["new-way"]})
    assert r is not None and r["kind"] == "superseded"
    assert "退役" in r["constructions"]
    assert "に統合" in r["constructions"]

    # And the lane's own pass still accepts the pair — the independent check agrees,
    # it does not merely fail to object.
    out = proven(user(text), TITLES)
    assert pairs(out) == [("old-way", "new-way")]


def test_a_failed_attempt_that_names_by_title_is_skipped_not_silent():
    """A line using the template's own verb (`退役して` / `やめて`) and naming a
    candidate only by its TITLE — not by slug — still fails the closed template (the
    template only ever reads slugs), but that must not read as ordinary talk: it is a
    failed retirement attempt and has to say so, the same as it would if the names were
    bare slugs."""
    titles = {**TITLES, "current-policy": "現行方針", "new-policy": "新方針"}
    out = proven(user("現行方針はやめて、新方針に統合する。"), titles)
    assert pairs(out) == []
    assert "direction not established by the construction" in why(out)


def test_a_line_broken_by_a_newline_is_skipped_not_silently_lost():
    """The template is line-anchored (each LINE is its own instruction), so an
    instruction split across two lines by a stray newline can never match as a whole —
    but the first half still uses the template's own verb and names a real candidate,
    so it must be flagged rather than let the watermark walk past it as if nothing had
    been said."""
    out = proven(user("old-way は退役して、\nnew-way に置き換える。"), TITLES)
    assert pairs(out) == []
    assert "direction not established by the construction" in why(out)
