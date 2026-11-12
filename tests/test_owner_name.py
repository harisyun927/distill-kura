"""The store owner's name, from config, closes the speaker floor's gap (life-meta#1423).

On a colleague's journal (`speaker`) the floor refused "the human decided" and the
generic owner nouns, but a sentence that named the owner -- "ミナが決めた", "Mina
decided" -- passed: the name was in no vocabulary. `[stores.<n>] owner` gives it.
Unset, every prompt and every verdict is what it was.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_pending as tp                                     # noqa: E402
from test_journal_speaker import EV, Recorder, _spot_calls     # noqa: E402
from distill_kura.distill import Distiller, prompts           # noqa: E402
from distill_kura.distill.gate import (final_surface_violations,   # noqa: E402
                                       owner_attributions, owner_names)
from distill_kura.registry import Registry                    # noqa: E402
from distill_kura.store import Store                          # noqa: E402

SPEAKER = "Yoichi (web marketing)"
OWNERS = ("ミナ", "Mina")


def _floor(text, speaker=SPEAKER, owners=OWNERS):
    return final_surface_violations(text, EV, ["USER", "TOOL"], speaker=speaker,
                                    owners=owners)


# ── the config ───────────────────────────────────────────────────────────

def _toml(tmp_path, owner_line: str) -> str:
    Store(name="k", path=str(tmp_path / "k")).init_files()
    cfg = tmp_path / "kura.toml"
    cfg.write_text(f'[stores.k]\npath = "{tmp_path / "k"}"\n{owner_line}\n',
                   encoding="utf-8")
    return str(cfg)


@pytest.mark.parametrize("line, want", [
    ('owner = "ミナ"', ("ミナ",)),
    ('owner = ["ミナ", "Mina (owner)"]', ("ミナ", "Mina")),
    ("", ()),
])
def test_owner_loads_as_one_name_or_a_list(tmp_path, line, want):
    reg = Registry.load(_toml(tmp_path, line))
    d = Distiller(reg, reg.stores["k"])
    assert d.owners == want


@pytest.mark.parametrize("line, says", [
    ("owner = 3", "owner must be str or list"),
    ("owner = true", "owner must be str or list"),
    ('owner = ""', "is empty"),
    ('owner = "  "', "is empty"),
    ('owner = "(x)"', "is empty"),
    ("owner = []", "empty list"),
    ('owner = ["ミナ", 3]', "a string or a list of strings"),
    ('owner = "a\\nb"', "one line"),
    (f'owner = "{"x" * 81}"', "one line"),
    ('ownr = "ミナ"', "unknown key"),
])
def test_an_owner_that_cannot_mean_what_it_says_is_refused_at_load(tmp_path, line, says):
    with pytest.raises(ValueError) as e:
        Registry.load(_toml(tmp_path, line))
    assert says in str(e.value), str(e.value)


def test_owner_names_strips_and_dedups():
    assert owner_names(None) == ()
    assert owner_names("ミナ（店主）") == ("ミナ",)
    assert owner_names(["Mina", "Mina (owner)", "ミナ"]) == ("Mina", "ミナ")


# ── the floor: what is refused, what passes ──────────────────────────────

@pytest.mark.parametrize("text", [
    "ミナが保管先を決めた",
    "ミナは遅いディスクに置くと決定した",
    "ミナさんが承認した",
    "ミナの指示で遅いディスクに置く",
    "ミナ：遅いディスクに置く",
    "Mina decided to put the archive on the slow disk.",
    "MINA approved the slow disk.",
    "Mina quickly decided on the slow disk.",
    "Mina's decision: the slow disk.",
    "ミナが耀一の案を承認した",              # the speaker's name inside does not excuse it
])
def test_naming_the_owner_as_the_decider_is_refused(text):
    v = _floor(text, speaker="耀一（Web）" if "耀一" in text else SPEAKER)
    assert v and all(x.startswith("owner-attribution: ") for x in v), v


@pytest.mark.parametrize("text, speaker", [
    ("耀一がミナに聞いて決めた", "耀一（Web）"),          # the speaker is the subject
    ("ミナの話を聞いて耀一が決めた", "耀一（Web）"),      # the speaker takes over
    ("Yoichi asked Mina and decided on the slow disk.", SPEAKER),
    ("Yoichi decided after talking to Mina.", SPEAKER),
    ("ミナミが保管先を決めた", SPEAKER),                 # a longer name is another person
    ("Minato decided on the slow disk.", SPEAKER),
    ("The archive goes on the slow disk.", SPEAKER),
])
def test_the_speaker_as_subject_and_other_names_pass(text, speaker):
    assert _floor(text, speaker=speaker) == []


def test_an_owner_who_shares_the_speakers_name_is_not_judged():
    assert _floor("Mina decided on the slow disk.", speaker="Mina (ops)") == []
    assert _floor("ミナが決めた", speaker="ミナ") == []
    # the other owner name is still judged
    assert _floor("ミナが決めた", speaker="Mina (ops)") == ["owner-attribution: ミナが決め"]


def test_one_finding_per_excerpt():
    # two spellings of one name give one line, not two
    assert owner_attributions("Mina decided.", SPEAKER, owner_names(["Mina", "Mina (owner)"])) == ["Mina decided"]


def test_without_owner_or_speaker_the_floor_is_what_it_was():
    for text in ("ミナが保管先を決めた", "Mina decided on the slow disk.",
                 "Yoichi decided on the slow disk.", "The human decided."):
        before = final_surface_violations(text, EV, ["USER", "TOOL"], speaker=SPEAKER)
        assert final_surface_violations(text, EV, ["USER", "TOOL"], speaker=SPEAKER,
                                        owners=()) == before
        # no speaker: the owner's names change nothing
        assert (final_surface_violations(text, EV, ["USER", "TOOL"], owners=OWNERS)
                == final_surface_violations(text, EV, ["USER", "TOOL"]))
    assert _floor("Mina decided on the slow disk.", speaker=None) == []


# ── the prompts ──────────────────────────────────────────────────────────

def test_the_note_names_the_owner_and_is_unchanged_without_one():
    plain = prompts.speaker_note(SPEAKER)
    assert prompts.speaker_note(SPEAKER, owners=()) == plain
    assert "calls the human. They are" in plain
    named = prompts.speaker_note(SPEAKER, owners=("ミナ", "Mina"))
    assert "calls the human (ミナ / Mina). They are" in named
    assert named.replace(" (ミナ / Mina)", "") == plain
    assert prompts.speaker_note(None, owners=("ミナ",)) == ""
    braced = prompts.speaker_note(SPEAKER, braced=True, owners=("K{x}",))
    assert "(K{{x}})" in braced


def _distiller(tmp_path, speaker, owner=None, scribe=None):
    kw = {"scribe": scribe} if scribe is not None else {}
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE, **kw)
    d.store.owner = owner
    if speaker:
        d.journals = {"yoichi": {"kind": "claude", "root": str(tmp_path / "journals"),
                                 "speaker": speaker}}
    b, s = d.models.brain, d.models.scribe
    d.models.brain = Recorder(url=b.url, model=b.model, name="brain", spot=b.spot, other=b.other)
    d.models.scribe = Recorder(url=s.url, model=s.model, name="scribe", other=s.other)
    return d


def test_the_owner_rides_the_brain_and_the_scribe(tmp_path):
    d = _distiller(tmp_path, SPEAKER, owner="ミナ")
    assert d.run(chunks=1)["drafts"]
    spot_sys, _ = _spot_calls(d)[0]
    assert spot_sys.endswith(prompts.speaker_note(SPEAKER, owners=("ミナ",)))
    assert "calls the human (ミナ)." in d.models.scribe.calls[0][0]


def _calls(tmp_path, speaker, owner):
    d = _distiller(tmp_path, speaker, owner=owner)
    d.run(chunks=1)
    return d.models.brain.calls, d.models.scribe.calls


def test_an_unset_owner_and_a_journal_without_speaker_are_byte_identical(tmp_path):
    base = _calls(tmp_path / "a", SPEAKER, None)
    assert _calls(tmp_path / "b", SPEAKER, None) == base   # determinism of the check
    # no speaker: the owner's name appears nowhere
    own0 = _calls(tmp_path / "c", None, None)
    own1 = _calls(tmp_path / "d", None, "ミナ")
    assert own1 == own0


SCRIBE_NAMING_OWNER = ("SLUG: archive-on-slow-disk\nTITLE: Archive on the slow disk\n"
                       "DESC: the archive lives on the slow disk\n"
                       "BODY:\nMina decided to put the archive on the slow disk.\n")


def test_the_scribe_cannot_name_the_owner_as_the_decider(tmp_path):
    d = _distiller(tmp_path, SPEAKER, owner="Mina", scribe=SCRIBE_NAMING_OWNER)
    r = d.run(chunks=1)
    assert not r.get("drafts"), r
    assert "owner-attribution: Mina decided" in d.models.scribe.calls[1][1]


def test_without_owner_the_same_draft_is_taken(tmp_path):
    d = _distiller(tmp_path, SPEAKER, owner=None, scribe=SCRIBE_NAMING_OWNER)
    assert d.run(chunks=1).get("drafts")
