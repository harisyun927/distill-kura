"""Was a transition PROVEN — old → new, in the human's own sentence?

The retirement face rewrites the map's most-read line, so the only thing allowed to
trigger it is a human saying, in one breath, that the old thing is over AND what
takes its place. A model PROPOSING `superseded` proves nothing; the gate refusing
that proposal proves nothing either. Proposed ≠ proven.

Six review rounds tried to read that proof out of ordinary conversation — free text,
scored by construction tables, slot markers and nearest-name heuristics — and each
round's fix was defeated by a new phrasing the next round found. The holes were never
in any one implementation; they were in the METHOD: free text does not carry enough
structure for a machine to recover "this sentence authorises a write" from word order
and position alone, no matter how many patches are layered on the reading.

So this module (2026-09-19, round "A′") stops reading free text for authorisation.
`superseded` may only come from an EXACT, whole-line match of one closed template —
the same template `distill_kura/distill/retire_lane.py` already carries, now defined
here once and imported by that lane so there is a single spec, not two copies drifting
apart:

    <old-slug> は [one reason sentence naming no candidate slug、ending in
    役目終わり。](optional) (退役して|やめて)、<new-slug> (に置き換える|に統合する)[。]

Conversation language ≠ authorisation language. Everything that is not this template —
however plausible, however explicit it reads to a person — proves nothing here. A
free-text proposal is not a lesser form of proof; it is not proof at all, of either
direction. This is a whitelist grammar: it fails closed. Names are exact slugs only —
no titles, no paraphrase, no word overlap — for `superseded`.

A quote that uses one of the loose retirement verbs (`やめる`, `廃止`, `stop`, `退役`,
…) without matching the template is a `retired-only` result: reference information
that the old thing was said to be over, nothing more. It is never proof of a
successor, and no caller may write a face for it — it exists only so a caller can say
WHY it stayed silent. Free text can never grant a write; only the closed template
can.

Pure and model-free on purpose: this is the same relation for the pipeline (which
decides whether to knock) and for `Store.retire` (which must not trust its caller).
"""
from __future__ import annotations

import re
import unicodedata

# ── the one closed template — the ONLY thing that proves `old` → `new` ──────────────
#
# Matched against the WHOLE line (`re.match` anchored at `^`, ending in `$`), not a
# fragment of it. Space (half- or full-width; NFKC folds the latter to the former in
# `_norm`) may sit between a name and its particle, and nowhere else the pattern does
# not already allow for.
#
# `<old-slug>` and `<new-slug>` are read only as raw slug-shaped tokens here — whether
# they are actually known slugs in a given store, and whether the optional reason
# clause names some THIRD candidate, is candidate-set logic that belongs to the
# caller (`retire_lane.py`'s `_match_template`), not to this pure relation.
_WS = r" *"
_SLUG = r"[0-9a-z_\-]+"
# The middle sentence carries a reason and NOTHING else: no subject/topic/object marker
# and no comma, so a clause naming a THIRD thing (in a different voice) cannot slip
# through as "just the reason". It must end in the one fixed phrase 役目終わり, right
# before the sentence's own 。.
_REASON = r"[^はがを、\n。]*役目終わり"
TEMPLATE = re.compile(
    rf"^(?P<old>{_SLUG}){_WS}は{_WS}"
    rf"(?:(?P<reason>{_REASON})。{_WS})?"
    rf"(?:退役して|やめて)、{_WS}"
    rf"(?P<new>{_SLUG}){_WS}"
    rf"(?:に置き換える|に統合する)"
    rf"。?$"
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).lower()


def parse_instruction(line: str) -> tuple[str, str] | None:
    """The (old, new) slugs ONE line proves under the closed template, or None.

    `line` is NFKC-normalised and lower-cased here (idempotent if the caller already
    did it). The match is whole-line-anchored: a valid-looking fragment inside a
    longer line is not a ruling, and multiple template lines in one quote each stand
    on their own (call this once per physical line).

    This is the raw grammar only — no candidate-set check, no reason-clause-names-a-
    third-memory check. A caller that has a store's own slug set (`retire_lane.py`)
    matches `TEMPLATE` directly so it can also read `reason` and validate both names
    against that set; this wrapper is for callers (like `find_transition`, below)
    that only need to know whether a line proves a SPECIFIC (old, new) pair they
    already have in hand.
    """
    m = TEMPLATE.match(_norm(line))
    if not m:
        return None
    return m.group("old"), m.group("new")


