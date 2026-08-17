"""Binding resolution unit tests (app/replay/engine.py).

Executor behavior against a live page is covered end-to-end by
test_replay_e2e.py — these tests exercise the pure resolution logic that
doesn't need a browser at all.
"""

import pytest

from app.artifact.schema import Binding
from app.context import RunContext
from app.replay.engine import _resolve_binding_value
from app.replay.errors import BindingMissing


def _context(**outputs: str) -> RunContext:
    return RunContext(run_id="r1", flow_id="f1", outputs=outputs)


def test_literal_binding_resolves_to_its_stored_value():
    binding = Binding(name="x", source="literal", value="fixed")

    assert _resolve_binding_value(binding, _context(), {}, "s1") == "fixed"


def test_input_binding_resolves_from_the_caller_supplied_inputs_dict():
    binding = Binding(name="search_term", source="input")

    value = _resolve_binding_value(binding, _context(), {"search_term": "hello"}, "s1")

    assert value == "hello"


def test_input_binding_missing_from_inputs_raises_binding_missing():
    binding = Binding(name="search_term", source="input")

    with pytest.raises(BindingMissing):
        _resolve_binding_value(binding, _context(), {}, "s1")


def test_extracted_binding_resolves_from_a_prior_steps_output():
    binding = Binding(name="acct_id", source="extracted", key="found_id")

    value = _resolve_binding_value(binding, _context(found_id="acct-123"), {}, "s1")

    assert value == "acct-123"


def test_extracted_binding_not_yet_produced_raises_binding_missing():
    binding = Binding(name="acct_id", source="extracted", key="not_produced_yet")

    with pytest.raises(BindingMissing):
        _resolve_binding_value(binding, _context(), {}, "s1")


def test_env_binding_missing_from_the_environment_raises_binding_missing(monkeypatch):
    # Neuter the real .env load — CLAUDE.md: "no test reads .env" — so this
    # only ever sees monkeypatch-controlled state, never a developer's
    # local .env file.
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    monkeypatch.delenv("SOME_UNSET_VAR", raising=False)
    binding = Binding(name="x", source="env", key="SOME_UNSET_VAR")

    with pytest.raises(BindingMissing):
        _resolve_binding_value(binding, _context(), {}, "s1")


def test_env_binding_resolves_from_the_environment(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda: None)
    monkeypatch.setenv("SOME_TEST_VAR", "env-value")
    binding = Binding(name="x", source="env", key="SOME_TEST_VAR")

    value = _resolve_binding_value(binding, _context(), {}, "s1")

    assert value == "env-value"
