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
from typing import Iterable

# ── the one closed template — the ONLY thing that proves `old` → `new` ──────────────
#
# Matched against the WHOLE line (`re.match` anchored at `^`, ending in `$`), not a
# fragment of it. Space (half- or full-width; NFKC folds the latter to the former in
# `_norm`) may sit between a name and its particle, and nowhere else the pattern does
# not already allow for.
#
# `<old-slug>` and `<new-slug>` are not a grammar of slug shapes: `template(names)`
# builds the two slots from the exact names the caller hands it (the store's candidate
# set in the lane, the (old, new) pair in hand for `find_transition`). Whether the
# optional reason clause names some THIRD candidate is the lane's own check.
_WS = r" *"
# The middle sentence carries a reason and NOTHING else: no subject/topic/object marker
# and no comma, so a clause naming a THIRD thing (in a different voice) cannot slip
# through as "just the reason". It must end in the one fixed phrase 役目終わり, right
# before the sentence's own 。.
_REASON = r"[^はがを、\n。]*役目終わり"


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).lower()


def template(names: "list[str] | tuple[str, ...]") -> re.Pattern:
    """The closed template, with both name slots restricted to EXACTLY the given
    names (already the caller's exact slugs; normalised here the way the line is).

    There is no grammar of what a slug looks like here on purpose: a store's slug is
    whatever file it holds (`name`, `_study/name`, `_study/design.v2`, …), so the only
    correct definition of "a name in the slot" is "one of the names the caller knows".
    Longest names first, so `new-way-v2` is never read as `new-way` + stray text — and
    the surrounding particle/verb is required immediately after, so it cannot be.
    """
    alts = sorted({_norm(n).strip() for n in names if _norm(n).strip()},
                  key=len, reverse=True)
    alt = "|".join(re.escape(a) for a in alts) or "(?!)"
    return re.compile(
        rf"^(?P<old>{alt}){_WS}は{_WS}"
        rf"(?:(?P<reason>{_REASON})。{_WS})?"
        rf"(?:退役して|やめて)、{_WS}"
        rf"(?P<new>{alt}){_WS}"
        rf"(?:に置き換える|に統合する)"
        rf"。?$"
    )


# ── decomposition, not the full names×names product ─────────────────────────────────
#
# A store's `slugs()` accepts any Markdown basename, so nothing stops it holding
# `x`, `x はやめて、y`, `y はやめて、z` and `z` side by side. Against that store,
# `x はやめて、y はやめて、z に統合する。` reads TWO ways under the closed template —
# (old=x, new="y はやめて、z") and (old="x はやめて、y", new=z) — and the old "try the
# alternation, take whichever it lands on" reading picked the longest name silently.
# A line whose decomposition is not unique proves nothing; it is refused exactly like
# a line that matches no template at all.
#
# Enumerating every (old, new) pair from `names` (hundreds, in the lane) would be the
# full product. Instead: `old` can only be a name the line could START with (at the
# line's own head); `new` can only be a name the line could END with (right before
# the trailing `。`, past `に置き換える|に統合する`). Only the pairs that survive both
# filters are confirmed by building the REAL two-name template and matching the whole
# line — small counts on both sides of the product, not `len(names)**2`.
_JP_OLD_START_FMT = r"^{name}"
_JP_NEW_END_FMT = r"{name}" + _WS + r"(?:に置き換える|に統合する)。?$"


def _decompositions(normed: str, names: "Iterable[str]", build,
                    old_start_fmt: str, new_end_fmt: str
                    ) -> set[tuple[str, str]]:
    """Every NORMALISED (old, new) pair whose own two-name template — `build([old,
    new])`, not the full-`names` one — matches `normed` in full, for one closed
    template. See the module note above for why this is a filtered pair search, not
    the `names` × `names` product.
    """
    old_ok: set[str] = set()
    new_ok: set[str] = set()
    for n in names:
        nn = _norm(n).strip()
        if not nn:
            continue
        if re.match(old_start_fmt.format(name=re.escape(nn)), normed):
            old_ok.add(nn)
        if re.search(new_end_fmt.format(name=re.escape(nn)), normed):
            new_ok.add(nn)
    found: set[tuple[str, str]] = set()
    for on in old_ok:
        for nn in new_ok:
            if on == nn:
                continue
            m = build([on, nn]).match(normed)
            if m and m.group("old") == on and m.group("new") == nn:
                found.add((on, nn))
    return found


