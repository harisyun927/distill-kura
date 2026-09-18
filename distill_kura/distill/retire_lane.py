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

Two things this lane must decide that the distiller gets for free:

**Which name is dying.** `find_transition` asks only that ONE quote carry both names and
a construction that says a change; fed "OLD はやめて NEW に統合する" it answers
`superseded` for both orderings, and correctly so — the distiller supplies the direction
from outside, because the NEW memory is the one it just poured. Found by this lane's own
dry run: with no such anchor it faced the surviving memory against the dead one. Hence
`_NEW_FIRST` and the position check.

**How much text is one instruction.** Per turn is too wide: a turn retiring five memories
in five lines carries ten names in one quote, and line 1's old memory pairs with line 5's
successor. Per sentence is too narrow: the instruction that started this is written
"OLD は …役目終わり。退役して、NEW に置き換える。" — two sentences, one instruction. So the
unit is the LINE, read sentence-first: a sentence that proves something on its own is the
answer, and only a line that proves nothing and names exactly two memories is read whole,
where there is no wrong pair to fall into.

The pass always walks a throwaway copy of the marks and merges forward at the end, so a
dry run cannot eat water it was only asked to look at, and `from_start` genuinely starts
at the start instead of reporting success against a mark already parked at EOF.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone

from .sources import call_sip, source_for
from .transition import _SENT, _norm, find_transition
from .watermark import Watermarks

# A stretch naming more names than this is not an instruction, it is a list (an index
# dump, a report, a pasted map). Pairing them all is quadratic and the result would be
# noise, so the lane says so and skips — loudly, never silently.
MAX_NAMES = 8

LANE_KIND = "retirement-lane"

# Which name comes first, per construction. Every construction in `transition.py` puts
# the dying thing first — "OLD はやめて NEW に統合する", "replace OLD with NEW",
# "OLD superseded by NEW" — except the two built the other way round: "NEW instead of
# OLD". A stretch whose constructions disagree is ambiguous and is refused, because
# guessing here writes the retirement backwards.
_NEW_FIRST = {"instead of", "instead"}


def _order_of(constructions) -> str | None:
    """'old-first', 'new-first', or None when the text says both."""
    kinds = {"new-first" if c in _NEW_FIRST else "old-first"
             for c in (constructions or [])}
    return kinds.pop() if len(kinds) == 1 else None


def _names_in(text: str, titles: dict[str, str]) -> list[str]:
    """The store's memories this text names, by slug or by exact index title."""
    low = _norm(text)
    return [slug for slug, title in titles.items()
            if slug in low or (title and _norm(title) in low)]


def _prove(text: str, titles: dict[str, str], seen: set) -> list[dict]:
    """Every transition this one stretch proves, direction decided. Pure."""
    named = _names_in(text, titles)
    if len(named) > MAX_NAMES:
        return [{"skipped": "too many names", "names": len(named),
                 "quote": text.strip()[:120]}]
    low = _norm(text)
    out: list[dict] = []
    for old in named:
        for new in named:
            if old == new or (old, new) in seen:
                continue
            r = find_transition([{"class": "USER", "text": text}],
                                {"slug": old, "title": titles.get(old, "")},
                                {"slug": new, "title": titles.get(new, "")})
            if not (r and r.get("kind") == "superseded"):
                continue
            order = _order_of(r.get("constructions"))
            if order is None:
                out.append({"skipped": "ambiguous direction", "names": [old, new],
                            "quote": text.strip()[:120]})
                continue
            if (low.find(_norm(old)) < low.find(_norm(new))) != (order == "old-first"):
                continue                  # the same text read backwards
            seen.add((old, new))
            out.append({"old": old, "new": new, "quote": r["quote"],
                        "constructions": r.get("constructions")})
    return out


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
            found: list[dict] = []
            for unit in (u for u in _SENT.split(line) if u.strip()):
                found += _prove(unit, titles, seen)
            if not found and len(_names_in(line, titles)) == 2:
                found = _prove(line, titles, seen)
            out += found
    return out


def _write_manifest(store, quote: str, source: str, key: str, gate_version: int) -> str:
    """The lane's evidence, content-addressed the same way the distiller's is.

    One USER quote, verbatim, and where it was read from. `Store.retire` re-runs both
    relations against this file, so nothing here is trusted on the strength of having
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
