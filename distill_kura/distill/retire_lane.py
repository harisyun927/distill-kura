"""The retirement lane — "stop X, use Y" must not depend on a model finding it new.

A retirement is a person CANCELLING something, not a discovery. The ordinary pass is
built for discoveries: it drinks only stretches worth a model's time (`MIN_DRINK`), and
a brain then picks the few candidates that are new or surprising. A sentence that
retires a memory is neither large nor new — the successor usually already says what the
sentence says — so it loses on both counts.

Measured, 2026-09-17/18 (Issue #754 in the operator's tracker): one instruction naming
five memories and their successors was said three times and retired nothing. Cut down to
that instruction alone the material was 808 characters, and `MIN_DRINK = 6_000` dropped
it before any model saw it — the watermark did not move and the pass answered
`nothing worth drinking`. The gate was never the problem: run against `find_transition`,
those same five sentences prove all five transitions on the first try.

So this lane carries exactly that traffic and nothing else:

  · it reads with its OWN watermark, so it can never consume material the distiller
    needs, and the distiller can never consume material it needs;
  · it has NO minimum — one sentence is a whole meal here;
  · it calls NO model. The lane is `find_transition`, which is deterministic Python.
    This is not a shortcut around the gate; it is the gate, reached sooner.

`find_transition` is NONDIRECTIONAL by design — it asks only that ONE quote carry both
names and a construction that says a change, and `Store.retire` re-runs that same
nondirectional relation. The distiller never needs more, because the NEW memory is the
one it just poured: direction comes from outside, set by code. A lane reading a journal
has no such anchor and must establish direction itself, and everything it writes is
accepted by `Store.retire` on the strength of that. So the whole design here is about
refusing rather than guessing:

  · **Only constructions whose word order is fixed are carried, and "fixed" is decided
    per construction, against ITS OWN SPAN — not once for the whole quote.** `に置き換え`,
    `→`, `replace … with`, `superseded by` and the Japanese retirement verbs (`やめる`,
    `廃止`) always stand the two names in the same places relative to the construction;
    `instead of` always reverses them. `switch to`, `now use`, `代わりに`, `今後は`, a bare
    `instead`, and — this is round 2's finding — the ENGLISH retirement verbs (`stop`,
    `drop`, `retire`, `done with`) do NOT fix an order: Japanese `やめる` puts the dying
    thing BEFORE the verb (`old-way をやめる`) but English puts it AFTER (`retire
    old-way`), so folding both into one "old-first" family read "Use new-way; retire
    old-way." backwards and would have retired the survivor. A quote resting only on a
    construction outside the table is refused, not guessed at. (Round 1 found `switch
    to` / `now use` / `代わりに` / `今後は` / bare `instead`; round 2 found the English
    retirement verbs, plus that a matched construction only speaks for the occurrences
    beside its own span — see `_construction_spans` / `_slot`.)

  · **Both names must be locatable, at EVERY occurrence, not just the first.** Order is
    decided by position, so a name that is present by TITLE while the check looks only
    for the SLUG has no position at all — two missing positions compare equal, which let
    both orientations pass and would have retired a pair reciprocally. And a name that
    the construction's span sits beside may not be its FIRST mention in the quote: round
    2's other finding was a heading clause ("Regarding new-way: stop old-way and replace
    it with new-way.") whose leading, unrelated mention of the successor came before the
    construction that actually fixed the order — reading "first occurrence" made the
    pair look reversed. `_where_all` returns every occurrence of slug and title alike,
    and a name with none of them is a refusal.

  · **Two names in a line are not a transition.** Sentence by sentence is the safe read;
    the instruction that started this is written "OLD は …役目終わり。退役して、NEW に
    置き換える。" — two sentences, one instruction — so a line that proves nothing
    sentence-wise gets ONE more chance, in the narrowest shape that carries it: the two
    sentences that name a memory WITH NOTHING NAMED BETWEEN THEM, the first naming only
    the old, the second naming only the new AND carrying the construction.
    "old-way is retired. new-way is nice." fails that (the construction is in the first
    sentence), where a plain two-names-in-the-line fallback would have stitched them
    together and retired old-way. "Adjacent" was too strict to be that rule: `§12.5`
    ends a sentence at its decimal point, which put one real instruction three units
    apart and lost it.

Nothing is written on a frozen store, including the lane's own watermark: the policy is
asked before the first byte, not by `Store.retire` after the evidence file already
exists.

A dry run walks a throwaway copy of the marks, so looking does not consume, and
`from_start` genuinely starts at the start instead of reporting success against a mark
already parked at EOF.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone

from ..store import FROZEN
from .sources import call_sip, source_for
from .transition import (_ASCII, _REPLACEMENT, _RETIREMENT, _SENT, _norm,
                         find_transition)
from .watermark import Watermarks

# A stretch naming more names than this is not an instruction, it is a list (an index
# dump, a report, a pasted map). Pairing them all is quadratic and the result would be
# noise, so the lane says so and skips — loudly, never silently.
MAX_NAMES = 8

LANE_KIND = "retirement-lane"

# Direction is a property of ONE MATCHED CONSTRUCTION's span, not of the quote as a
# whole. Round 2 finding 1: a bare retirement verb does not fix word order the way the
# module docstring claimed — English puts the object AFTER the verb (`retire old-way`),
# Japanese `やめる` puts it BEFORE (`old-way をやめる`) — so folding both into one
# "old-first" family made `retire old-way` (successor named first) read as old-first
# and would have retired the survivor. Round 2 finding 2: a construction only pins down
# where the two names stand RELATIVE TO ITS OWN SPAN; reading "the first occurrence in
# the quote" let a successor named again in an unrelated heading clause stand in for
# the occurrence that actually sits next to the construction.
#
# Each entry: construction name → (old's slot, new's slot). A slot is "before" (name's
# occurrence starts before the span), "inside" (occurrence overlaps the span) or
# "after" (occurrence starts at or after the span ends). Anything not listed here does
# not fix an order and is refused — see the module docstring for the constructions that
# read backwards depending on the sentence around them.
_SLOT_TABLE: dict[str, tuple[str, str]] = {
    "やめる": ("before", "after"),
    "廃止": ("before", "after"),
    "に代えて": ("before", "after"),
    "→": ("before", "after"),
    "superseded by": ("before", "after"),
    "に置き換え": ("before", "before"),
    "に変更": ("before", "before"),
    "replace … with": ("inside", "after"),
    "やめて…で行く": ("before", "inside"),
    "から…へ": ("before", "inside"),
    "instead of": ("after", "before"),
}

# `に置き換え` / `に変更` put BOTH names before the construction (「old を new に変更」),
# so the slot table alone cannot tell old from new — a slot match by itself would also
# accept the pair reversed. These two need the extra "old's occurrence precedes new's"
# check that the other constructions get for free from asymmetric slots.
_ORDERED_BY_POSITION = {"に置き換え", "に変更"}


def _at_all(text: str, name: str) -> list[int]:
    """Every position `name` is named in `text` as a WHOLE name.

    A slug sitting inside a longer slug is not a name — the same rule `transition.py`
    applies. CJK titles carry no ASCII word boundary, so for those containment is the
    rule there too. All occurrences, not just the first: a construction's span can sit
    next to a LATER mention while an earlier, unrelated one is what "first" would find.
    """
    name = _norm(name).strip()
    if not name:
        return []
    pat = (rf"(?<![0-9A-Za-z_\-]){re.escape(name)}(?![0-9A-Za-z_\-])"
           if _ASCII.match(name) else re.escape(name))
    return [m.start() for m in re.finditer(pat, text)]


def _where_all(text: str, slug: str, title: str) -> list[int]:
    """Every position this memory is named, by slug or by title. Empty if it is not
    named at all — order cannot be read off a name that has no position."""
    return sorted(_at_all(text, slug) + _at_all(text, title or ""))


def _construction_spans(text: str, allowed: set[str]) -> list[tuple[str, tuple[int, int]]]:
    """Every occurrence of a construction in `allowed`, with its span.

    Read off `transition.py`'s own tables rather than a second copy of the patterns: a
    construction added there must not silently mean nothing here. All occurrences, in
    case the same construction fires twice in one quote.
    """
    out: list[tuple[str, tuple[int, int]]] = []
    for name, pat in (*_REPLACEMENT, *_RETIREMENT):
        if name not in allowed:
            continue
        for m in re.finditer(pat, text):
            out.append((name, m.span()))
    return out


def _slot(pos: int, span: tuple[int, int]) -> str:
    """Where `pos` stands relative to `span`: before it, inside it, or after it."""
    start, end = span
    if pos < start:
        return "before"
    if pos < end:
        return "inside"
    return "after"


def _names_in(text: str, titles: dict[str, str]) -> list[str]:
    """The store's memories this text names, by slug or by exact index title."""
    low = _norm(text)
    return [slug for slug, title in titles.items() if _where_all(low, slug, title)]


