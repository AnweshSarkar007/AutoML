"""Shared pytest fixtures.

Adds mock-bank/ to sys.path so `backend.app` imports directly — the hyphen
in mock-bank/ makes it invalid as a dotted package name, so this sys.path
shim (rather than a real import) is the sanctioned way in, per CLAUDE.md §2.1.
"""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mock-bank"))


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser: Browser) -> Iterator[Page]:
    page = browser.new_page()
    yield page
    page.close()
