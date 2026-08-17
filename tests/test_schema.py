"""Artifact schema validation and round-trip tests (CLAUDE.md §6)."""

import json

import pytest
from pydantic import ValidationError

from app.artifact.schema import Binding, Flow, Locator, Step

EXAMPLE_FLOW: dict = {
    "schema_version": 1,
    "id": "get_savings_balance",
    "title": "Read the savings account balance",
    "origin": "http://127.0.0.1:8000",
    "created_at": "2026-08-17T14:25:30Z",
    "created_by": {
        "mode": "discovery",
        "run_id": "20260817T142530Z-9f3ab1",
        "model": "claude-opus-5",
    },
    "bindings": [
        {"name": "username", "source": "env", "key": "BANK_USERNAME", "secret": False},
        {"name": "password", "source": "env", "key": "BANK_PASSWORD", "secret": True},
    ],
    "outputs": ["savings_balance"],
    "steps": [
        {
            "id": "goto_login",
            "kind": "goto",
            "description": "Open the login page",
            "url": "/login",
            "budget_ms": 8000,
            "locators": [],
        },
        {
            "id": "fill_username",
            "kind": "fill",
            "description": "Enter the username",
            "binding": "username",
            "budget_ms": 8000,
            "locators": [
                {"strategy": "testid", "value": "username"},
                {"strategy": "label", "value": "Username"},
                {"strategy": "css", "value": "#user"},
            ],
        },
        {
            "id": "read_savings_balance",
            "kind": "extract",
            "description": "Read the rendered balance",
            "output": "savings_balance",
            "budget_ms": 12000,
            "locators": [{"strategy": "testid", "value": "balance-amount"}],
        },
    ],
}


def _step(**overrides) -> dict:
    step = {"id": "s1", "kind": "click", "description": "x", "budget_ms": 1000, "locators": []}
    step.update(overrides)
    return step


def _flow(**overrides) -> dict:
    flow = {
        "schema_version": 1,
        "id": "f",
        "title": "t",
        "origin": "http://127.0.0.1:8000",
        "created_at": "2026-01-01T00:00:00Z",
        "created_by": {"mode": "manual", "run_id": "r1"},
        "steps": [],
    }
    flow.update(overrides)
    return flow


def test_round_trips_the_example_flow_byte_for_byte():
    flow = Flow.model_validate(EXAMPLE_FLOW)

    dumped = json.dumps(flow.model_dump(mode="json", exclude_none=True), indent=2)
    reparsed = Flow.model_validate_json(dumped)

    assert reparsed == flow


def test_round_trip_omits_kind_conditional_fields_not_used_by_that_step():
    flow = Flow.model_validate(EXAMPLE_FLOW)

    dumped = flow.model_dump(mode="json", exclude_none=True)
    goto_step = next(s for s in dumped["steps"] if s["id"] == "goto_login")

    assert "binding" not in goto_step
    assert "output" not in goto_step
    assert "key" not in goto_step


def test_locators_out_of_ladder_rank_order_are_rejected():
    out_of_order = [{"strategy": "css", "value": "a"}, {"strategy": "testid", "value": "b"}]
    with pytest.raises(ValidationError, match="ladder rank"):
        Step(**_step(locators=out_of_order))


def test_locators_with_a_repeated_strategy_are_rejected():
    repeated = [{"strategy": "css", "value": "a"}, {"strategy": "css", "value": "b"}]
    with pytest.raises(ValidationError, match="repeat a strategy"):
        Step(**_step(locators=repeated))


def test_a_binding_referenced_by_a_step_but_not_declared_on_the_flow_is_rejected():
    with pytest.raises(ValidationError, match="undeclared binding"):
        Flow.model_validate(
            _flow(
                steps=[
                    _step(id="s1", kind="fill", binding="nope"),
                ]
            )
        )


def test_a_future_schema_version_fails_loudly_instead_of_best_effort_parsing():
    with pytest.raises(ValidationError, match="unsupported schema_version"):
        Flow.model_validate(_flow(schema_version=2))


def test_role_name_locator_without_a_role_is_rejected():
    with pytest.raises(ValidationError, match="role is required"):
        Locator(strategy="role_name", value="Savings")


def test_coordinates_locator_without_a_viewport_is_rejected():
    with pytest.raises(ValidationError, match="viewport is required"):
        Locator(strategy="coordinates", value="612,318")


def test_role_on_a_non_role_name_locator_is_rejected():
    with pytest.raises(ValidationError, match="role is only valid"):
        Locator(strategy="css", value="#x", role="link")


@pytest.mark.parametrize(
    ("kind", "extra"),
    [
        ("goto", {}),
        ("fill", {}),
        ("extract", {}),
        ("press", {}),
    ],
)
def test_kind_conditional_field_is_required_for_its_kind(kind, extra):
    with pytest.raises(ValidationError, match="is required when kind is"):
        Step(**_step(kind=kind, **extra))


def test_a_literal_binding_cannot_be_marked_secret():
    with pytest.raises(ValidationError, match="cannot be secret"):
        Binding(name="x", source="literal", value="v", secret=True)


def test_an_env_binding_requires_a_key():
    with pytest.raises(ValidationError, match="key is required"):
        Binding(name="x", source="env")


def test_an_extracted_binding_referencing_an_undeclared_output_is_rejected():
    with pytest.raises(ValidationError, match="undeclared step output"):
        Flow.model_validate(
            _flow(
                bindings=[{"name": "acct_id", "source": "extracted", "key": "missing_output"}],
                steps=[_step(id="s1", kind="extract", output="produced_output")],
            )
        )


def test_a_flow_output_not_produced_by_any_step_is_rejected():
    with pytest.raises(ValidationError, match="is not produced by any step"):
        Flow.model_validate(_flow(outputs=["nowhere"], steps=[_step(id="s1")]))


def test_duplicate_step_ids_are_rejected():
    with pytest.raises(ValidationError, match="unique"):
        Flow.model_validate(_flow(steps=[_step(id="dup"), _step(id="dup")]))


def test_origin_with_a_path_is_rejected():
    with pytest.raises(ValidationError, match="absolute scheme"):
        Flow.model_validate(_flow(origin="http://127.0.0.1:8000/login"))
