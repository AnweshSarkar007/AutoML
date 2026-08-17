"""Environment configuration. AI-free (see CLAUDE.md I1).

The only module under app/ that touches os.environ or .env (CLAUDE.md §11)
— app.safety.policy stays pure by receiving values as arguments instead of
reading this module itself.
"""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    anthropic_api_key: str | None
    bank_base_url: str
    bank_username: str
    bank_password: str
    allowed_origins: tuple[str, ...]


@lru_cache
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        bank_base_url=os.environ.get("BANK_BASE_URL", "http://127.0.0.1:8000"),
        bank_username=os.environ.get("BANK_USERNAME", "demo"),
        bank_password=os.environ.get("BANK_PASSWORD", "demo1234"),
        allowed_origins=_split_origins(os.environ.get("ALLOWED_ORIGINS", "http://127.0.0.1:8000")),
    )


def _split_origins(raw: str) -> tuple[str, ...]:
    return tuple(origin.strip() for origin in raw.split(",") if origin.strip())


def get_env_binding_value(key: str) -> str | None:
    """Resolve an arbitrary env-sourced Binding.key — e.g. BANK_USERNAME —
    which is not necessarily one of the fixed Settings fields above.
    Ensures .env is loaded even if get_settings() hasn't run yet."""
    load_dotenv()
    return os.environ.get(key)
