"""Was a transition PROVEN — old → new, in the human's own sentence?

The retirement face rewrites the map's most-read line, so the only thing allowed to
trigger it is a human saying, in one breath, that the old thing is over AND what
takes its place. A model PROPOSING `superseded` proves nothing; the gate refusing
that proposal proves nothing either. Proposed ≠ proven.

Pure and model-free on purpose: this is the same relation for the pipeline (which
decides whether to knock) and for `Store.retire` (which must not trust its caller).

The three things ONE [USER] quote must carry, all of them, none stitched together
from two quotes:
  (i)   the OLD memory, by exact slug or exact index title;
  (ii)  an explicit replacement/retirement construction — the sentence has to SAY the
        change, not merely mention both names;
  (iii) the NEW memory, in the SAME quote: exact slug, exact title, or ≥2 whole words
        of its title/topic.
A topic-shift clause ("ところで…", "by the way …") is cut off before (ii) and (iii)
are looked for, so "old-way はやめよう。ところで GPU 温度を測ろう" can never make the
GPU memory the successor of old-way.

A quote that only retires — `やめる`, `廃止`, `stop`, `退役` — is a `retired-only`
result even when the new memory is mentioned somewhere in it: retirement is proven,
succession is NOT, because no construction connected the two names. No caller writes a
face for it (a face without a successor is not implemented); it is returned so the
callers can say WHY they stayed silent.
"""
from __future__ import annotations

import re
import unicodedata

# ── the constructions that SAY a change, per language ───────────────────────
# Each is (name, pattern). The name is the receipt: what the human's sentence was
# read as. `…` in a construction is a gap the pattern spans loosely.

# What may follow an affirmative verb form for it to count: the end of the clause —
# punctuation, whitespace (what `_clauses` turns sentence enders into) or the end of
# the text. Anything else (`…たくない`, `…するべきではない`, `…してはいけない`) is a
# continuation that can negate, forbid or merely wish, and is not a ruling.
_END = r"(?=[\s、,。．.!?！？]|$)"

_REPLACEMENT = [
    ("やめて…で行く", r"やめ(?:て|で)[^。\n]{0,40}?(?:で|に)(?:行く|いく|する)"),
    ("に代えて", r"に代えて"),
    ("代わりに", r"代わりに"),
    ("今後は", r"今後は"),
    ("に変更", r"に(?:変更|変え)"),
    ("に置き換え", r"に置(?:き)?換え"),
    ("→", r"→"),
    ("から…へ", r"から[^。\n]{0,40}?へ(?:移|切|変|$|[^\w])"),
    ("instead of", r"\binstead of\b"),
    ("instead", r"\binstead\b(?! of)"),
    ("replace … with", r"\breplac(?:e|ed|es|ing)\b[^.\n]{0,60}?\bwith\b"),
    ("switch to", r"\bswitch(?:ed|es|ing)?\s+to\b"),
    ("now use", r"\bnow\s+(?:use|using|we use|we're using)\b"),
    ("superseded by", r"\bsuperseded by\b"),
    # Round 4's closed template in retire_lane.py carries these two as its own fixed
    # verb slots (退役して / に統合する). `Store.retire` re-runs this table as an
    # independent, nondirectional sanity receipt on whatever the template already
    # decided, so the receipt has to recognise the same vocabulary the template does —
    # otherwise every retirement using these forms would come back `kind: None` (an
    # expected gap, not a disagreement) instead of confirming what the template found.
    # The inflection is REQUIRED, positive, and must END the clause: with it optional,
    # the bare prefix `に統合` matched inside `に統合しない`; with only the next character
    # excluded, `に統合した` matched inside `に統合したくない` and `に統合する` inside
    # `に統合するべきではない`. Only the closed forms the template itself writes —
    # `に統合する` followed by punctuation, whitespace or the end — count; `_clauses`
    # has already turned sentence enders into spaces.
    ("に統合", rf"に統合(?:する|した|します){_END}"),
]

# Retirement without a successor: proves the old thing is over, nothing more.
_RETIREMENT = [
    ("やめる", r"やめ(?:る|た|よう|ます|る事|ること)?"),
    ("廃止", r"廃止|廃す|打ち切"),
    ("stop", r"\bstop(?:ped|ping|s)?\s+(?:using|doing)?"),
    ("drop", r"\bdrop(?:ped|ping|s)?\b"),
    ("retire", r"\bretir(?:e|ed|es|ing)\b"),
    ("done with", r"\bdone with\b"),
    # See the comment on "に統合" above: this is the template's other fixed verb slot,
    # and it has the same rule — a full positive inflection that ends the clause, never
    # the bare prefix (`退役しない` / `退役してはいけない` are not retirements).
    ("退役", rf"退役(?:して|した|する|します){_END}"),
]