# ── retired-only: reference information, never proof of a successor ─────────────────
# A quote that only retires — `やめる`, `廃止`, `stop`, `退役` — is informational: the
# human said the old thing is over, and that much free text CAN carry, because nothing
# downstream of it treats "retired" as license to point at any particular successor.
# It is returned only so a caller can explain why it stayed silent about a successor,
# never to write anything.
_RETIREMENT = [
    ("やめる", r"やめ(?:る|た|よう|ます|る事|ること)?"),
    ("廃止", r"廃止|廃す|打ち切"),
    ("stop", r"\bstop(?:ped|ping|s)?\s+(?:using|doing)?"),
    ("drop", r"\bdrop(?:ped|ping|s)?\b"),
    ("retire", r"\bretir(?:e|ed|es|ing)\b"),
    ("done with", r"\bdone with\b"),
    # The same fixed verb slot the closed template's front side carries. A full
    # positive inflection that ends the clause, never the bare prefix (`退役しない` /
    # `退役してはいけない` are not retirements). `_END` below turns a clause ender into
    # a lookahead so a continuation cannot be mistaken for a ruling.
    ("退役", r"退役(?:して|した|する|します)(?=[\s、,。．.!?！？]|$)"),
]

# A clause that changes the subject can never supply context for `retired-only`
# either: "old-way はやめよう。ところで GPU 温度を測ろう" must never make the GPU
# memory look connected to old-way, even as informational text.
_SHIFT = re.compile(r"(ところで|別件|余談|それはそうと|by the way|anyway|"
                    r"on another note|unrelated)", re.I)

_SENT = re.compile(r"[。．.!?！？\n]")


def _clauses(text: str) -> str:
    """The quote with every topic-shift sentence removed (from the marker onward)."""
    keep = []
    for part in _SENT.split(text):
        if _SHIFT.search(part):
            break
        keep.append(part)
    return "\n".join(keep)


def _names(text: str, *candidates: str) -> str | None:
    """The first candidate that appears in `text` as a whole name (already NFKC-low)."""
    _ASCII = re.compile(r"^[0-9A-Za-z_\-]+$")
    for c in candidates:
        c = _norm(c).strip()
        if not c:
            continue
        pat = (rf"(?<![0-9A-Za-z_\-]){re.escape(c)}(?![0-9A-Za-z_\-])"
               if _ASCII.match(c) else re.escape(c))
        if re.search(pat, text):
            return c
    return None


def _matched(text: str, table) -> list[str]:
    return [name for name, pat in table if re.search(pat, text)]


def find_transition(evidence: list[dict], old: dict, new: dict) -> dict | None:
    """Did ONE [USER] quote prove `old` → `new`?

    → `{"kind": "superseded", ...}` when some physical line of a [USER] quote is an
      exact whole-line match of the closed template naming exactly this (old, new)
      pair — the only route to proof;
      `{"kind": "retired-only", ...}` when the human said the old thing is over (loose
      retirement vocabulary) but no line proved a successor — reference information,
      never proof, and never written anywhere;
      None when nothing was said about the old memory at all, or nothing was proven
      and nothing informational was said either.

    Conversation language ≠ authorisation language: a proposal, a paraphrase, an
    arrow, an "instead of" — none of it counts, however plausible it reads. Only the
    closed template (`TEMPLATE` / `parse_instruction`, above) can produce
    `superseded`.
    """
    old_slug, old_title = str(old.get("slug") or ""), str(old.get("title") or "")
    new_slug, new_title = str(new.get("slug") or ""), str(new.get("title") or "")
    old_norm, new_norm = _norm(old_slug).strip(), _norm(new_slug).strip()
    if not old_norm or not new_norm or old_norm == new_norm:
        return None
    retired_only = None
    for q in (evidence or []):
        if not isinstance(q, dict) or q.get("class") != "USER":
            continue
        whole = _norm(q.get("text"))
        if not _names(whole, old_slug, old_title):
            continue                       # nothing here even mentions the old memory
        # (superseded) — each physical line stands on its own; a template spanning
        # a newline, or sharing a line with other prose, is not a whole-line match.
        for line in whole.splitlines():
            hit = parse_instruction(line)
            if hit == (old_norm, new_norm):
                return {"kind": "superseded", "old": old_slug, "new": new_slug,
                        "quote": str(q.get("text") or ""),
                        "constructions": ["閉じた型: 退役して/に置き換える"]}
        # (retired-only) — informational only; a "ところで" clause is cut first so an
        # unrelated later sentence can never be mistaken for context.
        text = _clauses(whole)
        if not _names(text, old_slug, old_title):
            continue
        retire = _matched(text, _RETIREMENT)
        if retire and retired_only is None:
            retired_only = {"kind": "retired-only", "old": old_slug, "new": None,
                            "quote": str(q.get("text") or ""),
                            "constructions": retire}
    return retired_only
