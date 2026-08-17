"""Shared pytest fixtures.

Adds mock-bank/ to sys.path so `backend.app` imports directly — the hyphen
in mock-bank/ makes it invalid as a dotted package name, so this sys.path
shim (rather than a real import) is the sanctioned way in, per CLAUDE.md §2.1.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mock-bank"))
