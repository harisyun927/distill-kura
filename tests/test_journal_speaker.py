"""A journal may say whose words its [USER] lines are (life-meta#1416).

The charter reads [USER] as the store owner's words. A colleague's conversations, fed
into the same store, were therefore distilled as the owner's decisions. A journal table
may now carry `speaker`; the brain and the scribe are told whose words they read, the
evidence manifest records it, and a new memory's frontmatter says so. A journal without
one is read exactly as before -- the prompts are byte-for-byte what they were.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_pending as tp                                     # noqa: E402
from distill_kura.distill import Distiller, prompts           # noqa: E402
from distill_kura.distill.sources import discover_all, speaker_for   # noqa: E402
from distill_kura.registry import Registry                    # noqa: E402
from distill_kura.store import Store                          # noqa: E402

SPEAKER = "Yoichi (web marketing)"


# ── the config: both forms, and what is refused at load ─────────────────

def _toml(tmp_path, journals: str) -> str:
    Store(name="k", path=str(tmp_path / "k")).init_files()
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f"""
[stores.k]
path = "{tmp_path / 'k'}"
[stores.k.distill]
inherit_global_journals = false
[stores.k.distill.journals]
{journals}
""", encoding="utf-8")
    return str(cfg)


def test_a_path_and_a_table_both_load(tmp_path):
    own, other = tmp_path / "own", tmp_path / "other"
    tp.journal(str(own / "a.jsonl"), tp.LINES)
    tp.journal(str(other / "b.jsonl"), tp.LINES)
    reg = Registry.load(_toml(tmp_path, f'claude = "{own}"\n'
                                        f'yoichi = {{ kind = "claude", root = "{other}", '
                                        f'speaker = "{SPEAKER}" }}'))
    d = Distiller(reg, reg.stores["k"])
    names = sorted(os.path.basename(f) for f in d.files())
    assert names == ["a.jsonl", "b.jsonl"]          # the label key found its format
    assert d.speaker_of(str(other / "b.jsonl")) == SPEAKER
    assert d.speaker_of(str(own / "a.jsonl")) is None


def test_the_plain_form_is_unchanged(tmp_path):
    reg = Registry.load(_toml(tmp_path, f'claude = "{tmp_path / "own"}"'))
    d = Distiller(reg, reg.stores["k"])
    assert d.journals == {"claude": str(tmp_path / "own")}
    assert d.speaker_of(str(tmp_path / "own" / "a.jsonl")) is None


@pytest.mark.parametrize("entry, says", [
    ('yoichi = { kind = "claude", root = "/x", speeker = "Y" }', "unknown key"),
    ('yoichi = { kind = "claude", path = "/x", speaker = "Y" }', "`root`, not `path`"),
    ('yoichi = { kind = "claude", root = "/x", speaker = 3 }', "speaker must be str"),
    ('yoichi = { kind = "claude", root = "/x", speaker = "  " }', "speaker is empty"),
    ('yoichi = { kind = "claude", root = "/x", speaker = "a\\nb" }', "one line"),
    ('yoichi = { root = "/x", speaker = "Y" }', "not a journal format"),
    ('claude = { speaker = "Y" }', "needs a `root`"),
    ('claude = { root = "/x", exclude_glob = [1] }', "list of strings"),
    ('claude = 3', "path or a table"),
])
def test_a_journal_table_that_cannot_mean_what_it_says_is_refused_at_load(tmp_path, entry, says):
    with pytest.raises(ValueError, match=None) as e:
        Registry.load(_toml(tmp_path, entry))
    assert says in str(e.value), str(e.value)


def test_the_global_table_is_checked_too(tmp_path):
    cfg = tmp_path / "kura.toml"
    Store(name="k", path=str(tmp_path / "k")).init_files()
    cfg.write_text(f'[stores.k]\npath = "{tmp_path / "k"}"\n'
                   f'[distill.journals]\nclaude = {{ root = "/x", speaker = "" }}\n',
                   encoding="utf-8")
    with pytest.raises(ValueError, match="speaker is empty"):
        Registry.load(str(cfg))


def test_speaker_for_reads_only_tables_that_name_one(tmp_path):
    roots = {"claude": str(tmp_path / "a"),
             "y": {"kind": "claude", "root": str(tmp_path / "b"), "speaker": SPEAKER}}
    assert speaker_for(roots, str(tmp_path / "b" / "x.jsonl")) == SPEAKER
    assert speaker_for(roots, str(tmp_path / "a" / "x.jsonl")) is None
    assert speaker_for(roots, "") is None
    os.makedirs(tmp_path / "b")
    tp.journal(str(tmp_path / "b" / "x.jsonl"), tp.LINES)
    assert [os.path.basename(f) for f in discover_all(roots)] == ["x.jsonl"]


# ── the prompts ──────────────────────────────────────────────────────────

@dataclass
class Recorder(tp.FakeMouth):
    calls: list = field(default_factory=list)

    def ask(self, system, user, max_tokens=400, timeout=None, temperature=None, schema=None):
        self.calls.append((system, user))
        return super().ask(system, user, max_tokens, timeout, temperature)


def _distiller(tmp_path, speaker):
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE)
    if speaker:
        spec = {"kind": "claude", "root": str(tmp_path / "journals"), "speaker": speaker}
        d.journals = {"yoichi": spec}
    b, s = d.models.brain, d.models.scribe
    d.models.brain = Recorder(url=b.url, model=b.model, name="brain", spot=b.spot, other=b.other)
    d.models.scribe = Recorder(url=s.url, model=s.model, name="scribe", other=s.other)
    return d


def _spot_calls(d):
    return [c for c in d.models.brain.calls if tp.SPOT_PHRASE in c[0]]


def test_the_speaker_rides_the_brain_and_the_scribe(tmp_path):
    d = _distiller(tmp_path, SPEAKER)
    r = d.run(chunks=1)
    assert r["drafts"], r
    spot_sys, _ = _spot_calls(d)[0]
    assert spot_sys.endswith(prompts.speaker_note(SPEAKER))
    assert f"spoken by {SPEAKER}" in spot_sys
    assert spot_sys.startswith(d.charter)             # the shared head is untouched
    scribe_sys, scribe_user = d.models.scribe.calls[0]
    assert f"spoken by {SPEAKER}" in scribe_sys
    assert scribe_user.startswith(prompts.speaker_line(SPEAKER))


def test_a_journal_without_a_speaker_gets_the_prompts_it_always_got(tmp_path):
    d = _distiller(tmp_path, None)
    d.run(chunks=1)
    spot_sys, _ = _spot_calls(d)[0]
    assert spot_sys == d._sys(prompts.SPOT_SYS.format(max_items=d.max_items,
                                                      language=d.language))
    scribe_sys, scribe_user = d.models.scribe.calls[0]
    assert scribe_sys == d._sys(prompts.SCRIBE_SYS.format(language=d.language))
    assert scribe_user.startswith("CANDIDATE: ")
    assert "Whose words" not in scribe_sys + scribe_user


def test_braces_in_a_speaker_do_not_break_the_scribe_template(tmp_path):
    d = _distiller(tmp_path, "Y {team}")
    r = d.run(chunks=1)
    assert r["drafts"], r
    assert "spoken by Y {team}" in d.models.scribe.calls[0][0]


# ── what the memory keeps ────────────────────────────────────────────────

def _manifest_of(d, slug):
    raw = open(os.path.join(d.drafts_dir, f"{slug}.md"), encoding="utf-8").read()
    hexd = raw.split("evidence_manifest: sha256:", 1)[1][:64]
    return d.store.load_manifest_verified(hexd)


def test_the_manifest_and_the_new_memory_say_whose_words(tmp_path):
    d = _distiller(tmp_path, SPEAKER)
    slug = d.run(chunks=1)["drafts"][0]
    assert _manifest_of(d, slug)["speaker"] == SPEAKER
    assert d.pour(slug)["ok"]
    assert d.store.frontmatter_exact(slug).get("speaker") == SPEAKER


def test_the_owners_journal_adds_nothing_to_manifest_or_memory(tmp_path):
    d = _distiller(tmp_path, None)
    slug = d.run(chunks=1)["drafts"][0]
    assert "speaker" not in _manifest_of(d, slug)
    assert d.pour(slug)["ok"]
    assert "speaker" not in d.store.frontmatter_exact(slug)


# ── the floor: the owner said nothing in a colleague's journal (Codex P1) ──

from distill_kura.distill.gate import final_surface_violations   # noqa: E402

EV = [{"class": "USER", "text": "put the archive on the slow disk"},
      {"class": "TOOL", "text": "/data 3.2T used 1.1T avail"}]
BAD = "The human decided to put the archive on the slow disk."


def test_crediting_the_owner_on_a_colleagues_words_is_refused():
    v = final_surface_violations(BAD, EV, ["USER", "TOOL"], speaker=SPEAKER)
    assert v == ["owner-attribution: The human decided"], v
    assert final_surface_violations("ユーザーが保管先を決めた", EV, ["USER"],
                                    speaker=SPEAKER)
    assert final_surface_violations("ケンが決めた", EV, ["USER"], speaker=SPEAKER)


@pytest.mark.parametrize("text", [
    "Yoichi decided to put the archive on the slow disk.",
    "the user Yoichi asked to put the archive on the slow disk.",
    "Yoichi (web marketing) asked for the slow disk; the archive goes there.",
    "The archive goes on the slow disk.",
])
def test_the_speakers_own_name_is_not_an_owner_attribution(text):
    assert final_surface_violations(text, EV, ["USER", "TOOL"], speaker=SPEAKER) == []


def test_a_name_inside_another_word_does_not_excuse_the_owner():
    # Codex P1: speaker "Ed" sits inside "decided".
    assert final_surface_violations(BAD, EV, ["USER", "TOOL"], speaker="Ed") == [
        "owner-attribution: The human decided"]
    assert final_surface_violations("the user Ed asked to put the archive on the slow disk.",
                                    EV, ["USER", "TOOL"], speaker="Ed (ops)") == []
    assert final_surface_violations("the user ED asked for the slow disk.",
                                    EV, ["USER", "TOOL"], speaker="Ed") == []


def test_a_japanese_name_counts_only_as_itself():
    assert final_surface_violations("耀一が保管先を決めた", EV, ["USER"],
                                    speaker="耀一（Web）") == []
    assert final_surface_violations("ユーザーは耀一と保管先を決めた", EV, ["USER"],
                                    speaker="耀一（Web）") == []
    assert final_surface_violations("ユーザーは耀一郎と保管先を決めた", EV, ["USER"],
                                    speaker="耀一（Web）")
    assert final_surface_violations("オーナーはアキラと保管先を決めた", EV, ["USER"],
                                    speaker="アキ")


def test_without_a_speaker_the_floor_is_what_it_was():
    # [USER] present: crediting the human is backed, exactly as before.
    assert final_surface_violations(BAD, EV, ["USER", "TOOL"]) == []
    assert final_surface_violations(BAD, EV, ["USER", "TOOL"], speaker=None) == []
    assert (final_surface_violations("the user decided on 9 disks", EV, ["TOOL"],
                                     speaker=SPEAKER)
            == ["invented number: 9", "credits the human with no [USER] quote",
                "owner-attribution: the user decided"])


BAD_SCRIBE = ("SLUG: archive-on-slow-disk\nTITLE: Archive on the slow disk\n"
              "DESC: the archive lives on the slow disk\n"
              f"BODY:\n{BAD}\n")


def test_the_scribe_cannot_write_the_colleagues_words_as_the_owners(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE, scribe=BAD_SCRIBE)
    d.journals = {"yoichi": {"kind": "claude", "root": str(tmp_path / "journals"),
                             "speaker": SPEAKER}}
    s = d.models.scribe
    d.models.scribe = Recorder(url=s.url, model=s.model, name="scribe", other=s.other)
    r = d.run(chunks=1)
    assert not r.get("drafts"), r                  # dropped after the one retry
    retry = d.models.scribe.calls[1][1]
    assert "owner-attribution: The human decided" in retry
    assert f"The [USER] words are {SPEAKER}'s" in retry


def test_the_owners_journal_still_takes_the_same_draft(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE, scribe=BAD_SCRIBE)
    assert d.run(chunks=1)["drafts"]


POUR_KEY = "You draw the last line"


def _judged(tmp_path, fix_body):
    fix = f"FIX\nreason: tighter\nBODY:\n{fix_body}\n"
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE,
                     scribe={POUR_KEY: fix, "": tp.SCRIBE})
    d.journals = {"yoichi": {"kind": "claude", "root": str(tmp_path / "journals"),
                             "speaker": SPEAKER}}
    s = d.models.scribe
    d.models.scribe = Recorder(url=s.url, model=s.model, name="scribe", other=s.other)
    slug = d.run(chunks=1)["drafts"][0]
    return d, slug, d.drain()


def test_a_fix_cannot_turn_the_colleagues_words_into_the_owners(tmp_path):
    d, slug, out = _judged(tmp_path, BAD)
    assert out["fixed"] == 0 and out["poured"] == 0, out
    assert os.path.exists(os.path.join(d.drafts_dir, f"{slug}.md"))   # left staged
    judge = [c for c in d.models.scribe.calls if POUR_KEY in c[0]][0]
    assert f"spoken by {SPEAKER}" in judge[0]
    assert judge[1].startswith(prompts.speaker_line(SPEAKER))


def test_a_fix_that_keeps_the_speaker_is_poured(tmp_path):
    d, slug, out = _judged(tmp_path, "Yoichi asked to put the archive on the slow disk.")
    assert out["fixed"] == 1 and out["poured"] == 1, out
    assert d.store.frontmatter_exact(slug).get("speaker") == SPEAKER


def test_the_owners_judge_prompt_is_unchanged(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE,
                     scribe={POUR_KEY: "POUR\nreason: fine\n", "": tp.SCRIBE})
    s = d.models.scribe
    d.models.scribe = Recorder(url=s.url, model=s.model, name="scribe", other=s.other)
    slug = d.run(chunks=1)["drafts"][0]
    assert d.drain()["poured"] == 1
    judge = [c for c in d.models.scribe.calls if POUR_KEY in c[0]][0]
    assert judge[0] == d._sys(prompts.POUR_SYS.format(language=d.language))
    assert judge[1].startswith(f"=== DRAFT: {slug} ===")


# ── one root split by globs (Codex P2) ───────────────────────────────────

def test_the_speaker_follows_the_globs_not_just_the_root(tmp_path):
    r = tmp_path / "sessions"
    tp.journal(str(r / "own" / "a.jsonl"), tp.LINES)
    tp.journal(str(r / "other" / "b.jsonl"), tp.LINES)
    a, b = str(r / "own" / "a.jsonl"), str(r / "other" / "b.jsonl")
    roots = {"claude": {"root": str(r), "include_glob": ["own/**"]},
             "yoichi": {"kind": "claude", "root": str(r), "include_glob": ["other/**"],
                        "speaker": SPEAKER}}
    assert sorted(os.path.basename(f) for f in discover_all(roots)) == ["a.jsonl", "b.jsonl"]
    assert speaker_for(roots, b) == SPEAKER
    assert speaker_for(roots, a) is None
    # the exclude side of the same selection
    roots["yoichi"] = {"kind": "claude", "root": str(r), "exclude_glob": ["own/**"],
                       "speaker": SPEAKER}
    assert speaker_for(roots, b) == SPEAKER
    assert speaker_for(roots, a) is None


def test_the_speaker_follows_the_adapter_too(tmp_path):
    # Codex P2: one directory, two formats -- the text adapter never reads own.jsonl.
    r = tmp_path / "journals"
    tp.journal(str(r / "own.jsonl"), tp.LINES)
    (r / "note.md").write_text("put the archive on the slow disk\n", encoding="utf-8")
    roots = {"claude": str(r),
             "colleague": {"kind": "text", "root": str(r), "speaker": "Aki"}}
    assert sorted(os.path.basename(f) for f in discover_all(roots)) == ["note.md", "own.jsonl"]
    assert speaker_for(roots, str(r / "own.jsonl")) is None
    assert speaker_for(roots, str(r / "note.md")) == "Aki"
    # a key that names a kind no adapter has gives nobody a speaker
    assert speaker_for({"x": {"kind": "nope", "root": str(r), "speaker": "Aki"}},
                       str(r / "note.md")) is None
