import os

import pytest

from furbyland_adventure.config import load_settings
from furbyland_adventure.dotenv import load_dotenv
from furbyland_adventure.errors import ConfigError


def test_username_at_sign_is_stripped(monkeypatch):
    monkeypatch.setenv("ADVENTURE_USERNAME", "@hero_name")
    assert load_settings().username == "hero_name"


def test_bad_username_is_rejected(monkeypatch):
    monkeypatch.setenv("ADVENTURE_USERNAME", "has a space")
    with pytest.raises(ConfigError):
        load_settings()


def test_selection_and_flags(monkeypatch):
    monkeypatch.setenv("ADVENTURE_SELECTION", "random")
    monkeypatch.setenv("ADVENTURE_NO_REPLIES", "skip")
    monkeypatch.setenv("ADVENTURE_CREDIT_MENTIONS", "yes")
    monkeypatch.setenv("ADVENTURE_SPLIT_LONG", "false")
    settings = load_settings()
    assert settings.selection == "random"
    assert settings.no_replies == "skip"
    assert settings.credit_mentions is True
    assert settings.split_long is False


def test_unknown_selection_is_rejected(monkeypatch):
    monkeypatch.setenv("ADVENTURE_SELECTION", "newest")
    with pytest.raises(ConfigError):
        load_settings()


def test_dotenv_does_not_override_existing_variables(monkeypatch, tmp_path):
    monkeypatch.delenv("ADVENTURE_SKIP_DOTENV", raising=False)
    monkeypatch.setenv("X_API_KEY", "already")
    env_file = tmp_path / ".env"
    env_file.write_text(
        'X_API_KEY=fromfile\nADVENTURE_USERNAME="hero"\nexport ADVENTURE_SELECTION=random\n',
        encoding="utf-8",
    )
    load_dotenv(env_file)
    assert os.environ["X_API_KEY"] == "already"
    assert os.environ["ADVENTURE_USERNAME"] == "hero"
    assert os.environ["ADVENTURE_SELECTION"] == "random"
