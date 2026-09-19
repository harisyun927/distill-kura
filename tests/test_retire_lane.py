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


# `test_taiyaku_and_ni_tougou_are_recognised_by_the_independent_relation` (round 4) is
# gone: it asserted `find_transition`'s receipt carried separate `"退役"` / `"に統合"`
# construction names, reconciling a SEPARATE construction table against the template.
# Round A′ (2026-09-19) deleted that separate table — `find_transition` now matches the
# same shared `template` this lane does, so there is nothing left to reconcile; the
# receipt's `constructions` is now the fixed `["閉じた型: 退役して/に置き換える"]` for
# every template match (see `tests/test_transition.py`). Consistency between the lane
# and `find_transition` is still exercised below and in `test_retirement_face.py`.


def test_find_transition_agrees_with_the_lane_on_the_same_template_line():
    """`Store.retire` re-runs `find_transition` on the manifest the lane writes, not as
    a second, independent method any more (round A′: they share one parser) but as a
    check that both sides read the same spec."""
    from distill_kura.distill.transition import find_transition

    text = "old-way は退役して、new-way に統合する。"
    r = find_transition([{"class": "USER", "text": text}],
                        {"slug": "old-way", "title": TITLES["old-way"]},
                        {"slug": "new-way", "title": TITLES["new-way"]})
    assert r is not None and r["kind"] == "superseded"

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


# ── round 5 (the confirmation review's two P1s) ─────────────────────────────


def test_a_negated_integration_or_retirement_proves_nothing():
    """(review) With the inflection optional, the bare prefix `に統合` matched inside
    `に統合しない` and `退役` inside `退役しない`, so a human's explicit REFUSAL of a
    transition came back `superseded` — and both the pour path and `Store.retire`
    trust that relation. The inflection is now required and must be the positive one."""
    from distill_kura.distill.transition import find_transition

    old = {"slug": "old-way", "title": TITLES["old-way"]}
    new = {"slug": "new-way", "title": TITLES["new-way"]}

    def rel(text):
        return find_transition([{"class": "USER", "text": text}], old, new)

    for refusal in ("old-way は new-way に統合しない。",
                    "old-way は new-way に統合しません。",
                    "old-way は new-way に統合するな。",
                    "old-way は退役しない。new-way は別物。",
                    "old-way は退役してはいけない。new-way は別物。"):
        r = rel(refusal)
        assert r is None or r["kind"] != "superseded", refusal

    # The positive forms still prove what they did before.
    r = rel("old-way は退役して、new-way に統合する。")
    assert r is not None and r["kind"] == "superseded"


def test_the_real_watermark_is_not_merged_through_a_substituted_store(tmp_path):
    """(review) The manifest check refuses the evidence write on a swapped store, but
    the end-of-pass merge still built `Watermarks` at the cached `dis.still` — whose
    constructor makes `_still` and whose `advance` writes `retire-watermark.json`
    through the substitution — even when the pass faced nothing. Drive a hit-less,
    non-dry pass against a store that reports substitution and confirm nothing under
    `_still` comes into being and the pass says why."""
    still = tmp_path / "_still"

    class Substituted:
        name = "stub"
        path = str(tmp_path)
        write_policy = "append"

        def _substitution_refusal(self):
            return {"ok": False, "error": "no longer resolves"}

        def titles(self):
            return {}

        def slug_set(self):
            return set()

    dis = SimpleNamespace(store=Substituted(), still=str(still), chunk_chars=4000,
                          marks=SimpleNamespace(read=lambda: {}),
                          files=lambda session=None: [])
    r = run_lane(dis)
    assert r["ok"] is False and "no longer resolves" in r["error"]
    assert r["faced"] == [] and r["refused"] == []
    assert not still.exists()


# ── round 6 (the second confirmation review) ────────────────────────────────


def test_compound_negations_after_the_stem_prove_nothing():
    """(review) Excluding one following character was not a rule: `に統合した` still
    matched inside `に統合したくない`, `に統合する` inside `に統合するべきではない`. An
    affirmative form now has to END its clause — punctuation, whitespace or the end
    of the text — for it to count."""
    from distill_kura.distill.transition import find_transition

    old = {"slug": "old-way", "title": TITLES["old-way"]}
    new = {"slug": "new-way", "title": TITLES["new-way"]}

    def rel(text):
        return find_transition([{"class": "USER", "text": text}], old, new)

    for refusal in ("old-way は new-way に統合したくない。",
                    "old-way は new-way に統合するべきではない。",
                    "old-way は new-way に統合してはならない。",
                    "old-way は退役するべきではない。new-way に統合する話は別。",
                    "old-way は退役したくない。new-way は別物。"):
        r = rel(refusal)
        assert r is None or r["kind"] != "superseded", refusal

    # The template's own closed forms still count, with or without the 。 that
    # `_clauses` turns into a space.
    for ok in ("old-way は退役して、new-way に統合する。",
               "old-way は退役して、new-way に統合する",
               "old-way は退役して、new-way に置き換える。"):
        r = rel(ok)
        assert r is not None and r["kind"] == "superseded", ok


