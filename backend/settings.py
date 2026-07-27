from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS_PATH = ROOT / ".streamlit" / "secrets.toml"


def get_groq_api_key() -> str | None:
    """Resolve Groq API key from environment or Streamlit secrets.toml."""
    key = os.getenv("GROQ_API_KEY")
    if key:
        return key
    if not SECRETS_PATH.exists():
        return None
    try:
        import tomllib

        with SECRETS_PATH.open("rb") as handle:
            data = tomllib.load(handle)
        value = data.get("GROQ_API_KEY")
        if isinstance(value, str) and value.strip():
            return value.strip()
    except (OSError, ValueError, KeyError):
        return None
    return None


def require_groq_api_key() -> str:
    key = get_groq_api_key()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Use export GROQ_API_KEY=... or .streamlit/secrets.toml."
        )
    return key