def parse_instruction(line: str, names: "list[str] | tuple[str, ...]"
                      ) -> tuple[str, str, str | None] | None:
    """The (old, new, reason) ONE line proves under the closed template, with old and
    new drawn from `names` (returned in the caller's own spelling), or None.

    `line` is NFKC-normalised and lower-cased here. The match is whole-line-anchored:
    a valid-looking fragment inside a longer line is not a ruling, and multiple
    template lines in one quote each stand on their own (call this once per physical
    line). A name "succeeding" itself is not an instruction.

    A line may decompose into an (old, new) pair more than one way when the store
    holds names built out of other names (`x`, `x はやめて、y`, `y はやめて、z`, `z` —
    see `_decompositions`). A non-unique decomposition proves nothing: it is refused
    exactly like no match at all.
    """
    normed = _norm(line)
    decomps = _decompositions(normed, names, template, _JP_OLD_START_FMT,
                              _JP_NEW_END_FMT)
    if len(decomps) != 1:
        return None
    ((old_norm, new_norm),) = decomps
    # Two of the caller's names may fold to the same normalised spelling (`Old` and
    # `old`, or an NFKC pair). A slot that matched such a spelling names BOTH — which
    # is to say it names neither exactly — and is refused rather than resolved to
    # whichever happened to come last. Exact names only.
    back: dict[str, set[str]] = {}
    for n in names:
        back.setdefault(_norm(n).strip(), set()).add(n)
    olds, news = back.get(old_norm, set()), back.get(new_norm, set())
    if len(olds) != 1 or len(news) != 1:
        return None
    (old,), (new,) = olds, news
    if old == new:
        return None
    m = template((old_norm, new_norm)).match(normed)
    return old, new, (m.groupdict().get("reason") if m else None)


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
    # `退役してはいけない` are not retirements): the lookahead requires a clause ender
    # so a continuation cannot be mistaken for a ruling.
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
    # `/` is a slug character too (`_study/name`), so it is part of the boundary:
    # `_study/brain` must not read as naming `brain`.
    _ASCII = re.compile(r"^[0-9A-Za-z_\-/]+$")
    for c in candidates:
        c = _norm(c).strip()
        if not c:
            continue
        pat = (rf"(?<![0-9A-Za-z_\-/]){re.escape(c)}(?![0-9A-Za-z_\-/])"
               if _ASCII.match(c) else re.escape(c))
        if re.search(pat, text):
            return c
    return None


def _matched(text: str, table) -> list[str]:
    return [name for name, pat in table if re.search(pat, text)]


def find_transition(evidence: list[dict], old: dict, new: dict,
                    known: "Iterable[str] | None" = None) -> dict | None:
    """Did ONE [USER] quote prove `old` → `new`?

    `known` is every slug the store holds (its `slug_set()`); the (old, new) pair is
    added to it. It is what lets `parse_instruction` see a THIRD name that folds to
    the same normalised spelling as `old` or `new` (`Old` beside `old`) and refuse
    the slot as ambiguous. With only the pair in hand that collision is invisible, so
    a caller that has a store must pass it — the lane, the pour path and
    `Store.retire` all do.

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
    closed template (`template` / `parse_instruction`, above) can produce
    `superseded`.
    """
    old_slug, old_title = str(old.get("slug") or ""), str(old.get("title") or "")
    new_slug, new_title = str(new.get("slug") or ""), str(new.get("title") or "")
    old_norm, new_norm = _norm(old_slug).strip(), _norm(new_slug).strip()
    if not old_norm or not new_norm or old_norm == new_norm:
        return None
    names = tuple({str(n) for n in (known or ()) if str(n)} | {old_slug, new_slug})
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
            hit = parse_instruction(line, names)
            if hit is not None and (hit[0], hit[1]) == (old_slug, new_slug):
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
