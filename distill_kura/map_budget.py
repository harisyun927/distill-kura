"""The ORDER of the budget map — the one place read counts may steer anything.

A host that cannot wear the whole map (a SessionStart hook with a 10,000-character
ceiling, say) wears a *budget map*: the same `/prefill` lines, cut down to what fits.
Which lines survive the cut is an order, and until now the order was "pinned first,
then newest first by index position". This module answers one question for such a
host: in what order should the lines be offered to the cut?

    pinned (index order)
    → read within the last `recent_read_days` days, most recently read first
    → everything else, newest first (index position from the end)

**The line this module crosses, and how far.** Elsewhere in this codebase read counts
are diagnostics and are never consulted for a decision (`tests/test_rooms.py`,
`richness.py`). The household's operator decided (2026-11-10, life-meta#1363 PR-4) to
cross that line for the budget map's ORDER and nothing else. So:

- `budget_order` is the only function in the package that calls `read_counts()` for
  anything but a diagnostic, and a test pins it there.
- Nothing here retires, drops, garages, ranks recall, or feeds `tend`. A memory that
  falls off the budget map is still on the full map (`kura_map` / `/prefill`), still
  readable by name, still found by recall. Its body is untouched; nothing is written.
- No reads log (`_still/reads.jsonl` absent) → the order is exactly the old one, and
  the plan says so (`reads_present: false`, no note), so the host renders as before.

The default window lives in ONE place (`DEFAULT_RECENT_READ_DAYS`); a store changes it
with `recent_read_days` in its `[prefill]` table.
"""
from __future__ import annotations

import re
import time

from .store import Store

DEFAULT_RECENT_READ_DAYS = 30

# `- [title](slug.md) — trigger`: the slug is what the host matches on, too.
_SLUG = re.compile(r"\]\(([^)\s]+)\.md\)")


def recent_read_days(cfg: dict | None = None) -> float:
    """The window from a `[prefill]` table, or the default. Garbage raises."""
    v = (cfg or {}).get("recent_read_days", DEFAULT_RECENT_READ_DAYS)
    days = float(v)
    if days < 0:
        raise ValueError(f"recent_read_days must be >= 0, got {v!r}")
    return days


def index_slugs(store: Store) -> list[str]:
    """Slugs in the order the canonical index lists them (oldest first, as appended)."""
    out, seen = [], set()
    for line in store.index_text().splitlines():
        if not line.startswith("- ["):
            continue
        m = _SLUG.search(line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def budget_order(store: Store, slugs: list[str], pinned: list[str] | tuple[str, ...] = (),
                 days: float = DEFAULT_RECENT_READ_DAYS,
                 now: float | None = None) -> tuple[list[str], list[str], bool]:
    """→ (order, recent, reads_present). `slugs` is in index order (oldest first).

    The ONLY decision in the package allowed to look at the read log, and the only
    thing it decides is the order a budget map offers its lines to the cut."""
    now = time.time() if now is None else now
    pin = set(pinned)
    order = [s for s in slugs if s in pin]
    last_read = {n: at for n, (_c, at) in store.read_counts().items()}
    present = bool(last_read)
    cutoff = now - days * 86400
    taken = set(order)
    recent = [s for s in slugs if s not in taken and last_read.get(s, 0) >= cutoff
              and s in last_read]
    # most recently read first; ties keep the newer index position first
    pos = {s: i for i, s in enumerate(slugs)}
    recent.sort(key=lambda s: (-last_read[s], -pos[s]))
    order += recent
    taken.update(recent)
    order += [s for s in reversed(slugs) if s not in taken]
    return order, recent, present


def plan(store: Store, cfg: dict | None = None, pinned: list[str] | tuple[str, ...] = (),
         now: float | None = None) -> dict:
    """What `/map_budget` returns: the order plus the one line the host shows so a
    reader knows why these lines and not others."""
    days = recent_read_days(cfg)
    order, recent, present = budget_order(store, index_slugs(store), pinned,
                                          days=days, now=now)
    d = int(days) if float(days).is_integer() else days
    return {"store": store.name, "recent_read_days": d, "reads_present": present,
            "order": order, "recent": recent,
            "note": f"最近参照を優先（{d} 日）" if present else ""}
