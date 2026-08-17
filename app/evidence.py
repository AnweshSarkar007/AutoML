"""Evidence capture: TraceWriter, save_screenshot. AI-free (see CLAUDE.md I1).

The only writer to evidence/ (CLAUDE.md I4 chokepoint) — nothing else under
app/ should open a file under evidence/. Schema and event vocabulary are
CLAUDE.md §9; both discovery and replay write the same shape so one
analysis script can read either.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from playwright.sync_api import Page

EVIDENCE_ROOT = Path(__file__).resolve().parent.parent / "evidence"

Mode = Literal["discovery", "replay"]
Level = Literal["info", "warn", "error"]


def _iso_ms_timestamp() -> str:
    now = datetime.now(UTC)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


class TraceWriter:
    """Appends one JSON object per line to evidence/{mode}/{run_id}/trace.jsonl."""

    def __init__(self, run_id: str, mode: Mode, root: Path = EVIDENCE_ROOT) -> None:
        self.run_id = run_id
        self.mode = mode
        self.run_dir = root / mode / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self._seq = 0

    def write(
        self,
        event: str,
        *,
        level: Level = "info",
        step_index: int | None = None,
        step_id: str | None = None,
        kind: str | None = None,
        locator: dict | None = None,
        attempt: int | None = None,
        duration_ms: int | None = None,
        screenshot: str | None = None,
        detail: dict | None = None,
    ) -> None:
        self._seq += 1
        # TODO(Day 5.2): route `detail` and `locator` through
        # app.safety.policy.redact() before writing, once policy.py exists
        # — see CLAUDE.md I4.
        line = {
            "ts": _iso_ms_timestamp(),
            "run_id": self.run_id,
            "mode": self.mode,
            "seq": self._seq,
            "event": event,
            "level": level,
            "step_index": step_index,
            "step_id": step_id,
            "kind": kind,
            "locator": locator,
            "attempt": attempt,
            "duration_ms": duration_ms,
            "screenshot": screenshot,
            "detail": detail or {},
        }
        with (self.run_dir / "trace.jsonl").open("a", encoding="utf-8") as trace_file:
            trace_file.write(json.dumps(line, ensure_ascii=False) + "\n")


def save_screenshot(page: Page, run_dir: Path, step_index: int, step_id: str) -> str:
    """Save a screenshot to run_dir/steps/NNN-<step_id>.png (NNN zero-padded
    to 3) and return its path relative to run_dir, ready to drop into a
    trace line's `screenshot` field (CLAUDE.md §9)."""
    relative_path = Path("steps") / f"{step_index:03d}-{step_id}.png"
    absolute_path = run_dir / relative_path
    absolute_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(absolute_path))
    return str(relative_path).replace("\\", "/")
