"""Shared run identity. AI-free (see CLAUDE.md I1).

Used by both the discovery and replay paths so run_id and evidence-path
semantics never diverge between them (CLAUDE.md §2.1, §9).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime


def new_run_id() -> str:
    """<UTC compact timestamp>-<6 lowercase hex>, e.g. 20260817T142530Z-9f3ab1.

    No colons: Windows forbids them in path components, and this id is used
    directly as an evidence directory name (CLAUDE.md §9).
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = secrets.token_hex(3)
    return f"{timestamp}-{suffix}"


@dataclass
class RunContext:
    """Mutable state threaded through a single run.

    `outputs` accumulates as `extract` steps fire, keyed by `Step.output`;
    it doubles as the source a `Binding.source == "extracted"` reads from.
    """

    run_id: str
    flow_id: str
    outputs: dict[str, str] = field(default_factory=dict)
