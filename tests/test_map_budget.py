"""The budget map's order (life-meta#1363 PR-4): pinned → recently read → newest.

Read counts steer this order and nothing else; see `distill_kura/map_budget.py` and
the exception carved into `tests/test_rooms.py`."""
from __future__ import annotations

import ast
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from distill_kura import map_budget                      # noqa: E402
from distill_kura.store import Store                     # noqa: E402

NOW = 1_800_000_000
DAY = 86400


def make(tmp_path, names=("a", "b", "c", "d", "e")):
    s = Store(name="main", path=str(tmp_path / "main"), label="main")
    s.init_files()
    for n in names:                       # remembered in this order → index order
        s.remember(n, f"memory {n}", f"body of {n}")
    return s


def reads(s, rows):
    os.makedirs(s.still, exist_ok=True)
    with open(os.path.join(s.still, "reads.jsonl"), "a", encoding="utf-8") as f:
        for at, names in rows:
            f.write(json.dumps({"at": at, "why": "recall", "n": names}) + "\n")


def test_index_slugs_follow_the_index(tmp_path):
    s = make(tmp_path)
    assert map_budget.index_slugs(s) == ["a", "b", "c", "d", "e"]


def test_without_a_read_log_the_order_is_the_old_one(tmp_path):
    s = make(tmp_path)
    p = map_budget.plan(s, {}, pinned=["b"], now=NOW)
    assert p["order"] == ["b", "e", "d", "c", "a"]       # pinned, then newest first
    assert p["reads_present"] is False and p["recent"] == [] and p["note"] == ""


def test_a_recently_read_memory_comes_forward(tmp_path):
    s = make(tmp_path)
    reads(s, [(NOW - 2 * DAY, ["a"]), (NOW - 1 * DAY, ["c"])])
    p = map_budget.plan(s, {}, now=NOW)
    assert p["order"] == ["c", "a", "e", "d", "b"]       # most recently read first
    assert p["recent"] == ["c", "a"]
    assert p["note"] == "最近参照を優先（30 日）"


def test_a_read_older_than_the_window_does_not_count(tmp_path):
    s = make(tmp_path)
    reads(s, [(NOW - 31 * DAY, ["a"]), (NOW - 29 * DAY, ["b"])])
    p = map_budget.plan(s, {}, now=NOW)
    assert p["recent"] == ["b"]
    assert p["order"] == ["b", "e", "d", "c", "a"]


def test_the_window_comes_from_the_prefill_table(tmp_path):
    s = make(tmp_path)
    reads(s, [(NOW - 10 * DAY, ["a"])])
    assert map_budget.plan(s, {"recent_read_days": 7}, now=NOW)["recent"] == []
    p = map_budget.plan(s, {"recent_read_days": 14}, now=NOW)
    assert p["recent"] == ["a"] and p["note"] == "最近参照を優先（14 日）"
    with pytest.raises(ValueError):
        map_budget.recent_read_days({"recent_read_days": -1})


def test_pinned_always_leads_even_over_a_fresh_read(tmp_path):
    s = make(tmp_path)
    reads(s, [(NOW - 60, ["e", "d"]), (NOW - 30, ["a"])])
    p = map_budget.plan(s, {}, pinned=["c", "a"], now=NOW)
    assert p["order"][:2] == ["a", "c"]                  # pinned, in index order
    assert p["order"][2:] == ["e", "d", "b"]
    assert "a" not in p["recent"]


def test_ordering_writes_nothing_and_drops_nothing(tmp_path):
    s = make(tmp_path)
    reads(s, [(NOW - DAY, ["b"])])
    before = {n: open(s.file_of(n), "rb").read() for n in s.slugs()}
    log = open(os.path.join(s.still, "reads.jsonl"), "rb").read()
    idx = s.index_text()
    p = map_budget.plan(s, {}, now=NOW)
    assert sorted(p["order"]) == sorted(s.slugs())        # a reorder, never a filter
    assert {n: open(s.file_of(n), "rb").read() for n in s.slugs()} == before
    assert open(os.path.join(s.still, "reads.jsonl"), "rb").read() == log
    assert s.index_text() == idx


def _calls_read_counts(tree):
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute) and n.func.attr == "read_counts"]


def test_read_counts_steer_only_the_budget_order():
    """The line crossed on 2026-11-10 (life-meta#1363): read counts may order the
    budget map and nothing else. Every call site in the package is listed here."""
    sites = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, "distill_kura")):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            tree = ast.parse(open(path, encoding="utf-8").read())
            for fn in ast.walk(tree):
                if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    for _ in _calls_read_counts(fn):
                        sites.append((os.path.relpath(path, ROOT).replace(os.sep, "/"),
                                      fn.name))
    # nested defs would count twice; the set is what matters
    assert set(sites) == {("distill_kura/map_budget.py", "budget_order")}, sites
    # and the module that may look is imported only by the door that serves the order
    importers = set()
    for dirpath, _, files in os.walk(os.path.join(ROOT, "distill_kura")):
        for f in files:
            if f.endswith(".py") and f != "map_budget.py":
                src = open(os.path.join(dirpath, f), encoding="utf-8").read()
                if "map_budget" in src:
                    importers.add(f)
    assert importers <= {"server.py", "registry.py"}, importers


def test_the_server_hands_out_the_order(tmp_path):
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer
    from distill_kura.registry import Registry
    from distill_kura.server import _make_handler
    from distill_kura.thinker import Models
    s = make(tmp_path)
    s.note_read(["a"], "recall")                      # stamped with the real clock
    reg = Registry(stores={"main": s}, modes={}, models=Models.from_config({}),
                   default="main")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(reg))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/map_budget?store=main&pinned=c"
        d = json.loads(urllib.request.urlopen(url).read())
    finally:
        srv.shutdown()
    assert d["order"] == ["c", "a", "e", "d", "b"]
    assert d["recent"] == ["a"] and d["recent_read_days"] == 30
    assert d["note"] == "最近参照を優先（30 日）"


def test_the_window_is_a_known_prefill_key():
    # a typo in [prefill] is refused loudly; the real key must be on the list
    from distill_kura.registry import _PREFILL_TYPES, _check_table
    assert "recent_read_days" in _PREFILL_TYPES
    _check_table("prefill", {"recent_read_days": 14}, _PREFILL_TYPES)