def test_a_bare_retirement_verb_beside_a_mention_is_retired_only():
    """(review) `old-way は退役した。new-way は別物。` named both memories and carried a
    retirement verb, and that was enough for `superseded` — the second sentence
    explicitly says there is no succession. Only a REPLACEMENT construction connects
    two names; a retirement verb alone stops at `retired-only`, for every verb in
    the table, not just the newly added one."""
    from distill_kura.distill.transition import find_transition

    old = {"slug": "old-way", "title": TITLES["old-way"]}
    new = {"slug": "new-way", "title": TITLES["new-way"]}
    for text in ("old-way は退役した。new-way は別物。",
                 "old-way はやめた。new-way は別物。",
                 "old-way is retired. new-way is nice.",
                 "old-way は廃止。new-way も見ておく。"):
        r = find_transition([{"class": "USER", "text": text}], old, new)
        assert r is not None and r["kind"] == "retired-only" and r["new"] is None, text

    # And the lane never faces such a pair either.
    assert pairs(proven(user("old-way は退役した。new-way は別物。"), TITLES)) == []


def test_a_writing_pass_holds_the_lane_lock_before_copying_the_marks(tmp_path, monkeypatch):
    """(review) Two writing passes each walked a private copy of the real marks, so
    `claim()` reserved only against that copy and both read — and retired, and wrote
    evidence for — the same stretch. A writing pass now takes an exclusive lock on
    `retire-watermark.json.lane.lock` for its whole duration, and takes the copy only
    once it holds it. Recorded through `flock` rather than by racing two processes:
    the order (lock, then copy) is the property."""
    from distill_kura.distill import retire_lane as rl

    still = tmp_path / "_still"
    still.mkdir()
    real = still / "retire-watermark.json"
    real.write_text('{"j": 7}', encoding="utf-8")
    events: list[str] = []
    orig_flock, orig_start = rl.fcntl.flock, rl._start_marks

    def flock(fd, op):
        name = getattr(fd, "name", "")
        if name.endswith(".lane.lock"):
            events.append("lock" if op == rl.fcntl.LOCK_EX else "unlock")
        return orig_flock(fd, op)

    def start(*a, **kw):
        events.append("copy")
        return orig_start(*a, **kw)

    monkeypatch.setattr(rl.fcntl, "flock", flock)
    monkeypatch.setattr(rl, "_start_marks", start)

    class Plain:
        name = "stub"
        path = str(tmp_path)
        write_policy = "append"

        def _substitution_refusal(self):
            return None

        def titles(self):
            return {}

        def slug_set(self):
            return set()

    dis = SimpleNamespace(store=Plain(), still=str(still), chunk_chars=4000,
                          marks=SimpleNamespace(read=lambda: {}),
                          files=lambda session=None: [])
    assert run_lane(dis)["ok"] is True
    assert events == ["lock", "copy", "unlock"]
    assert (still / "retire-watermark.json.lane.lock").exists()

    # A dry run takes no lock and copies as before.
    events.clear()
    assert run_lane(dis, dry_run=True)["ok"] is True
    assert events == ["copy"]


def test_cli_dry_run_makes_nothing_on_a_writable_store(tmp_path):
    """(review) `--dry-run` promised to write nothing, but the CLI built a `Distiller`
    first, whose constructor made `_still/drafts` (and Watermarks / Seeds made their
    own parent) on the store it was handed. Snapshot the store tree before and after
    a dry run and require them identical."""
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from distill_kura import cli
    from distill_kura.store import Store

    s = Store(name="w", path=str(tmp_path / "w"), label="w")
    s.init_files()
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f"""
default = "w"
[stores.w]
path = "{s.path}"
write_policy = "direct-allowed"
[stores.w.distill]
inherit_global_journals = false
""", encoding="utf-8")

    def tree():
        return sorted(os.path.relpath(os.path.join(d, n), s.path)
                      for d, ds, fs in os.walk(s.path) for n in ds + fs)

    before = tree()
    assert cli.main(["-c", str(cfg), "-s", "w", "retire-lane", "--dry-run"]) == 0
    assert tree() == before


