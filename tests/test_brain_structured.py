"""The brain is asked for JSON, and an unreadable answer is not asked for twice.

life-meta#1363: the brain (thinking off) answered SPOT with prose — English or Chinese
notes on the material, a refusal, or an array of objects missing its braces — and the
server, which samples from a key derived from the prompt when no seed is given, gave
the same reply to the same batch on every retry. Two fixes, each held here:

- an endpoint configured with `structured` sends the caller's schema as
  `response_format`, only on the calls that carry one, and never on the plain retry;
- a batch that gets the same bad reply twice in a row is shelved for a person at once
  instead of spending the remaining attempts on the same answer.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import test_pending as tp                                     # noqa: E402
from distill_kura.distill.pending import MAX_ATTEMPTS         # noqa: E402
from distill_kura.distill.pipeline import SPOT_SCHEMA         # noqa: E402
from distill_kura.thinker import Endpoint                     # noqa: E402

PROSE = "I'll analyze this journal against the charter. Key candidates I see: ..."


# ── the request body ─────────────────────────────────────────────────────

def test_structured_off_sends_no_response_format():
    e = Endpoint(url="http://x", model="m")
    assert "response_format" not in e._body("s", "u", 10, None, "vllm", SPOT_SCHEMA)


def test_json_schema_rides_only_the_calls_that_carry_a_schema():
    e = Endpoint(url="http://x", model="m", structured="json_schema")
    body = e._body("s", "u", 10, None, "vllm", SPOT_SCHEMA)
    assert body["response_format"] == {"type": "json_schema",
                                       "json_schema": {"name": "reply", "schema": SPOT_SCHEMA}}
    assert "response_format" not in e._body("s", "u", 10, None, "vllm")   # plain text call
    # the 400 fallback is the bare minimum: a server that rejects the field still answers
    assert "response_format" not in e._body("s", "u", 10, None, "generic", SPOT_SCHEMA)


def test_json_object_is_the_plain_switch():
    e = Endpoint(url="http://x", model="m", structured="json_object", dialect="openai")
    assert e._body("s", "u", 10, None, "openai", SPOT_SCHEMA)["response_format"] == {
        "type": "json_object"}


def test_structured_is_read_from_the_config():
    e = Endpoint.from_dict({"url": "http://x", "structured": "json_schema"}, "brain")
    assert e.structured == "json_schema"


# ── the distiller hands the schema to the brain ──────────────────────────

@dataclass
class SchemaMouth(tp.FakeMouth):
    schemas: list = None

    def ask(self, system, user, max_tokens=400, timeout=None, temperature=None, schema=None):
        if self.spot is not None and tp.SPOT_PHRASE in system:
            self.schemas = (self.schemas or []) + [schema]
        return super().ask(system, user, max_tokens, timeout, temperature)


def test_spot_asks_for_the_candidate_array_when_the_brain_is_structured(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: tp.CANDIDATE)
    old = d.models.brain
    d.models.brain = SchemaMouth(url="http://fake", model="fake", name="brain",
                                 spot=old.spot, other=old.other, structured="json_schema")
    d.run(chunks=1)
    assert d.models.brain.schemas and d.models.brain.schemas[0] == SPOT_SCHEMA


# ── the same wrong answer is not asked for again ─────────────────────────

def test_the_same_bad_reply_twice_shelves_the_batch_for_a_person(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: PROSE)
    r = d.run(chunks=1)
    assert r["ok"] is False and r["reason"] == "bad_reply"
    d.run(chunks=1)                               # attempt 2: the very same reply
    rec = tp.shelf(d)[0]
    assert rec["retryable"] is False and rec["reason"] == "same bad reply"
    assert rec["attempt"] == 2 < MAX_ATTEMPTS
    assert rec["segments"]                        # kept, never dropped
    tries = len(d.models.brain.seen)
    d.run(chunks=1)
    assert len(d.models.brain.seen) == tries      # and not asked again


def test_a_different_bad_reply_is_still_retried(tmp_path):
    d = tp.distiller(tmp_path, lambda user, n: f"{PROSE} (take {n})")
    d.run(chunks=1)
    d.run(chunks=1)
    rec = tp.shelf(d)[0]
    assert rec["retryable"] is True and rec["attempt"] == 2
