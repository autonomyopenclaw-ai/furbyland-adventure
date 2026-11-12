"""Shared fixtures. Tests never read a developer's real .env or tokens."""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_CLEARED = (
    "X_API_KEY",
    "X_API_SECRET",
    "ADVENTURE_ACCESS_TOKEN",
    "ADVENTURE_ACCESS_TOKEN_SECRET",
    "ADVENTURE_USERNAME",
    "ADVENTURE_SELECTION",
    "ADVENTURE_NO_REPLIES",
    "ADVENTURE_CREDIT_MENTIONS",
    "ADVENTURE_SPLIT_LONG",
    "ADVENTURE_MAX_CHARS",
    "ADVENTURE_LLM",
    "XAI_API_KEY",
    "OPENAI_API_KEY",
    "XAI_MODEL",
    "OPENAI_MODEL",
    "XAI_BASE_URL",
    "OPENAI_BASE_URL",
    "ADVENTURE_RANDOM_SEED",
    "X_API_BASE",
)


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("ADVENTURE_SKIP_DOTENV", "1")
    for name in _CLEARED:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ADVENTURE_STATE_PATH", str(tmp_path / "story.json"))
    monkeypatch.setenv("ADVENTURE_PREMISE_PATH", str(tmp_path / "premise.md"))
    monkeypatch.setenv("ADVENTURE_TOKEN_PATH", str(tmp_path / "tokens.json"))
    return tmp_path