# ── round 7 & round 8 (the third and fourth confirmation reviews) ───────────
#
# Both rounds hardened the OLD construction-table reading's "marked slot" / "reversed
# slot" / "filler" machinery against a direction it kept misreading from word order —
# `に統合`'s destination slot, a filler between a name and its marker, a passive that
# turns the slot around. Round A′ (2026-09-19) deleted that whole reading, table and
# slot logic included, so there is no longer any positional analysis to test: every
# construction those rounds fought over — `に統合する`, `replace … with`, `switch to`,
# `instead of`, the passive — now proves nothing in EITHER direction unless the line is
# an exact whole-line match of the closed template, and every one of these round 7/8
# inputs, in both directions, fails that template. Coverage collapses to
# `test_free_text_alone_never_proves_succession` in `tests/test_transition.py`
# (forward direction, several of these constructions) and the regression below (the
# reverse direction of the one construction the closed template DOES carry).


def test_the_closed_template_itself_is_still_directional():
    """The one thing round 7/8 were really guarding — `X は Y に統合する` naming Y as
    the destination — still holds under the closed template: swapping the names in the
    template's own two fixed slots proves the opposite pair, never both."""
    from distill_kura.distill.transition import find_transition

    old = {"slug": "old-way", "title": TITLES["old-way"]}
    new = {"slug": "new-way", "title": TITLES["new-way"]}

    def rel(text):
        return find_transition([{"class": "USER", "text": text}], old, new)

    forward = rel("old-way はやめて、new-way に統合する。")
    assert forward is not None and forward["kind"] == "superseded"

    backward = rel("new-way はやめて、old-way に統合する。")
    assert backward is None or backward["kind"] != "superseded"


def test_a_study_slug_may_stand_in_either_slot_and_is_not_its_basename():
    """(review, A′) A store's long-form notes are slugs of the form `_study/name`
    (store.py). The template's slug token refused the `/`, so such a memory could
    never be retired nor serve as successor — a permanent, silent skip as the
    watermark walked past. And `/` is a name boundary: `_study/brain` is not
    `brain`."""
    from distill_kura.distill.transition import find_transition

    titles = {**TITLES, "_study/old-note": "Old note", "_study/new-note": "New note",
              "brain": "Brain"}

    out = proven(user("_study/old-note はやめて、new-way に統合する。"), titles)
    assert pairs(out) == [("_study/old-note", "new-way")]
    out = proven(user("old-way は PR2 完了で役目終わり。退役して、_study/new-note に置き換える。"),
                 titles)
    assert pairs(out) == [("old-way", "_study/new-note")]

    # The same line proves the same pair through the store's own relation.
    r = find_transition([{"class": "USER", "text": "_study/old-note はやめて、new-way に統合する。"}],
                        {"slug": "_study/old-note", "title": "Old note"},
                        {"slug": "new-way", "title": "The new way"})
    assert r is not None and r["kind"] == "superseded"

    # (review, A′ round 2) A study note's basename is whatever file the store holds —
    # `design.v2`, `design note` — so there is no slug grammar at all: the slots are
    # built from the store's exact candidate names.
    titles3 = {**titles, "_study/design.v2": "Design v2", "_study/design note": "Design note"}
    out = proven(user("_study/design.v2 はやめて、_study/design note に統合する。"), titles3)
    assert pairs(out) == [("_study/design.v2", "_study/design note")]
    r = find_transition([{"class": "USER",
                          "text": "_study/design.v2 はやめて、_study/design note に統合する。"}],
                        {"slug": "_study/design.v2", "title": "Design v2"},
                        {"slug": "_study/design note", "title": "Design note"})
    assert r is not None and r["kind"] == "superseded"
    # And a name the store does NOT hold is not a name, however slug-shaped.
    out = proven(user("_study/design.v3 はやめて、new-way に統合する。"), titles3)
    assert pairs(out) == []

    # `_study/brain` names nothing called `brain`: no pair, and not counted as a name.
    titles2 = {**titles, "_study/brain": "Brain note"}
    out = proven(user("_study/brain はやめて、new-way に統合する。"), titles2)
    assert pairs(out) == [("_study/brain", "new-way")]
    r = find_transition([{"class": "USER", "text": "_study/brain はやめて、new-way に統合する。"}],
                        {"slug": "brain", "title": "Brain"},
                        {"slug": "new-way", "title": "The new way"})
    assert r is None
