"""Proof that replay is AI-free (CLAUDE.md I1).

Two independent proofs, per the invariant text:
1. Static — AST-walk every module in the reachable set, follow first-party
   app.* imports transitively, and assert the closure never names
   anthropic, openai, or app.agent.
2. Runtime — with ANTHROPIC_API_KEY unset and non-loopback socket connects
   blocked, a full replay against a file:// fixture still succeeds.
"""

import ast
import socket
from pathlib import Path

from app.artifact.schema import Flow
from app.replay.engine import run_flow
from app.replay.errors import Success

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
FIXTURES = Path(__file__).parent / "fixtures"

# CLAUDE.md I1's reachable set: modules that must stay AI-free, transitively.
REACHABLE_ROOTS = [
    APP / "replay",
    APP / "artifact",
    APP / "safety",
    APP / "intervention",
    APP / "context.py",
    APP / "evidence.py",
    APP / "config.py",
]

FORBIDDEN_EXACT = {"anthropic", "openai"}
FORBIDDEN_PREFIXES = ("app.agent",)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _module_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root]
    if root.is_dir():
        return sorted(root.rglob("*.py"))
    return []


def _path_to_module(path: Path) -> str:
    parts = path.relative_to(ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _first_party_module_path(module_name: str) -> Path | None:
    candidate = ROOT / Path(*module_name.split("."))
    if candidate.with_suffix(".py").is_file():
        return candidate.with_suffix(".py")
    if (candidate / "__init__.py").is_file():
        return candidate / "__init__.py"
    return None


def _imported_module_names(path: Path) -> set[str]:
    """Every module named by an Import or absolute ImportFrom anywhere in
    the file (ast.walk covers the whole tree, not just top-level statements
    — a lazy import inside a function still counts). Relative imports
    (level > 0) are refused outright: this codebase's convention is
    absolute first-party imports, so a relative import here is itself a
    finding, not something to silently resolve.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level > 0:
                raise AssertionError(
                    f"{path}: relative import (level={node.level}) — this codebase's "
                    "AI-free reachable set must use absolute imports so this checker "
                    "can follow them"
                )
            if node.module:
                modules.add(node.module)
    return modules


def _transitive_import_closure(start_files: list[Path]) -> set[str]:
    seen_files: set[Path] = set()
    all_modules: set[str] = set()
    queue = list(start_files)

    while queue:
        path = queue.pop()
        if path in seen_files or not path.is_file():
            continue
        seen_files.add(path)

        for module_name in _imported_module_names(path):
            all_modules.add(module_name)
            if module_name.startswith("app."):
                next_path = _first_party_module_path(module_name)
                if next_path is not None:
                    queue.append(next_path)

    return all_modules


def test_reachable_set_never_imports_an_ai_sdk_or_agent_module():
    start_files: list[Path] = []
    for root in REACHABLE_ROOTS:
        start_files.extend(_module_files(root))
    assert start_files, "reachable set resolved to zero files — path list is stale"

    imported = _transitive_import_closure(start_files)

    violations = {
        module
        for module in imported
        if module in FORBIDDEN_EXACT or module.startswith(FORBIDDEN_PREFIXES)
    }
    assert not violations, f"AI-free reachable set imports forbidden modules: {violations}"


def _block_non_loopback_connects(monkeypatch) -> None:
    # A blanket replacement of socket.socket itself breaks asyncio's
    # ProactorEventLoop on Windows, which opens a loopback self-pipe socket
    # as an internal implementation detail unrelated to any real network
    # call (confirmed empirically — see Day 3.5 commit). Guarding at
    # connect()/connect_ex() and exempting loopback addresses lets that
    # local machinery (and Playwright's own local driver process) through
    # while still blocking anything that would reach a real external host,
    # which is what an anthropic/openai SDK call would have to do.
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK_HOSTS:
            raise AssertionError(f"blocked non-loopback socket connect to {address!r}")
        return real_connect(self, address, *args, **kwargs)

    def guarded_connect_ex(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else address
        if host not in LOOPBACK_HOSTS:
            raise AssertionError(f"blocked non-loopback socket connect to {address!r}")
        return real_connect_ex(self, address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)


def test_replay_completes_with_no_api_key_and_no_outbound_network(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    _block_non_loopback_connects(monkeypatch)

    fixture_url = (FIXTURES / "ai_free_check.html").resolve().as_uri()
    flow = Flow.model_validate(
        {
            "schema_version": 1,
            "id": "ai_free_check",
            "title": "AI-free runtime proof fixture",
            # Never actually contacted: the goto step's url is already an
            # absolute file:// URL, which urljoin() returns unchanged
            # regardless of this origin.
            "origin": "http://127.0.0.1:1",
            "created_at": "2026-01-01T00:00:00Z",
            "created_by": {"mode": "manual", "run_id": "fixture"},
            "outputs": ["greeting"],
            "steps": [
                {
                    "id": "goto",
                    "kind": "goto",
                    "description": "Open the local fixture file",
                    "url": fixture_url,
                    "budget_ms": 5000,
                    "locators": [],
                },
                {
                    "id": "extract",
                    "kind": "extract",
                    "description": "Read the greeting text",
                    "output": "greeting",
                    "budget_ms": 3000,
                    "locators": [{"strategy": "testid", "value": "greeting"}],
                },
            ],
        }
    )

    result = run_flow(flow)

    assert isinstance(result, Success)
    assert result.outputs == {"greeting": "hello world"}
