"""Step executors and the run_flow() loop. AI-free (see CLAUDE.md I1).

_navigate and _click are the only two functions in this module permitted to
call Playwright's navigation/action primitives (CLAUDE.md I3) — `_click`
covers click, fill, *and* press despite its name, since Day 5's
check_action() must gate every state-changing action, not literal mouse
clicks alone. wait_for/extract only read, so they call Playwright directly
without going through either chokepoint.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urljoin

from playwright.sync_api import Page, sync_playwright

from app import config
from app.artifact.schema import Binding, Flow, Step, StepKind
from app.context import RunContext, new_run_id
from app.evidence import TraceWriter, save_screenshot
from app.replay import locators
from app.replay.errors import (
    BindingMissing,
    Failed,
    LocatorUnresolved,
    PolicyBlocked,
    PolicyViolation,
    RunResult,
    StepTimeout,
    Success,
)
from app.replay.locators import ResolvedElement

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (0.5, 1.0)


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
) -> ResolvedElement | None:
    # step.url is recorded relative to flow.origin (e.g. "/login.html") so a
    # flow never hardcodes an environment's host; resolve it here, since
    # page.goto() has no base URL to resolve against on its own.
    _navigate(page, urljoin(flow.origin, step.url))
    return None


def _execute_click(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    resolved = locators.resolve(
        page, step.locators, step.budget_ms, step.id, live_viewport=_current_viewport(page)
    )
    _click(page, step, resolved)
    return resolved


def _execute_fill(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    resolved = locators.resolve(page, step.locators, step.budget_ms, step.id)
    binding = _find_binding(flow, step.binding)
    value = _resolve_binding_value(binding, context, inputs, step.id)
    _click(page, step, resolved, value=value)
    return resolved


def _execute_press(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    resolved = (
        locators.resolve(page, step.locators, step.budget_ms, step.id) if step.locators else None
    )
    _click(page, step, resolved)
    return resolved


def _execute_wait_for(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    return locators.resolve(page, step.locators, step.budget_ms, step.id)


def _execute_extract(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    resolved = locators.resolve(page, step.locators, step.budget_ms, step.id)
    context.outputs[step.output] = resolved.element.inner_text().strip()
    return resolved


Executor = Callable[[Page, Step, Flow, RunContext, dict[str, str]], "ResolvedElement | None"]

EXECUTORS: dict[StepKind, Executor] = {
    StepKind.GOTO: _execute_goto,
    StepKind.CLICK: _execute_click,
    StepKind.FILL: _execute_fill,
    StepKind.PRESS: _execute_press,
    StepKind.WAIT_FOR: _execute_wait_for,
    StepKind.EXTRACT: _execute_extract,
}


def _run_step(
    page: Page, step: Step, flow: Flow, context: RunContext, inputs: dict[str, str]
) -> ResolvedElement | None:
    """Run one step, retrying on LocatorUnresolved when on_fail == "retry"
    (fresh full-budget attempts, with backoff between them). Any other
    on_fail value gets exactly one attempt; the exception propagates
    unchanged either way once attempts are exhausted."""
    attempts = MAX_RETRY_ATTEMPTS if step.on_fail == "retry" else 1
    last_error: LocatorUnresolved | None = None

    for attempt in range(1, attempts + 1):
        try:
            return EXECUTORS[step.kind](page, step, flow, context, inputs)
        except LocatorUnresolved as exc:
            last_error = exc
            if attempt < attempts:
                backoff_index = min(attempt - 1, len(RETRY_BACKOFF_SECONDS) - 1)
                time.sleep(RETRY_BACKOFF_SECONDS[backoff_index])

    raise last_error


def _run_step_and_trace(
    page: Page,
    step: Step,
    flow: Flow,
    context: RunContext,
    inputs: dict[str, str],
    tracer: TraceWriter,
    index: int,
    rung_stats: dict[str, int],
) -> None:
    tracer.write("step_start", step_index=index, step_id=step.id, kind=step.kind.value)
    step_start = time.monotonic()

    try:
        resolved = _run_step(page, step, flow, context, inputs)
    except (LocatorUnresolved, BindingMissing, StepTimeout, PolicyViolation) as exc:
        screenshot = save_screenshot(page, tracer.run_dir, index, step.id)
        tracer.write(
            "step_fail",
            level="error",
            step_index=index,
            step_id=step.id,
            kind=step.kind.value,
            duration_ms=int((time.monotonic() - step_start) * 1000),
            screenshot=screenshot,
            detail={"error_class": type(exc).__name__, "message": str(exc)},
        )
        raise

    step_duration_ms = int((time.monotonic() - step_start) * 1000)

    if resolved is not None:
        rung_stats[resolved.strategy.value] = rung_stats.get(resolved.strategy.value, 0) + 1
        tracer.write(
            "locator_resolved",
            step_index=index,
            step_id=step.id,
            locator={"strategy": resolved.strategy.value},
            attempt=resolved.rungs_attempted,
        )

    screenshot = save_screenshot(page, tracer.run_dir, index, step.id)
    tracer.write(
        "step_ok",
        step_index=index,
        step_id=step.id,
        kind=step.kind.value,
        duration_ms=step_duration_ms,
        screenshot=screenshot,
    )


def _failed_result(
    run_id: str,
    flow_id: str,
    tracer: TraceWriter,
    step_id: str | None,
    error_class: str,
    message: str,
) -> Failed:
    return Failed(
        run_id=run_id,
        flow_id=flow_id,
        step_id=step_id,
        error_class=error_class,
        message=message,
        evidence_dir=str(tracer.run_dir),
    )


def run_flow(flow: Flow, inputs: dict[str, str] | None = None) -> RunResult:
    """Execute flow end-to-end with a real Playwright browser session and
    return a RunResult. Never raises (CLAUDE.md I2): every internal
    exception is caught here and converted to the matching variant.

    TODO(Day 5.4): LocatorUnresolved on a step with on_fail == "handoff"
    should call app.intervention.handoff.request_handoff() and return
    NeedsHuman instead of Failed — deferred because that module doesn't
    exist until Day 5. Every LocatorUnresolved becomes Failed for now,
    regardless of on_fail (retry already got its chance in _run_step).
    """
    inputs = inputs or {}
    run_id = new_run_id()
    context = RunContext(run_id=run_id, flow_id=flow.id)
    tracer = TraceWriter(run_id=run_id, mode="replay")
    rung_stats: dict[str, int] = {}
    start = time.monotonic()

    tracer.write("run_start", detail={"flow_id": flow.id})

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page()
            try:
                for index, step in enumerate(flow.steps):
                    _run_step_and_trace(
                        page, step, flow, context, inputs, tracer, index, rung_stats
                    )
            finally:
                browser.close()
    except (LocatorUnresolved, BindingMissing, StepTimeout) as exc:
        return _failed_result(run_id, flow.id, tracer, exc.step_id, type(exc).__name__, str(exc))
    except PolicyViolation as exc:
        return PolicyBlocked(
            run_id=run_id,
            flow_id=flow.id,
            step_id=exc.step_id,
            rule=exc.rule,
            detail=exc.detail,
            evidence_dir=str(tracer.run_dir),
        )
    except Exception as exc:  # noqa: BLE001 - last line of defense (CLAUDE.md I2)
        return _failed_result(run_id, flow.id, tracer, None, type(exc).__name__, str(exc))

    duration_ms = int((time.monotonic() - start) * 1000)
    outputs = {name: context.outputs[name] for name in flow.outputs}
    tracer.write("run_end", detail={"status": "success"})
    return Success(
        run_id=run_id,
        flow_id=flow.id,
        outputs=outputs,
        steps_completed=len(flow.steps),
        duration_ms=duration_ms,
        evidence_dir=str(tracer.run_dir),
        rung_stats=rung_stats,
    )
