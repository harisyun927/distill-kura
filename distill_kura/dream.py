"""`kura dream-propose` — the night's repair proposals, never the repair itself.

A person scored some memories `wrong` (written down wrongly) or `stale` (still the
ruling that was later overturned) with life-meta's kura-audit. This turns each such
(case, slug) into ONE proposal line in `<store>/_still/dream-proposals.jsonl`, with the
person's own words quoted verbatim from the conversation index (kura-audit `index` →
utter.jsonl) as the evidence. Applying a proposal is a person's act in the morning;
nothing here touches a memory, the index or anything outside that one file.

No model call (v0): the proposal is the scored answer, the verbatim quote that backs it,
and the line of the memory that disagrees — enough to decide by. A proposal whose quote
cannot be found is not written as a proposal at all; it becomes `needs-human` with the
reason, because a repair without the person's words behind it is a guess.

Re-running is idempotent: a pending line for the same (case_id, slug) is replaced, and
lines a person already moved off `pending` are kept as they are.
"""
from __future__ import annotations

import json
import os
from datetime import date as _date

from .store import Store

FILE = "dream-proposals.jsonl"
VERDICTS = ("wrong", "stale")
MIN_QUOTE = 6          # kura-audit's `short` rule: 「はい」 is not evidence of content
MAX_LINES = 3


def _read_jsonl(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    raise ValueError(f"{path}:{n}: not JSON ({e.msg})") from None
    return rows


def _as_list(v) -> list[str]:
    if not v:
        return []
    return [str(x) for x in (v if isinstance(v, list) else [v]) if str(x).strip()]


def _quote_lines(text: str, needle: str) -> str:
    """The lines of `text` the needle sits on, verbatim, at most three."""
    start = text.find(needle)
    end = start + len(needle)
    first = text.rfind("\n", 0, start) + 1
    last = text.find("\n", end)
    lines = text[first:last if last != -1 else len(text)].split("\n")
    return "\n".join(lines[:MAX_LINES])


def find_evidence(quotes: list[str], utter: list[dict]) -> list[dict]:
    """Each quote found character-for-character in a human utterance. Earliest wins."""
    rows = sorted(utter, key=lambda r: (not r.get("ts"), r.get("ts") or ""))
    out = []
    for q in quotes:
        if len(q) < MIN_QUOTE:
            continue
        for r in rows:
            text = r.get("text") or ""
            if q in text:
                src = f"{r.get('file', '?')}:{r.get('line', '?')}"
                out.append({"source": src, "quote": _quote_lines(text, q)})
                break
    return out


def _disagreeing_line(body: str, traps: list[str]) -> str | None:
    """The first line of the memory that carries one of the case's traps (the old or
    wrong answer), so the morning reader sees WHERE the memory differs."""
    for t in traps:
        for line in body.splitlines():
            if t and t in line:
                return line.strip()
    return None


def _proposal(day: str, score: dict, slug: str, case: dict, store: Store,
              utter: list[dict]) -> dict:
    base = {"date": day, "case_id": score.get("id"), "verdict": score["verdict"],
            "slug": slug}

    def human(reason: str) -> dict:
        return {**base, "kind": "needs-human", "reason": reason, "status": "pending"}

    text = store.read_exact(slug)
    if not text:
        return human(f"memory {slug!r} is not in store {store.name!r}")
    if not case:
        return human("case not found in --cases (no quote to look for)")
    quotes = _as_list(case.get("quote"))
    if not quotes:
        return human("case has no quote of the person's words")
    evidence = find_evidence(quotes, utter)
    if not evidence:
        return human("none of the case's quotes was found verbatim in the utterance index")
    answer = str(case.get("answer") or "").strip()
    _, body = Store._split(text)
    where = _disagreeing_line(body, _as_list(case.get("traps")))
    differs = f"本文の該当行: 「{where}」" if where else "本文の該当行: 特定できず（採点メモを見る）"
    note = str(score.get("note") or "").strip()
    if score["verdict"] == "stale":
        kind = "annotate"
        proposed = f"覆り: 今の裁定は「{answer}」。{differs}。この記憶は覆り前のまま。"
    else:
        kind = "replace"
        proposed = f"正: {answer}。{differs} を置き換える。"
    if note:
        proposed += f"（採点メモ: {note}）"
    return {**base, "kind": kind, "proposed": proposed, "evidence": evidence,
            "status": "pending"}


def propose(store: Store, scores_path: str, utter_path: str,
            cases_path: str | None = None, day: str | None = None) -> dict:
    """Write proposals for every wrong/stale score; return what happened."""
    day = day or _date.today().isoformat()
    scores = [s for s in _read_jsonl(scores_path) if s.get("verdict") in VERDICTS]
    cases = {c.get("id"): c for c in _read_jsonl(cases_path)} if cases_path else {}
    utter = _read_jsonl(utter_path)
    new = []
    for s in scores:
        slugs = _as_list(s.get("slugs"))
        if not slugs:
            new.append({"date": day, "case_id": s.get("id"), "verdict": s["verdict"],
                        "slug": None, "kind": "needs-human",
                        "reason": "score names no slug", "status": "pending"})
        for slug in slugs:
            new.append(_proposal(day, s, slug, cases.get(s.get("id"), {}), store, utter))

    path = os.path.join(store.still, FILE)
    keys = {(p["case_id"], p["slug"]) for p in new}
    kept = []
    if os.path.exists(path):
        kept = [p for p in _read_jsonl(path)
                if not (p.get("status") == "pending"
                        and (p.get("case_id"), p.get("slug")) in keys)]
    if new:
        os.makedirs(store.still, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            for p in kept + new:
                fh.write(json.dumps(p, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    kinds: dict[str, int] = {}
    for p in new:
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    return {"path": path, "scored": len(scores), "written": len(new), "kinds": kinds,
            "kept": len(kept)}
