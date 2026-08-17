"""run_flow() integration tests against a live mock bank subprocess.

Uses tests/fixtures/flow_minimal.json — a 3-step flow decoupled from any
particular business scenario — to exercise the run loop's success and
failure/retry mechanics. The real reference artifact gets its own
end-to-end test in test_replay_e2e.py.
"""

import json
import time
from pathlib import Path

from app.artifact.schema import Flow
from app.replay.engine import run_flow
from app.replay.errors import Failed, Success

FIXTURES = Path(__file__).parent / "fixtures"


def _load_minimal_flow() -> Flow:
    return Flow.model_validate_json((FIXTURES / "flow_minimal.json").read_text(encoding="utf-8"))


def test_run_flow_succeeds_and_extracts_the_expected_output(bank_server):
    result = run_flow(_load_minimal_flow())

    assert isinstance(result, Success)
    assert result.outputs == {"heading_text": "Log in"}
    assert result.steps_completed == 3
    assert result.rung_stats == {"testid": 1, "role_name": 1}


def test_run_flow_writes_evidence_under_its_own_run_id(bank_server):
    result = run_flow(_load_minimal_flow())

    evidence_dir = Path(result.evidence_dir)
    assert evidence_dir.is_dir()
    assert (evidence_dir / "trace.jsonl").is_file()

    events = [
        json.loads(line)["event"]
        for line in (evidence_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert events[0] == "run_start"
    assert events[-1] == "run_end"
    assert "step_ok" in events


def test_run_flow_fails_closed_on_a_step_with_on_fail_abort(bank_server):
    raw = json.loads((FIXTURES / "flow_minimal.json").read_text(encoding="utf-8"))
    raw["id"] = "flow_minimal_broken"
    raw["steps"][1] = {
        "id": "wait_for_form",
        "kind": "wait_for",
        "description": "Wait for something that is never there",
        "budget_ms": 600,
        "on_fail": "abort",
        "locators": [{"strategy": "testid", "value": "does-not-exist"}],
    }
    del raw["steps"][2:]  # unreachable now
    raw["outputs"] = []  # nothing still produces "heading_text" once extract is gone
    broken_flow = Flow.model_validate(raw)

    result = run_flow(broken_flow)

    assert isinstance(result, Failed)
    assert result.step_id == "wait_for_form"
    assert result.error_class == "LocatorUnresolved"


def test_run_flow_retries_before_failing_when_on_fail_is_retry(bank_server):
    raw = json.loads((FIXTURES / "flow_minimal.json").read_text(encoding="utf-8"))
    raw["id"] = "flow_minimal_retry"
    raw["steps"][1] = {
        "id": "wait_for_form",
        "kind": "wait_for",
        "description": "Wait for something that is never there",
        "budget_ms": 400,
        "on_fail": "retry",
        "locators": [{"strategy": "testid", "value": "does-not-exist"}],
    }
    del raw["steps"][2:]
    raw["outputs"] = []
    broken_flow = Flow.model_validate(raw)

    single_attempt_start = time.monotonic()
    result = run_flow(broken_flow)
    elapsed = time.monotonic() - single_attempt_start

    assert isinstance(result, Failed)
    # 3 attempts at ~0.4s each plus >=1.5s of backoff between them, vs. a
    # single on_fail="abort" attempt at ~0.4s — this is unambiguously the
    # retried path, not a fluke of one slow attempt.
    assert elapsed > 2.5