def _accept(text: str, old: str, new: str, titles: dict[str, str]) -> dict | None:
    """The proof that THIS text retires `old` in favour of `new`, or None.

    `find_transition` decides whether a transition is said at all; this decides whether
    it is said in that direction, and refuses when it cannot tell.
    """
    r = find_transition([{"class": "USER", "text": text}],
                        {"slug": old, "title": titles.get(old, "")},
                        {"slug": new, "title": titles.get(new, "")})
    if not (r and r.get("kind") == "superseded"):
        return None
    matched = r.get("constructions") or []
    ordering = {c for c in matched if c in _SLOT_TABLE}
    if not ordering:
        return {"skipped": "direction not established by the construction",
                "names": [old, new], "constructions": matched,
                "quote": text.strip()[:120]}
    low = _norm(text)
    old_pos = _where_all(low, old, titles.get(old, ""))
    new_pos = _where_all(low, new, titles.get(new, ""))
    if not old_pos or not new_pos:
        return {"skipped": "a name has no position", "names": [old, new],
                "quote": text.strip()[:120]}
    # Every occurrence of every ordering construction is a separate chance to satisfy
    # the pair — one construction, one span, but names can occur several times and only
    # the occurrence beside THIS span speaks for it (see the module-level comment on
    # `_at_all`).
    for name, span in _construction_spans(low, ordering):
        old_slot, new_slot = _SLOT_TABLE[name]
        for po in old_pos:
            if _slot(po, span) != old_slot:
                continue
            for pn in new_pos:
                if _slot(pn, span) != new_slot:
                    continue
                if name in _ORDERED_BY_POSITION and not (po < pn):
                    continue
                return {"old": old, "new": new, "quote": r["quote"],
                        "constructions": matched}
    return None                           # no occurrence pair fits any matched slot


