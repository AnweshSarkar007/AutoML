"""Flow artifact schema: LocatorStrategy, Locator, StepKind, Binding, Step, Flow.

AI-free (see CLAUDE.md I1) — nothing here may import anthropic, openai, or
app.agent. The canonical shape and every validation rule below are specified
in CLAUDE.md §6.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LocatorStrategy(str, Enum):
    TESTID = "testid"
    ROLE_NAME = "role_name"
    LABEL = "label"
    TEXT = "text"
    CSS = "css"
    COORDINATES = "coordinates"


# Rank order the ladder is walked in; Step._check_locator_ladder enforces that
# every step's locators list is sorted according to this order.
RUNG_ORDER: tuple[LocatorStrategy, ...] = (
    LocatorStrategy.TESTID,
    LocatorStrategy.ROLE_NAME,
    LocatorStrategy.LABEL,
    LocatorStrategy.TEXT,
    LocatorStrategy.CSS,
    LocatorStrategy.COORDINATES,
)
_RUNG_RANK = {strategy: index for index, strategy in enumerate(RUNG_ORDER)}


class Viewport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    w: int
    h: int


class Locator(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    strategy: LocatorStrategy
    value: str
    role: str | None = None
    nth: int | None = None
    viewport: Viewport | None = None

    @model_validator(mode="after")
    def _check_strategy_fields(self) -> Locator:
        _require_iff(
            self.role is not None,
            self.strategy is LocatorStrategy.ROLE_NAME,
            "role",
            "strategy is role_name",
        )
        _require_iff(
            self.viewport is not None,
            self.strategy is LocatorStrategy.COORDINATES,
            "viewport",
            "strategy is coordinates",
        )
        return self


class StepKind(str, Enum):
    GOTO = "goto"
    CLICK = "click"
    FILL = "fill"
    PRESS = "press"
    WAIT_FOR = "wait_for"
    EXTRACT = "extract"


OnFail = Literal["abort", "retry", "handoff"]
BindingSource = Literal["env", "input", "extracted", "literal"]
BindingType = Literal["string", "number"]


class Binding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    source: BindingSource
    type: BindingType = "string"
    key: str | None = None
    value: str | None = None
    secret: bool = False

    @model_validator(mode="after")
    def _check_source_fields(self) -> Binding:
        _require_iff(
            self.key is not None,
            self.source in ("env", "extracted"),
            "key",
            "source is env or extracted",
        )
        _require_iff(
            self.value is not None,
            self.source == "literal",
            "value",
            "source is literal",
        )
        if self.source == "literal" and self.secret:
            raise ValueError(
                "a literal binding cannot be secret — its value is stored directly in the "
                "artifact, and I4 forbids a secret ever reaching artifacts/ (see CLAUDE.md §6)"
            )
        return self


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    kind: StepKind
    description: str
    url: str | None = None
    binding: str | None = None
    output: str | None = None
    key: str | None = None
    budget_ms: int = Field(gt=0)
    on_fail: OnFail = "abort"
    locators: list[Locator] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_kind_fields(self) -> Step:
        required_field_by_kind = {
            StepKind.GOTO: "url",
            StepKind.FILL: "binding",
            StepKind.EXTRACT: "output",
            StepKind.PRESS: "key",
        }
        for kind, field_name in required_field_by_kind.items():
            _require_iff(
                getattr(self, field_name) is not None,
                self.kind is kind,
                field_name,
                f"kind is {kind.value!r}",
            )
        return self

    @model_validator(mode="after")
    def _check_locator_ladder(self) -> Step:
        strategies = [locator.strategy for locator in self.locators]
        if len(strategies) != len(set(strategies)):
            raise ValueError(f"step {self.id!r}: locators must not repeat a strategy")
        ranks = [_RUNG_RANK[s] for s in strategies]
        if ranks != sorted(ranks):
            raise ValueError(f"step {self.id!r}: locators must be ordered by ladder rank")
        return self


class CreatedBy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["discovery", "manual"]
    run_id: str
    model: str | None = None


class Flow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    id: str
    title: str
    origin: str
    created_at: str
    created_by: CreatedBy
    bindings: list[Binding] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    steps: list[Step]

    @field_validator("schema_version")
    @classmethod
    def _check_schema_version(cls, version: int) -> int:
        if version != 1:
            raise ValueError(
                f"unsupported schema_version {version}; this build only reads version 1"
            )
        return version

    @field_validator("origin")
    @classmethod
    def _check_origin(cls, origin: str) -> str:
        parsed = urlparse(origin)
        if not parsed.scheme or not parsed.netloc or parsed.path or parsed.query:
            raise ValueError(
                f"origin must be an absolute scheme://host[:port] with no path: {origin!r}"
            )
        return origin

    @model_validator(mode="after")
    def _check_step_ids_unique(self) -> Flow:
        ids = [step.id for step in self.steps]
        if len(ids) != len(set(ids)):
            raise ValueError("step ids must be unique within a flow")
        return self

    @model_validator(mode="after")
    def _check_bindings_declared(self) -> Flow:
        binding_names = {binding.name for binding in self.bindings}
        for step in self.steps:
            if step.binding is not None and step.binding not in binding_names:
                raise ValueError(f"step {step.id!r} references undeclared binding {step.binding!r}")
        return self

    @model_validator(mode="after")
    def _check_extracted_bindings_resolve(self) -> Flow:
        output_names = {step.output for step in self.steps if step.output is not None}
        for binding in self.bindings:
            if binding.source == "extracted" and binding.key not in output_names:
                raise ValueError(
                    f"binding {binding.name!r} (source=extracted) references undeclared "
                    f"step output {binding.key!r}"
                )
        return self

    @model_validator(mode="after")
    def _check_outputs_produced(self) -> Flow:
        output_names = {step.output for step in self.steps if step.output is not None}
        for name in self.outputs:
            if name not in output_names:
                raise ValueError(f"flow output {name!r} is not produced by any step")
        return self


def _require_iff(present: bool, condition: bool, field_name: str, condition_desc: str) -> None:
    """Raise unless `present` and `condition` agree — both true or both false."""
    if condition and not present:
        raise ValueError(f"{field_name} is required when {condition_desc}")
    if present and not condition:
        raise ValueError(f"{field_name} is only valid when {condition_desc}")
