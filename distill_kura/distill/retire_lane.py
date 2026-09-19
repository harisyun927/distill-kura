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
  · it calls NO model. What decides is deterministic Python, next.

── why this file stopped reading word order (round 4, 2026-09-18) ────────────────────

Three review rounds found thirteen holes in this lane, and every one of them came from
the same place: reading DIRECTION off the order and position of words in a free-form
sentence. Negation ("やめない"), a different subject ("予備サーバーは退役した"), a
heading mention, the passive, `instead of`, and one name nested inside another all
defeat that reading — and three independent implementers, writing the fix
independently across three rounds, fell into the same holes each time. The holes were
never in any one implementation; they were in the METHOD. Free text does not carry
enough structure for position-and-order to recover direction reliably, and no amount of
patching the reading (a slot table, a span-scoping rule, a two-sentence fallback) closes
that gap for good — round 3's fix was exactly such a patch, and round 4 found new holes
in it.

So round 4 does not patch the reading again. It removes it. The lane now carries exactly
ONE closed template, matched against the WHOLE line (`re.fullmatch`, in effect):

    <old-slug> は [one sentence naming no candidate slug。] (退役して|やめて)、
    <new-slug> (に置き換える|に統合する)[。]

`<old-slug>` and `<new-slug>` are read only as the store's own slugs — never as titles,
never as a slug sitting inside a longer one — and direction is not inferred from
anything: it is simply which side of the template's own two fixed slots each name sits
in. A line that is not exactly this template proves nothing, however plausible it
reads; the person who wants anything else retired says so through `kura retire`, which
was always the explicit door. A line that names two or more candidate memories without
matching the template says so out loud (`skipped: "direction not established by the
construction"`) rather than staying silent, so the person can go use that door.

After the template decides the pair, `find_transition` is still called as an
independent sanity receipt — the same nondirectional relation `Store.retire` re-runs on
the manifest this lane writes. It is not a second vote on direction (`find_transition`
never reads direction at all; see its own docstring), only a check that nothing about
the line actively contradicts what the template found. Its own construction vocabulary
is narrower than this template's two Japanese retirement/replacement phrasings, so it
sometimes has nothing to add — that is expected, not a disagreement, and the template's
own match stands on its own.

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
from .transition import _norm, find_transition
from .watermark import Watermarks

# A stretch naming more names than this is not an instruction, it is a list (an index
# dump, a report, a pasted map). Pairing them all is quadratic and the result would be
# noise, so the lane says so and skips — loudly, never silently.
MAX_NAMES = 8

LANE_KIND = "retirement-lane"

# ── the one closed template ──────────────────────────────────────────────────────────
# Matched against the whole line, not a fragment of it. Space (half- or full-width; NFKC
# folds the latter to the former in `_norm`) may sit between a name and its particle, and
# nowhere else the pattern does not already allow for.
_WS = r" *"
_SLUG = r"[0-9a-z_\-]+"
# The middle sentence carries a reason and NOTHING else: no subject/topic/object marker
# and no comma, so a clause like "old-way は残すが、予備サーバーは役目終わり" (which
# names a THIRD thing, in a different voice) cannot slip through as "just the reason".
# It must end in the one fixed phrase 役目終わり, right before the sentence's own 。.
_REASON = r"[^はがを、\n。]*役目終わり"
_TEMPLATE = re.compile(
    rf"^(?P<old>{_SLUG}){_WS}は{_WS}"
    rf"(?:(?P<reason>{_REASON})。{_WS})?"
    rf"(?:退役して|やめて)、{_WS}"
    rf"(?P<new>{_SLUG}){_WS}"
    rf"(?:に置き換える|に統合する)"
    rf"。?$"
)

# The two verbs the template's front slot carries. A line that uses one of these AND
# names a candidate — by slug or by title — but still fails the closed template is not
# ordinary talk: it is an attempted retirement the template could not parse, and it must
# say so out loud rather than let the watermark pass over it in silence.
_VERB = re.compile(r"退役して|やめて")


def _names_slug(text: str, slug: str) -> bool:
    """Whole-token presence of `slug` in already-`_norm`-ed `text`.

    A slug sitting inside a longer slug is not a name (`new-way` inside `new-way-v2`),
    so the check needs the same word-boundary the store itself enforces on slugs.
    """
    pat = rf"(?<![0-9a-z_\-]){re.escape(slug.lower())}(?![0-9a-z_\-])"
    return re.search(pat, text) is not None


def _named_slugs(line: str, candidates: dict[str, str]) -> list[str]:
    """Every candidate SLUG this line names, by literal presence. Titles do not count
    here: this feeds MAX_NAMES (a list of names, not an instruction) and the "two bare
    slugs outside the template" refusal, both of which are about slugs the template
    itself could have pointed at."""
    low = _norm(line)
    return [slug for slug in candidates if _names_slug(low, slug)]


def _names_title(text: str, title: str) -> bool:
    """Whole-string presence of a candidate's index TITLE in already-`_norm`-ed text."""
    t = _norm(title).strip()
    return bool(t) and t in text


def _named_or_titled_slugs(line: str, candidates: dict[str, str]) -> list[str]:
    """Every candidate this line names, by slug OR by its index title. Used only to
    decide whether a line that uses the template's own verb but fails the template is a
    failed attempt (loud skip) rather than ordinary talk (silence) — a person naming the
    memory by its title deserves the same loud refusal as one naming it by slug."""
    low = _norm(line)
    out = []
    for slug, title in candidates.items():
        if _names_slug(low, slug) or _names_title(low, title):
            out.append(slug)
    return out


