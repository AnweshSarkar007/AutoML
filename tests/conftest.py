"""Shared pytest fixtures.

Adds mock-bank/ to sys.path so `backend.app` imports directly — the hyphen
in mock-bank/ makes it invalid as a dotted package name, so this sys.path
shim (rather than a real import) is the sanctioned way in, per CLAUDE.md §2.1.
"""

import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from urllib.error import URLError

import pytest
from playwright.sync_api import Browser, Page, sync_playwright

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mock-bank"))

# Matches `make bank` and the origin hardcoded into the committed reference
# artifact (artifacts/get_savings_balance.json) — Flow.origin has no
# per-test override, so anything that replays a real flow needs the bank on
# this exact port.
BANK_SERVER_URL = "http://127.0.0.1:8000"


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


@pytest.fixture
def tmp_run(tmp_path: Path) -> Path:
    """A throwaway root directory for evidence/artifact writes in tests, so
    tests never touch the real evidence/ or artifacts/ trees."""
    return tmp_path


def _wait_until_ready(url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)  # noqa: S310 - fixed localhost URL, test-only
            return
        except URLError as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"mock bank did not start within {timeout}s") from last_error


@pytest.fixture(scope="session")
def bank_server() -> Iterator[str]:
    """Spawns the mock bank as a real subprocess on BANK_SERVER_URL's port
    and yields the base URL. A real socket-bound server, not TestClient —
    needed by anything that must goto() a real origin (Flow.origin requires
    a host, so file:// URLs don't validate)."""
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.app:app",
            "--app-dir",
            str(ROOT / "mock-bank"),
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_until_ready(f"{BANK_SERVER_URL}/login.html", timeout=10.0)
        yield BANK_SERVER_URL
    finally:
        process.terminate()
        process.wait(timeout=10)