# ── a construction read backwards ───────────────────────────────────────────
# Most constructions mark ONE of the two slots: `X に統合する` says X is the
# destination, `replace X with Y` says X is what goes. Finding the marker somewhere
# beside both names is not enough — `new-way は old-way に統合する` carries `に統合`
# and both names and says the OPPOSITE of old → new.
#
# Not a gap pattern. Three versions tried to describe what may sit between the name and
# the marker — a fixed width, a filler that stops at a particle, a filler that stops at
# punctuation — and each was a rule a longer or differently-shaped modifier walked past
# (`new-wayを基盤とする方式に代えて old-wayを使う`: the を inside the modifier ended
# the filler). The slot is read the other way round: of the two names, WHICHEVER STANDS
# NEAREST the marker on its marked side is the one in that slot, however much sits
# between. Each entry is (construction, marker, side, the memory that belongs there).
# `→` has two marked sides and two entries. A quote where the nearest name on the
# marked side is the wrong one says the reverse, and that construction no longer counts.
# Too strict only withholds proof — the safe direction — never grants it.
_SLOTS = [
    ("やめて…で行く", r"(?:で|に)(?:行く|いく|する)", "before", "new"),
    ("に代えて", r"に代えて", "before", "old"),
    ("代わりに", r"代わりに", "before", "old"),
    ("今後は", r"今後は", "after", "new"),
    ("に変更", r"に(?:変更|変え)", "before", "new"),
    ("に置き換え", r"に置(?:き)?換え", "before", "new"),
    ("→", r"→", "before", "old"),
    ("→", r"→", "after", "new"),
    ("から…へ", r"から", "before", "old"),
    ("instead of", r"\binstead of\b", "after", "old"),
    ("instead", r"\binstead\b(?! of)", "before", "new"),
    ("replace … with", r"\breplac(?:e|ed|es|ing)\b", "after", "old"),
    ("switch to", r"\bswitch(?:ed|es|ing)?\s+to\b", "after", "new"),
    ("now use", r"\bnow\s+(?:use|using|we use|we're using)\b", "after", "new"),
    ("superseded by", r"\bsuperseded by\b", "after", "new"),
    ("に統合", r"に統合", "before", "new"),
]

# A clause that changes the subject can never supply the successor.
_SHIFT = re.compile(r"(ところで|別件|余談|それはそうと|by the way|anyway|"
                    r"on another note|unrelated)", re.I)

_SENT = re.compile(r"[。．.!?！？\n]")
_WORD = re.compile(r"[0-9A-Za-z_\-]+|[぀-ヿ㐀-鿿]+")
_ASCII = re.compile(r"^[0-9A-Za-z_\-]+$")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKC", str(s or "")).lower()


def _clauses(text: str) -> str:
    """The quote with every topic-shift sentence removed (from the marker onward)."""
    keep = []
    for part in _SENT.split(text):
        if _SHIFT.search(part):
            break
        keep.append(part)
    return " ".join(keep)


def _names(text: str, *candidates: str) -> str | None:
    """The first candidate that appears in `text` as a whole name (already NFKC-low)."""
    for c in candidates:
        c = _norm(c).strip()
        if not c:
            continue
        pat = (rf"(?<![0-9A-Za-z_\-]){re.escape(c)}(?![0-9A-Za-z_\-])"
               if _ASCII.match(c) else re.escape(c))
        if re.search(pat, text):
            return c
    return None


# Words that fit any title in any store: two of them are not a name.
_STOP = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with", "that",
         "this", "it", "its", "is", "was", "are", "we", "our", "you", "how", "what",
         "から", "こと", "もの", "ため", "する", "した", "など", "よう"}


def _words(*sources: str) -> list[str]:
    """The words a title/topic contributes, deduped, order kept. Filler is dropped:
    "the" + "new" from "the new way" must not stand in for naming a memory."""
    out: list[str] = []
    for s in sources:
        for w in _WORD.findall(_norm(s)):
            if len(w) >= 2 and w not in _STOP and w not in out:
                out.append(w)
    return out


