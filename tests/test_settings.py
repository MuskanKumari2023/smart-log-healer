from pathlib import Path
from unittest.mock import patch

from backend.settings import get_groq_api_key


def test_get_groq_api_key_from_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert get_groq_api_key() == "gsk_test"


def test_get_groq_api_key_from_secrets_toml(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    secrets_dir = tmp_path / ".streamlit"
    secrets_dir.mkdir()
    (secrets_dir / "secrets.toml").write_text('GROQ_API_KEY = "gsk_from_toml"\n')
    with patch("backend.settings.SECRETS_PATH", secrets_dir / "secrets.toml"):
        assert get_groq_api_key() == "gsk_from_toml"


def test_system_prompt_includes_tests():
    from backend.ai_client import _system_prompt

    prompt = _system_prompt("none_type")
    assert "ACCEPTANCE_TESTS" in prompt
    assert "test_missing_user_returns_none" in prompt


def test_judge_prompt_context_includes_tests():
    from backend.judge import JUDGE_PROMPT

    assert "pytest" in JUDGE_PROMPT.lower()
    assert "acceptance tests" in JUDGE_PROMPT.lower()
