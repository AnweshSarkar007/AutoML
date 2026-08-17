"""Locator ladder resolution. AI-free (see CLAUDE.md I1).

The destructive-action denylist is deliberately *not* checked here — that
is app.safety.policy's job, enforced at the single `_click` chokepoint in
engine.py (CLAUDE.md I3) regardless of which rung resolved. This module
only knows about elements, points, and timing.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from playwright.sync_api import Locator as PlaywrightLocator
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.artifact.schema import Locator as ArtifactLocator
from app.artifact.schema import LocatorStrategy, Viewport
from app.replay.errors import LocatorUnresolved


@dataclass(frozen=True)
class ResolvedElement:
    """Result of a successful ladder walk. Exactly one of `element` or
    `point` is set, depending on whether an element-based strategy or the
    trailing `coordinates` rung resolved."""

    strategy: LocatorStrategy
    rungs_attempted: int
    element: PlaywrightLocator | None = None
    point: tuple[int, int] | None = None


def rung_budget(remaining_ms: int, rungs_left: int) -> int:
    """Per-rung timeout: an even split of what's left, floored at 300ms so
    a late rung still gets a meaningful attempt rather than none at all."""
    return max(300, remaining_ms // rungs_left)


def _viewport_within_tolerance(recorded: Viewport, live: tuple[int, int]) -> bool:
    live_w, live_h = live
    width_drift = abs(live_w - recorded.w) / recorded.w
    height_drift = abs(live_h - recorded.h) / recorded.h
    return width_drift <= 0.10 and height_drift <= 0.10


def _locate(page: Page, locator: ArtifactLocator) -> PlaywrightLocator:
    match locator.strategy:
        case LocatorStrategy.TESTID:
            found = page.get_by_test_id(locator.value)
        case LocatorStrategy.ROLE_NAME:
            found = page.get_by_role(locator.role, name=locator.value)
        case LocatorStrategy.LABEL:
            found = page.get_by_label(locator.value)
        case LocatorStrategy.TEXT:
            found = page.get_by_text(locator.value, exact=True)
        case LocatorStrategy.CSS:
            found = page.locator(locator.value)
        case _:
            raise AssertionError(f"{locator.strategy} is not element-based")
    return found.nth(locator.nth) if locator.nth is not None else found


def resolve(
    page: Page,
    locators: list[ArtifactLocator],
    timeout_ms: int,
    step_id: str,
    live_viewport: tuple[int, int] | None = None,
) -> ResolvedElement:
    """Walk the ladder in order, returning on the first rung that resolves.

    Element-based rungs (testid/role_name/label/text/css) resolve by
    waiting for visibility within a per-rung budget (`rung_budget`). A
    trailing `coordinates` rung resolves to a raw point instead of an
    element, and only if `live_viewport` is within 10% of the recorded
    viewport in both dimensions (CLAUDE.md §6) — otherwise it is skipped,
    not attempted. Raises `LocatorUnresolved` once every rung has been
    tried or skipped without success.
    """
    remaining_ms = timeout_ms
    tried: list[LocatorStrategy] = []

    for index, locator in enumerate(locators):
        if remaining_ms < 300:
            break
        rungs_left = len(locators) - index
        budget = rung_budget(remaining_ms, rungs_left)
        tried.append(locator.strategy)

        if locator.strategy == LocatorStrategy.COORDINATES:
            in_tolerance = live_viewport is not None and _viewport_within_tolerance(
                locator.viewport, live_viewport
            )
            if not in_tolerance:
                continue
            x_str, y_str = locator.value.split(",")
            point = (int(x_str), int(y_str))
            return ResolvedElement(
                strategy=locator.strategy, rungs_attempted=index + 1, point=point
            )

        start = time.monotonic()
        candidate = _locate(page, locator)
        try:
            candidate.wait_for(state="visible", timeout=budget)
            return ResolvedElement(
                strategy=locator.strategy, rungs_attempted=index + 1, element=candidate
            )
        except PlaywrightTimeoutError:
            continue
        finally:
            remaining_ms -= int((time.monotonic() - start) * 1000)

    raise LocatorUnresolved(step_id, tried)