def _prove(text: str, titles: dict[str, str], seen: set) -> list[dict]:
    """Every transition this one stretch proves, direction decided. Pure."""
    named = _names_in(text, titles)
    if len(named) > MAX_NAMES:
        return [{"skipped": "too many names", "names": len(named),
                 "quote": text.strip()[:120]}]
    out: list[dict] = []
    for old in named:
        for new in named:
            if old == new or (old, new) in seen:
                continue
            hit = _accept(text, old, new, titles)
            if hit is None:
                continue
            if "old" in hit:
                seen.add((old, new))
            out.append(hit)
    return out


def _prove_window(units: list[str], titles: dict[str, str], seen: set) -> list[dict]:
    """The one widening allowed: the two sentences that name a memory with nothing named
    between them, one name each, and the construction in the second. See the module
    docstring for why nothing wider is safe."""
    out: list[dict] = []
    named = [(i, _names_in(u, titles)) for i, u in enumerate(units)]
    speaking = [(i, ns) for i, ns in named if ns]        # units that name anything
    for (ia, na), (ib, nb) in zip(speaking, speaking[1:]):
        # Nothing is named between them — that is what `speaking` being consecutive
        # means, and it is the guarantee the adjacency test was reaching for.
        if len(na) != 1 or len(nb) != 1 or na[0] == nb[0]:
            continue
        b = units[ib]
        old, new = na[0], nb[0]
        if (old, new) in seen:
            continue
        # The construction must live in the second sentence, beside the successor, and
        # it must be one that fixes an order at all. A retirement stated in the first
        # and a bare mention in the second is not one instruction, however adjacent the
        # two are; nor is a construction (`switch to`, bare `instead`, …) that this
        # sentence alone could not settle a direction with.
        if not any(c in _SLOT_TABLE for c in _constructions_in(b)):
            continue
        hit = _accept(" ".join(units), old, new, titles)
        if hit is None:
            continue
        if "old" in hit:
            seen.add((old, new))
        out.append(hit)
    return out


