"""Brain pass rate with and without structured output, on the same batches.

    python -m bench.brain_json --config ~/kura/kura.toml --store main \
        --batches ~/kura/main/_still/pending --n 4 --out /tmp/brain-json-bench

Reads the shelved batches (never moves, rewrites or drops them) and asks the brain the
same SPOT question the distiller asks, once per variant:

    off          the brain exactly as configured
    json_schema  the same, with `structured = "json_schema"` (SPOT_SCHEMA enforced)
    think_low    json_schema, plus thinking ON at effort "low" (opt-in: --think)

Writes one JSON line per call to <out>/results.jsonl (the reply itself goes to
<out>/replies/, for a person to read; it is NOT a store) and prints a summary. Nothing
is written under the store: the distiller is built with `writes=False`.

A call "passes" when the reply is a readable answer: candidates `salvage` can take, or
an explicit `[]`. `quotes_ok` counts candidates with at least one quote found
character-for-character in the evidence (the gate's first test, roughly).
"""
from __future__ import annotations

import argparse
import copy
import glob
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from distill_kura.distill import Distiller, prompts                       # noqa: E402
from distill_kura.distill.gate import salvage                             # noqa: E402
from distill_kura.distill.pipeline import SPOT_SCHEMA, Segment, _is_empty_list  # noqa: E402
from distill_kura.distill.sources import as_evidence                     # noqa: E402
from distill_kura.registry import Registry                               # noqa: E402


def variant(base, name):
    e = copy.deepcopy(base)
    if name == "off":
        e.structured = ""
    elif name == "json_schema":
        e.structured = "json_schema"
    elif name == "think_low":
        e.structured = "json_schema"
        kw = dict((e.extra or {}).get("chat_template_kwargs") or {})
        kw.update({"thinking": True, "enable_thinking": True, "reasoning_effort": "low"})
        e.extra = {**(e.extra or {}), "chat_template_kwargs": kw}
    return e


def quote_ok(c, evidence):
    for q in c.get("quotes") or []:
        q = q.split("] ", 1)[1] if q.startswith("[") and "] " in q else q
        if q and q in evidence:
            return True
    return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--store", default="main")
    ap.add_argument("--batches", required=True, help="a directory of shelved batch files")
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--max-chars", type=int, default=60000,
                    help="skip batches bigger than this (keep the bench light)")
    ap.add_argument("--think", action="store_true", help="add the think_low variant")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    reg = Registry.load(os.path.expanduser(a.config))
    store = reg.stores[a.store]
    d = Distiller(reg, store, writes=False)
    files = sorted(glob.glob(os.path.join(os.path.expanduser(a.batches), "*")))
    picked = []
    for fp in files:
        try:
            rec = json.load(open(fp, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        segs = [Segment(s.get("cls", "SELF"), s.get("text", ""))
                for s in (rec.get("segments") or [])]
        size = sum(len(s.text) for s in segs)
        if segs and size <= a.max_chars:
            picked.append((os.path.basename(fp), segs, size))
    picked = picked[:a.n]
    names = ["off", "json_schema"] + (["think_low"] if a.think else [])
    os.makedirs(os.path.join(a.out, "replies"), exist_ok=True)
    system = d._sys(prompts.SPOT_SYS.format(max_items=d.max_items, language=d.language))
    rows = []
    for bname, segs, size in picked:
        evidence = as_evidence(segs)
        for name in names:
            ep = variant(d.models.brain, name)
            t0 = time.time()
            choice = ep._choice(system, evidence, 5000, 3600, None, SPOT_SCHEMA)
            dt = time.time() - t0
            m = (choice or {}).get("message") or {}
            content = (m.get("content") or "").strip()
            found = salvage(content)
            empty = bool(_is_empty_list(content))
            row = {"batch": bname, "chars_in": size, "variant": name,
                   "answered": choice is not None, "error": ep.last_error,
                   "finish": (choice or {}).get("finish_reason"),
                   "reply_chars": len(content),
                   "reasoning_chars": len((m.get("reasoning_content") or m.get("reasoning") or "")),
                   "candidates": len(found), "explicit_empty": empty,
                   "pass": bool(found) or empty,
                   "quotes_ok": sum(1 for c in found if quote_ok(c, evidence)),
                   "seconds": round(dt, 1),
                   "usage": ep.last_usage}
            rows.append(row)
            with open(os.path.join(a.out, "results.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            with open(os.path.join(a.out, "replies", f"{bname}.{name}.txt"), "w",
                      encoding="utf-8") as f:
                f.write(content)
            print(json.dumps({k: row[k] for k in ("batch", "variant", "pass", "candidates",
                                                   "quotes_ok", "finish", "seconds")}),
                  flush=True)
    for name in names:
        rs = [r for r in rows if r["variant"] == name]
        print(json.dumps({"variant": name, "calls": len(rs),
                          "pass": sum(r["pass"] for r in rs),
                          "candidates": sum(r["candidates"] for r in rs),
                          "quotes_ok": sum(r["quotes_ok"] for r in rs),
                          "seconds": round(sum(r["seconds"] for r in rs), 1)}), flush=True)


if __name__ == "__main__":
    main()
