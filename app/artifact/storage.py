"""Flow artifact storage: save_flow, load_flow, list_flows.

AI-free (see CLAUDE.md I1). The only writer to artifacts/ (CLAUDE.md I4
chokepoint) — nothing else under app/ should open a file under artifacts/.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.artifact.schema import Flow

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"


def save_flow(flow: Flow, path: Path) -> Path:
    """Write flow as deterministic JSON to path. Refuses if path's filename
    isn't exactly f"{flow.id}.json" — there is only one valid name for a
    given flow, so a mismatch is a caller bug, not something to coerce."""
    expected_name = f"{flow.id}.json"
    if path.name != expected_name:
        raise ValueError(
            f"refusing to save flow {flow.id!r} to filename {path.name!r}; "
            f"must be {expected_name!r}"
        )

    # TODO(Day 5.2): route payload through app.safety.policy.redact() before
    # writing, once policy.py exists — see CLAUDE.md I4.
    payload = json.dumps(
        flow.model_dump(mode="json", exclude_none=True), indent=2, ensure_ascii=False
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def load_flow(path: Path) -> Flow:
    """Parse and validate a flow from disk.

    Rejects an unknown schema_version with a clear message rather than
    attempting best-effort parsing against the wrong shape.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = raw.get("schema_version")
    if version != 1:
        raise ValueError(
            f"{path}: unsupported schema_version {version!r}; this build only reads version 1"
        )
    return Flow.model_validate(raw)


def list_flows(directory: Path = ARTIFACTS_DIR) -> list[Flow]:
    """Load every *.json flow in directory, sorted by id."""
    flows = [load_flow(path) for path in sorted(directory.glob("*.json"))]
    return sorted(flows, key=lambda flow: flow.id)