def _constructions_in(text: str) -> list[str]:
    """Which constructions this sentence carries, named the way the relation names them.

    Read off `transition.py`'s own tables rather than a second copy of the patterns: a
    construction added there must not silently mean nothing here.
    """
    low = _norm(text)
    return [name for name, pat in (*_REPLACEMENT, *_RETIREMENT)
            if re.search(pat, low)]


def proven(segments, titles: dict[str, str]) -> list[dict]:
    """Every transition the human's own words prove, one entry per (old, new).

    Pure: no store, no model, no clock. `titles` maps slug → its index title.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for seg in segments:
        if getattr(seg, "cls", None) != "USER":
            continue
        for line in (getattr(seg, "text", "") or "").splitlines():
            if not line.strip():
                continue
            units = [u for u in _SENT.split(line) if u.strip()]
            found: list[dict] = []
            for unit in units:
                found += _prove(unit, titles, seen)
            if not any("old" in h for h in found):
                found += _prove_window(units, titles, seen)
            out += found
    return out


def _write_manifest(store, quote: str, source: str, key: str,
                     gate_version: int) -> str | None:
    """The lane's evidence, content-addressed the same way the distiller's is, or None
    if the store no longer resolves to the directory it was opened on.

    `Store.retire` re-runs `_substitution_refusal()` too, but by the time it does the
    evidence file would already be on disk — through whatever `store.path` now points
    at, since a symlink swap makes `os.path.join(store.path, ...)` write outside the
    store without any error along the way. Checking here, before the first byte, is the
    only place that can refuse before that write happens; `Store.retire`'s copy of the
    same check is defence for the direct `retire` CLI path, not redundant with this one.

    One USER quote, verbatim, and where it was read from. `Store.retire` re-runs its
    relation against this file, so nothing here is trusted on the strength of having
    been written by us.
    """
    if store._substitution_refusal() is not None:
        return None
    manifest = {
        "gate_version": gate_version,
        "kind": LANE_KIND,
        "source_key": key,
        "source_file": os.path.basename(source),
        "evidence_classes": ["USER"],
        "quotes": [{"class": "USER", "text": quote}],
        "created_at": datetime.now(timezone.utc).isoformat()[:19] + "Z",
    }
    blob = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=1)
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    path = os.path.join(store.path, "_evidence", f"{digest}.json")
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + f".tmp.{os.getpid()}"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(blob)
        os.replace(tmp, path)
    return digest


def _candidates(store) -> dict[str, str]:
    """slug → its index title (or "" if it has none), for every slug the store holds.

    `store.titles()` is title → slug, so two memories sharing one index title collapse
    to a single dict entry and the other's slug never appears as a key — it becomes
    permanently unreachable as an `old` or `new` here, while the watermark still walks
    past whatever instruction named it. `slug_set()` is the universe this lane must
    face; a title is only an extra way to be named, layered on afterward.
    """
    by_slug = {sl: t for t, sl in store.titles().items()}
    return {slug: by_slug.get(slug, "") for slug in store.slug_set()}


def _start_marks(scratch: str, real: str, dis, files: list[str],
                 from_start: bool) -> Watermarks:
    """The marks this pass walks: a copy, never the real file.

    `from_start` leaves it empty (start at zero). Otherwise it inherits whatever the lane
    already read, and a journal the lane has never seen starts where the DISTILLER has
    already read to — a first run must not walk a year of journals and face memories
    against sentences whose world is long gone. History is opt-in.
    """
    path = os.path.join(scratch, "marks.json")
    lane = Watermarks(path)
    if from_start:
        return lane
    if os.path.exists(real):
        shutil.copyfile(real, path)
    cur, theirs = lane.read(), dis.marks.read()
    for p in files:
        src = source_for(p)
        if src and src.key(p) not in cur and src.key(p) in theirs:
            lane.advance(src.key(p), theirs[src.key(p)])
    return lane


def run_lane(dis, session: str | None = None, *, dry_run: bool = False,
             from_start: bool = False) -> dict:
    """One pass of the retirement lane over whatever is new. → what it faced, and why not.

    `dis` is a Distiller: the lane borrows its journals, its store and its chunk size,
    and shares nothing else — above all not its watermark.
    """
    from .pipeline import GATE_VERSION

    store = dis.store
    # Asked before the first byte. `Store.retire` refuses a frozen store too, but by then
    # the evidence file is already on disk and the watermark is about to move — a store
    # whose policy promises that nothing may write would have been written to twice.
    if getattr(store, "write_policy", None) == FROZEN:
        return {"ok": False, "error": f"store '{store.name}' is frozen: nothing may write",
                "segments": 0, "faced": [], "refused": [], "skipped": []}

    files = dis.files(session)
    real = os.path.join(dis.still, "retire-watermark.json")
    scratch = tempfile.mkdtemp(prefix="kura-retire-lane-")
    faced, refused, skipped, read = [], [], [], 0
    try:
        lane = _start_marks(scratch, real, dis, files, from_start)
        titles = _candidates(store)

        while True:
            c = lane.claim(files, dis.chunk_chars, 1)   # 1: no meal is too small here
            if not c:
                break
            k = c.source.key(c.path)
            if c.scan_pending:
                lane.advance(k, c.end)
                continue
            segs, nxt = call_sip(c.source, c.path, c.start, dis.chunk_chars,
                                 bound_end=c.end)
            lane.advance(k, nxt)
            read += len(segs)
            for hit in proven(segs, titles):
                if "skipped" in hit:
                    skipped.append(hit)
                    continue
                if dry_run:
                    faced.append({**hit, "dry_run": True})
                    continue
                hexd = _write_manifest(store, hit["quote"], c.path, k, GATE_VERSION)
                if hexd is None:
                    refused.append({"old": hit["old"], "new": hit["new"],
                                    "error": store._substitution_refusal()["error"]})
                    continue
                r = store.retire(hit["old"], hit["new"], hexd)
                if r.get("ok"):
                    faced.append({"old": hit["old"], "new": hit["new"],
                                  "manifest": hexd, "already": bool(r.get("already"))})
                else:
                    refused.append({"old": hit["old"], "new": hit["new"],
                                    "error": r.get("error")})

        # Only a pass that actually wrote gets to move the real marks, and it moves them
        # forward only (`advance` takes a max), so a narrower `--session` run can never
        # pull a wider one backwards.
        if not dry_run:
            done = Watermarks(real)
            for k, pos in lane.read().items():
                done.advance(k, pos)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    return {"ok": True, "segments": read, "faced": faced,
            "refused": refused, "skipped": skipped}
