"""Locator ladder resolver tests (app/replay/locators.py)."""

import pytest

from app.artifact.schema import Locator
from app.replay.errors import LocatorUnresolved
from app.replay.locators import ResolvedElement, resolve, rung_budget


@pytest.mark.parametrize(
    ("remaining_ms", "rungs_left", "expected"),
    [
        (9000, 3, 3000),
        (1000, 5, 300),  # floored at 300 even though 1000 // 5 == 200
        (900, 1, 900),  # the last rung gets everything that's left
        (301, 1, 301),
    ],
)
def test_rung_budget_splits_remaining_time_evenly_with_a_300ms_floor(
    remaining_ms, rungs_left, expected
):
    assert rung_budget(remaining_ms, rungs_left) == expected


@pytest.mark.browser
def test_resolve_returns_on_the_first_matching_rung(page):
    page.set_content('<button data-testid="submit-btn">Submit</button>')

    result = resolve(
        page,
        [Locator(strategy="testid", value="submit-btn")],
        timeout_ms=2000,
        step_id="s1",
    )

    assert isinstance(result, ResolvedElement)
    assert result.strategy == "testid"
    assert result.rungs_attempted == 1
    assert result.element.inner_text() == "Submit"


@pytest.mark.browser
def test_resolve_falls_through_to_css_when_testid_is_absent(page):
    page.set_content('<button id="submit-btn">Submit</button>')

    result = resolve(
        page,
        [
            Locator(strategy="testid", value="wrong-id"),
            Locator(strategy="css", value="#submit-btn"),
        ],
        timeout_ms=1000,
        step_id="s1",
    )

    assert result.strategy == "css"
    assert result.rungs_attempted == 2


@pytest.mark.browser
def test_resolve_raises_locator_unresolved_when_every_rung_fails(page):
    page.set_content("<p>nothing matches</p>")

    with pytest.raises(LocatorUnresolved) as exc_info:
        resolve(
            page,
            [Locator(strategy="testid", value="missing")],
            timeout_ms=600,
            step_id="s1",
        )

    assert exc_info.value.step_id == "s1"
    assert exc_info.value.tried == ["testid"]


@pytest.mark.browser
def test_resolve_accepts_coordinates_within_viewport_tolerance(page):
    page.set_content("<p>irrelevant</p>")
    locator = Locator(strategy="coordinates", value="100,200", viewport={"w": 1280, "h": 720})

    result = resolve(page, [locator], timeout_ms=1000, step_id="s1", live_viewport=(1300, 720))

    assert result.strategy == "coordinates"
    assert result.point == (100, 200)


@pytest.mark.browser
def test_resolve_skips_coordinates_outside_viewport_tolerance(page):
    page.set_content("<p>irrelevant</p>")
    locator = Locator(strategy="coordinates", value="100,200", viewport={"w": 1280, "h": 720})

    with pytest.raises(LocatorUnresolved):
        resolve(page, [locator], timeout_ms=600, step_id="s1", live_viewport=(400, 720))
