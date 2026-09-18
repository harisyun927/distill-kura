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

  · **Only constructions whose word order is fixed are carried.** `に置き換え`, `→`,
    `replace … with`, `superseded by` and the retirement verbs always put the dying
    thing first; `instead of` always puts the successor first. `switch to`, `now use`,
    `代わりに`, `今後は` and a bare `instead` do NOT fix an order — "switch to new-way,
    not old-way" and "new-way を old-way の代わりに使う" both name the successor first —
    so a quote resting on one of those is refused, not guessed at. (Found by review, not
    by the dry run: the first version treated everything except `instead*` as old-first
    and would have written those two backwards.)

  · **Both names must be locatable.** Order is decided by position, so a name that is
    present by TITLE while the check looks only for the SLUG has no position at all.
    Two missing positions compare equal, which let both orientations pass and would have
    retired a pair reciprocally. `_where` looks for slug and title alike, and a name it
    cannot place is a refusal.

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

# Word order, per construction, and ONLY where the order is a property of the
# construction rather than of one example sentence. Anything not listed here is refused:
# see the module docstring for the two that read backwards.
_OLD_FIRST = {"やめて…で行く", "に代えて", "に変更", "に置き換え", "→", "から…へ",
              "replace … with", "superseded by",
              "やめる", "廃止", "stop", "drop", "retire", "done with"}
_NEW_FIRST = {"instead of"}


def _order_of(constructions) -> str | None:
    """'old-first', 'new-first', or None — None meaning the order is not established.

    A quote carrying constructions from both families, or any construction that does not
    fix an order, lands on None and is refused.
    """
    cs = list(constructions or [])
    if cs and all(c in _OLD_FIRST for c in cs):
        return "old-first"
    if cs and all(c in _NEW_FIRST for c in cs):
        return "new-first"
    return None


def _at(text: str, name: str) -> int:
    """Where `name` is named in `text` as a WHOLE name, or -1.

    A slug sitting inside a longer slug is not a name — the same rule `transition.py`
    applies. CJK titles carry no ASCII word boundary, so for those containment is the
    rule there too.
    """
    name = _norm(name).strip()
    if not name:
        return -1
    pat = (rf"(?<![0-9A-Za-z_\-]){re.escape(name)}(?![0-9A-Za-z_\-])"
           if _ASCII.match(name) else re.escape(name))
    m = re.search(pat, text)
    return m.start() if m else -1


def _where(text: str, slug: str, title: str) -> int:
    """Where this memory is named — by slug or by title, whichever comes first. -1 if
    it is not named at all. Order cannot be read off a name that has no position."""
    hits = [p for p in (_at(text, slug), _at(text, title or "")) if p >= 0]
    return min(hits) if hits else -1


def _names_in(text: str, titles: dict[str, str]) -> list[str]:
    """The store's memories this text names, by slug or by exact index title."""
    low = _norm(text)
    return [slug for slug, title in titles.items() if _where(low, slug, title) >= 0]


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
    order = _order_of(r.get("constructions"))
    if order is None:
        return {"skipped": "direction not established by the construction",
                "names": [old, new], "constructions": r.get("constructions"),
                "quote": text.strip()[:120]}
    low = _norm(text)
    po, pn = _where(low, old, titles.get(old, "")), _where(low, new, titles.get(new, ""))
    if po < 0 or pn < 0:
        return {"skipped": "a name has no position", "names": [old, new],
                "quote": text.strip()[:120]}
    if (po < pn) != (order == "old-first"):
        return None                       # the same text read backwards
    return {"old": old, "new": new, "quote": r["quote"],
            "constructions": r.get("constructions")}


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
        # The construction must live in the second sentence, beside the successor. A
        # retirement stated in the first and a bare mention in the second is not one
        # instruction, however adjacent the two are.
        if _order_of(_constructions_in(b)) != "old-first":
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


def _write_manifest(store, quote: str, source: str, key: str, gate_version: int) -> str:
    """The lane's evidence, content-addressed the same way the distiller's is.

    One USER quote, verbatim, and where it was read from. `Store.retire` re-runs its
    relation against this file, so nothing here is trusted on the strength of having
    been written by us.
    """
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
        titles = {sl: t for t, sl in store.titles().items()}

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
