"""Step executors and the run_flow() loop. AI-free (see CLAUDE.md I1).

_navigate and _click are the only two functions in this module permitted to
call Playwright's navigation/action primitives (CLAUDE.md I3) — `_click`
covers click, fill, *and* press despite its name, since Day 5's
check_action() must gate every state-changing action, not literal mouse
clicks alone. wait_for/extract only read, so they call Playwright directly
without going through either chokepoint.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urljoin

from playwright.sync_api import Page

from app import config
from app.artifact.schema import Binding, Flow, Step, StepKind
from app.context import RunContext
from app.replay import locators
from app.replay.errors import BindingMissing
from app.replay.locators import ResolvedElement


def _navigate(page: Page, url: str) -> None:
    # TODO(Day 5.2): call app.safety.policy.check_navigation(url, allowed_origins)
    # as the first statement here, once policy.py exists — see CLAUDE.md I3.
    page.goto(url)


def _click(
    page: Page, step: Step, resolved: ResolvedElement | None, value: str | None = None
) -> None:
    # TODO(Day 5.2): call app.safety.policy.check_action(step, element) as the
    # first statement here, once policy.py exists — see CLAUDE.md I3.
    if step.kind is StepKind.CLICK:
        assert resolved is not None
        if resolved.element is not None:
            resolved.element.click()
        else:
            x, y = resolved.point
            page.mouse.click(x, y)
    elif step.kind is StepKind.FILL:
        assert resolved is not None and resolved.element is not None
        resolved.element.fill(value)
    elif step.kind is StepKind.PRESS:
        if resolved is not None and resolved.element is not None:
            resolved.element.press(step.key)
        else:
            page.keyboard.press(step.key)


def _current_viewport(page: Page) -> tuple[int, int] | None:
    size = page.viewport_size
    return (size["width"], size["height"]) if size is not None else None


def _find_binding(flow: Flow, name: str) -> Binding:
    # Flow validation already guarantees every Step.binding resolves to a
    # declared Binding (schema.py's _check_bindings_declared) — this can't
    # miss for a flow that passed validation.
    return next(binding for binding in flow.bindings if binding.name == name)


def _resolve_binding_value(
    binding: Binding, context: RunContext, inputs: dict[str, str], step_id: str
) -> str:
    if binding.source == "literal":
        return binding.value

    if binding.source == "env":
        value = config.get_env_binding_value(binding.key)
        if value is None:
            raise BindingMissing(step_id, binding.name)
        return value

    if binding.source == "input":
        if binding.name not in inputs:
            raise BindingMissing(step_id, binding.name)
        return inputs[binding.name]

    # source == "extracted"
    if binding.key not in context.outputs:
        raise BindingMissing(step_id, binding.name)
    return context.outputs[binding.key]


def _execute_goto(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    # step.url is recorded relative to flow.origin (e.g. "/login.html") so a
    # flow never hardcodes an environment's host; resolve it here, since
    # page.goto() has no base URL to resolve against on its own.
    _navigate(page, urljoin(flow.origin, step.url))


def _execute_click(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    resolved = locators.resolve(
        page, step.locators, step.budget_ms, step.id, live_viewport=_current_viewport(page)
    )
    _click(page, step, resolved)


def _execute_fill(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    resolved = locators.resolve(page, step.locators, step.budget_ms, step.id)
    binding = _find_binding(flow, step.binding)
    value = _resolve_binding_value(binding, context, inputs, step.id)
    _click(page, step, resolved, value=value)


def _execute_press(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    resolved = (
        locators.resolve(page, step.locators, step.budget_ms, step.id) if step.locators else None
    )
    _click(page, step, resolved)


def _execute_wait_for(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    locators.resolve(page, step.locators, step.budget_ms, step.id)


def _execute_extract(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> None:
    resolved = locators.resolve(page, step.locators, step.budget_ms, step.id)
    context.outputs[step.output] = resolved.element.inner_text().strip()


EXECUTORS: dict[StepKind, Callable[[Page, Step, Flow, RunContext, dict[str, str]], None]] = {
    StepKind.GOTO: _execute_goto,
    StepKind.CLICK: _execute_click,
    StepKind.FILL: _execute_fill,
    StepKind.PRESS: _execute_press,
    StepKind.WAIT_FOR: _execute_wait_for,
    StepKind.EXTRACT: _execute_extract,
}