def _word_hits(text: str, words: list[str]) -> list[str]:
    hits = []
    for w in words:
        pat = (rf"(?<![0-9A-Za-z_\-]){re.escape(w)}(?![0-9A-Za-z_\-])"
               if _ASCII.match(w) else re.escape(w))
        if re.search(pat, text):
            hits.append(w)
    return hits


def _matched(text: str, table) -> list[str]:
    return [name for name, pat in table if re.search(pat, text)]


def _name_pat(slug: str, title: str) -> str:
    """A pattern for one memory by either of its names (already NFKC-lowered), with the
    same whole-name rule `_names` applies."""
    alts = []
    for c in (slug, title):
        c = _norm(c).strip()
        if c:
            alts.append(rf"(?<![0-9A-Za-z_\-]){re.escape(c)}(?![0-9A-Za-z_\-])"
                        if _ASCII.match(c) else re.escape(c))
    return "(?:" + "|".join(alts) + ")"


def _nearest(text: str, pos: int, side: str, old_pat: str, new_pat: str) -> str | None:
    """Which memory — "old" or "new" — stands nearest to `pos` on `side`, or None if
    neither is named there at all."""
    best: tuple[int, str] | None = None
    for who, pat in (("old", old_pat), ("new", new_pat)):
        for m in re.finditer(pat, text):
            if side == "before" and m.end() <= pos:
                d = pos - m.end()
            elif side == "after" and m.start() >= pos:
                d = m.start() - pos
            else:
                continue
            if best is None or d < best[0]:
                best = (d, who)
    return best[1] if best else None


def _reversed(name: str, text: str, old_pat: str, new_pat: str) -> bool:
    """Does construction `name`, in this quote, put the wrong memory in its marked slot?"""
    for n, marker, side, expect in _SLOTS:
        if n != name:
            continue
        for m in re.finditer(marker, text):
            pos = m.start() if side == "before" else m.end()
            found = _nearest(text, pos, side, old_pat, new_pat)
            if found is not None and found != expect:
                return True
    return False


def find_transition(evidence: list[dict], old: dict, new: dict) -> dict | None:
    """Did ONE [USER] quote prove `old` → `new`?

    → `{"kind": "superseded", ...}` when all three halves are in one quote,
      `{"kind": "retired-only", ...}` when the human retired the old thing but named
      no successor, and None when nothing was proven. The quote and the matched
      constructions come back as the receipt: what sentence, read how.
    """
    old_slug, old_title = str(old.get("slug") or ""), str(old.get("title") or "")
    new_slug, new_title = str(new.get("slug") or ""), str(new.get("title") or "")
    new_topic = str(new.get("topic") or "")
    if not old_slug or not new_slug or old_slug == new_slug:
        return None
    new_words = _words(new_title, new_topic)
    old_pat, new_pat = _name_pat(old_slug, old_title), _name_pat(new_slug, new_title)
    retired_only = None
    for q in (evidence or []):
        if not isinstance(q, dict) or q.get("class") != "USER":
            continue
        whole = _norm(q.get("text"))
        if not _names(whole, old_slug, old_title):
            continue                       # (i) — the old memory, by name
        text = _clauses(whole)             # a "ところで" clause is not the human's ruling
        if not _names(text, old_slug, old_title):
            continue
        # A construction whose marked slot holds the WRONG memory (`new-way は
        # old-way に統合する`) says the reverse and is not proof of old → new.
        repl = [n for n in _matched(text, _REPLACEMENT)
                if not _reversed(n, text, old_pat, new_pat)]
        retire = _matched(text, _RETIREMENT)
        if not (repl or retire):
            continue                       # (ii) — the sentence must SAY the change
        named = _names(text, new_slug, new_title)
        hits = _word_hits(text, new_words)
        # (iii) — and name the successor in it. Only a REPLACEMENT construction can
        # connect the two names: a retirement verb beside a mention of the new memory
        # (`old-way は退役した。new-way は別物。`) proves the old thing is over and
        # nothing about what follows it. Every proven-succession form has its own
        # entry in `_REPLACEMENT`; `_RETIREMENT` alone stops at `retired-only`.
        if repl and (named or len(hits) >= 2):
            return {"kind": "superseded", "old": old_slug, "new": new_slug,
                    "quote": str(q.get("text") or ""),
                    "constructions": repl + retire,
                    "new_named_by": named or hits}
        if retire and retired_only is None:
            retired_only = {"kind": "retired-only", "old": old_slug, "new": None,
                            "quote": str(q.get("text") or ""),
                            "constructions": retire}
    return retired_only
