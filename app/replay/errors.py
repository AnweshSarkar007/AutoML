"""Typed run outcomes and internal replay exceptions. AI-free (see CLAUDE.md I1).

`RunResult` is the only thing `app.replay.engine.run_flow` and
`app.intervention.handoff.request_handoff` ever return (invariant I2) — they
must never raise. The `*Error` exceptions below are strictly internal: they
signal failure *within* the engine and are always caught and converted to a
`RunResult` at those two boundaries before returning to the caller. If one of
these is ever visible outside `app/replay/` or `app/intervention/`, that is
an I2 violation.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.artifact.schema import LocatorStrategy

Status = Literal["success", "needs_human", "policy_blocked", "failed"]


class Success(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["success"] = "success"
    run_id: str
    flow_id: str
    outputs: dict[str, str]
    steps_completed: int
    duration_ms: int
    evidence_dir: str
    rung_stats: dict[str, int]


class NeedsHuman(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["needs_human"] = "needs_human"
    run_id: str
    flow_id: str
    step_id: str
    reason: str
    tried: list[LocatorStrategy]
    handoff_path: str
    evidence_dir: str


class PolicyBlocked(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["policy_blocked"] = "policy_blocked"
    run_id: str
    flow_id: str
    step_id: str
    rule: str
    detail: str
    evidence_dir: str


class Failed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["failed"] = "failed"
    run_id: str
    flow_id: str
    step_id: str | None
    error_class: str
    message: str
    evidence_dir: str


RunResult = Annotated[Success | NeedsHuman | PolicyBlocked | Failed, Field(discriminator="status")]


class ReplayError(Exception):
    """Base for internal replay failures.

    Caught and converted to a `RunResult` at the two public boundaries
    (`run_flow`, `request_handoff`) per CLAUDE.md I2. Never let one of these
    propagate past those boundaries.
    """


class LocatorUnresolved(ReplayError):
    def __init__(self, step_id: str, tried: list[LocatorStrategy]) -> None:
        self.step_id = step_id
        self.tried = tried
        tried_values = [t.value for t in tried]
        super().__init__(f"step {step_id!r}: no locator rung resolved (tried {tried_values})")


class PolicyViolation(ReplayError):
    def __init__(self, step_id: str, rule: str, detail: str) -> None:
        self.step_id = step_id
        self.rule = rule
        self.detail = detail
        super().__init__(f"step {step_id!r}: policy rule {rule!r} denied — {detail}")


class StepTimeout(ReplayError):
    def __init__(self, step_id: str, budget_ms: int) -> None:
        self.step_id = step_id
        self.budget_ms = budget_ms
        super().__init__(f"step {step_id!r}: exceeded budget of {budget_ms}ms")


class BindingMissing(ReplayError):
    def __init__(self, step_id: str, binding_name: str) -> None:
        self.step_id = step_id
        self.binding_name = binding_name
        super().__init__(f"step {step_id!r}: binding {binding_name!r} could not be resolved")