def _match_template(line: str, candidates: dict[str, str]) -> tuple[str, str] | None:
    """The (old, new) slugs this line's WHOLE text proves under the closed template, or
    None if it is not an exact match — a valid-looking fragment inside a longer line is
    not the person's whole ruling."""
    low = _norm(line)
    m = _TEMPLATE.match(low)
    if not m:
        return None
    by_lower = {slug.lower(): slug for slug in candidates}
    old = by_lower.get(m.group("old"))
    new = by_lower.get(m.group("new"))
    if not old or not new or old == new:
        return None                        # unknown slug, or a memory "succeeding" itself
    reason = m.group("reason")
    if reason and any(_names_slug(reason, slug) or _names_title(reason, title)
                      for slug, title in candidates.items()):
        return None                        # the reason clause is not about a third memory
    return old, new


def _accept(line: str, old: str, new: str, candidates: dict[str, str]) -> dict:
    """The template has already decided the pair; this re-runs the same nondirectional
    relation `Store.retire` re-runs on the manifest, as an independent receipt — never a
    second vote on direction, since `find_transition` does not read direction at all.

    Its construction vocabulary now includes `退役` and `に統合` (added alongside this
    template so the two independent checks use the same words), but it still does not
    cover every phrasing this template's OTHER verb slot carries (`やめて` / `に置き換
    える` are read as `retired-only`/`に置(き)?換え` already, so this is mostly belt and
    braces) — so `None` here can still happen and is an expected gap, not a disagreement,
    and the template's own match stands either way. A `kind` that is neither `None` nor
    `superseded` WOULD be a genuine
    contradiction of what the template found, and is refused rather than kept — this
    should not be reachable given the checks above, but silently trusting that is how a
    bug becomes a wrong retirement.
    """
    r = find_transition([{"class": "USER", "text": line}],
                        {"slug": old, "title": candidates.get(old, "")},
                        {"slug": new, "title": candidates.get(new, "")})
    kind = r.get("kind") if r else None
    if kind not in (None, "superseded"):
        return {"skipped": "construction matched but the independent check disagreed",
                "names": [old, new], "quote": line.strip()[:120]}
    quote = r["quote"] if r else line
    constructions = (r.get("constructions") or []) if r else []
    return {"old": old, "new": new, "quote": quote, "constructions": constructions}


def _judge_line(line: str, candidates: dict[str, str]) -> dict | None:
    """What this one line proves, refuses loudly, or says nothing about at all."""
    named = _named_slugs(line, candidates)
    if len(named) > MAX_NAMES:
        return {"skipped": "too many names", "names": len(named),
                "quote": line.strip()[:120]}
    hit = _match_template(line, candidates)
    if hit is None:
        if len(named) >= 2:
            # Two or more candidate memories named on a line that is not the template:
            # exactly the case a person should see, so they can say it with the direct
            # `kura retire` door instead of leaving the AI to guess.
            return {"skipped": "direction not established by the construction",
                    "names": named, "quote": line.strip()[:120]}
        if _VERB.search(_norm(line)):
            # The line uses the template's own verb (退役して / やめて) and names at
            # least one candidate — by slug or by title — yet still failed the closed
            # template (bad punctuation, a broken line, a verb that doesn't pair with
            # the rest). That is a failed retirement attempt, not ordinary talk, and
            # letting the watermark pass over it in silence is exactly the bug this
            # lane exists to not repeat.
            named_or_titled = _named_or_titled_slugs(line, candidates)
            if named_or_titled:
                return {"skipped": "direction not established by the construction",
                        "names": named_or_titled, "quote": line.strip()[:120]}
        return None                        # ordinary talk; logging it would bury what matters
    old, new = hit
    return _accept(line, old, new, candidates)


def proven(segments, titles: dict[str, str]) -> list[dict]:
    """Every transition the human's own words prove, one entry per (old, new).

    Pure: no store, no model, no clock. `titles` maps slug → its index title. Each LINE
    is its own instruction — the template is line-anchored, so there is no sentence
    splitting left to do and no cross-line stitching to guard against.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for seg in segments:
        if getattr(seg, "cls", None) != "USER":
            continue
        for line in (getattr(seg, "text", "") or "").splitlines():
            if not line.strip():
                continue
            hit = _judge_line(line, titles)
            if hit is None:
                continue
            if "old" in hit:
                pair = (hit["old"], hit["new"])
                if pair in seen:
                    continue
                seen.add(pair)
            out.append(hit)
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
    The pass's other write — the real watermark merge at the end of `run_lane` — asks
    the same question itself, since a pass that faced nothing never gets here.

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
        #
        # This is the pass's second write door, and it is asked the same question as
        # the first: `real` was joined from the path the store was opened on, so if
        # the directory has since been swapped for a symlink, `Watermarks(real)` would
        # mkdir `_still` and then `advance` would write `retire-watermark.json` through
        # the substitution — even on a pass that faced nothing. `_write_manifest`'s
        # check does not cover this write, and cannot: a pass with no hits never
        # reaches it.
        if not dry_run:
            if (r := store._substitution_refusal()) is not None:
                return {"ok": False, "error": r["error"], "segments": read,
                        "faced": faced, "refused": refused, "skipped": skipped}
            done = Watermarks(real)
            for k, pos in lane.read().items():
                done.advance(k, pos)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

    return {"ok": True, "segments": read, "faced": faced,
            "refused": refused, "skipped": skipped}
