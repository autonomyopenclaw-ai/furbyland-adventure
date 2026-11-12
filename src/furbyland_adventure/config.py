"""Settings come from environment variables and nowhere else."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from furbyland_adventure.errors import ConfigError

_HANDLE = re.compile(r"[A-Za-z0-9_]{1,15}")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

CREDENTIAL_NAMES = (
    "X_API_KEY",
    "X_API_SECRET",
    "ADVENTURE_ACCESS_TOKEN",
    "ADVENTURE_ACCESS_TOKEN_SECRET",
    "ADVENTURE_USERNAME",
)


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    api_secret: str = ""
    access_token: str = ""
    access_token_secret: str = ""
    username: str = ""
    state_path: Path = Path("state/story.json")
    premise_path: Path = Path("premises/sample.md")
    token_path: Path = Path(".secrets/adventure-tokens.json")
    selection: str = "most_liked"
    no_replies: str = "nudge"
    credit_mentions: bool = False
    split_long: bool = False
    max_chars: int = 280
    llm: str = "auto"
    xai_api_key: str = ""
    openai_api_key: str = ""
    xai_model: str = "grok-4"
    openai_model: str = "gpt-4.1-mini"
    xai_base_url: str = "https://api.x.ai/v1"
    openai_base_url: str = "https://api.openai.com/v1"
    api_base: str = "https://api.x.com"
    random_seed: int | None = None

    def missing_credentials(self) -> list[str]:
        values = {
            "X_API_KEY": self.api_key,
            "X_API_SECRET": self.api_secret,
            "ADVENTURE_ACCESS_TOKEN": self.access_token,
            "ADVENTURE_ACCESS_TOKEN_SECRET": self.access_token_secret,
            "ADVENTURE_USERNAME": self.username,
        }
        return [name for name in CREDENTIAL_NAMES if not values[name]]

    def require_credentials(self) -> None:
        missing = self.missing_credentials()
        if missing:
            raise ConfigError(
                "Missing environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env, fill in the placeholders, and "
                "export the file (`set -a && source .env && set +a`). "
                "Run `adventure auth` to create the adventure account tokens. "
                "The consumer secret is never printed."
            )

    def resolved_llm(self) -> str:
        """Which writer to use. `xai` or `openai` here may still lack a key."""
        if self.llm == "none":
            return "none"
        if self.llm == "auto":
            if self.xai_api_key:
                return "xai"
            if self.openai_api_key:
                return "openai"
            return "none"
        return self.llm

    def writer_label(self) -> str:
        if self.llm == "xai" and not self.xai_api_key:
            return "xAI requested, but XAI_API_KEY is empty"
        if self.llm == "openai" and not self.openai_api_key:
            return "OpenAI requested, but OPENAI_API_KEY is empty"
        mode = self.resolved_llm()
        if mode == "xai":
            return f"xAI ({self.xai_model})"
        if mode == "openai":
            return f"OpenAI ({self.openai_model})"
        return "template (no language model)"

    def secret_values(self) -> list[str]:
        return [
            self.api_key,
            self.api_secret,
            self.access_token,
            self.access_token_secret,
            self.xai_api_key,
            self.openai_api_key,
        ]


def load_settings() -> Settings:
    username = os.environ.get("ADVENTURE_USERNAME", "").strip().lstrip("@")
    if username and not _HANDLE.fullmatch(username):
        raise ConfigError(
            "ADVENTURE_USERNAME must be the account handle, without @, "
            "using 1–15 letters, numbers, or underscores."
        )
    selection = _choice("ADVENTURE_SELECTION", "most_liked", {"most_liked", "random"})
    no_replies = _choice("ADVENTURE_NO_REPLIES", "nudge", {"nudge", "skip"})
    llm = _choice("ADVENTURE_LLM", "auto", {"auto", "xai", "openai", "none"})
    max_chars = _int("ADVENTURE_MAX_CHARS", 280)
    if max_chars < 80 or max_chars > 280:
        raise ConfigError("ADVENTURE_MAX_CHARS must be from 80 through 280.")
    seed_raw = os.environ.get("ADVENTURE_RANDOM_SEED", "").strip()
    seed: int | None
    if not seed_raw:
        seed = None
    else:
        try:
            seed = int(seed_raw)
        except ValueError as exc:
            raise ConfigError("ADVENTURE_RANDOM_SEED must be a whole number.") from exc
    return Settings(
        api_key=os.environ.get("X_API_KEY", "").strip(),
        api_secret=os.environ.get("X_API_SECRET", "").strip(),
        access_token=os.environ.get("ADVENTURE_ACCESS_TOKEN", "").strip(),
        access_token_secret=os.environ.get("ADVENTURE_ACCESS_TOKEN_SECRET", "").strip(),
        username=username,
        state_path=Path(os.environ.get("ADVENTURE_STATE_PATH", "state/story.json").strip()),
        premise_path=Path(os.environ.get("ADVENTURE_PREMISE_PATH", "premises/sample.md").strip()),
        token_path=Path(
            os.environ.get("ADVENTURE_TOKEN_PATH", ".secrets/adventure-tokens.json").strip()
        ),
        selection=selection,
        no_replies=no_replies,
        credit_mentions=_bool("ADVENTURE_CREDIT_MENTIONS", False),
        split_long=_bool("ADVENTURE_SPLIT_LONG", False),
        max_chars=max_chars,
        llm=llm,
        xai_api_key=os.environ.get("XAI_API_KEY", "").strip(),
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        xai_model=os.environ.get("XAI_MODEL", "grok-4").strip() or "grok-4",
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        xai_base_url=_base("XAI_BASE_URL", "https://api.x.ai/v1"),
        openai_base_url=_base("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        api_base=_base("X_API_BASE", "https://api.x.com"),
        random_seed=seed,
    )


def _choice(name: str, default: str, allowed: set[str]) -> str:
    raw = os.environ.get(name, default).strip().lower() or default
    if raw not in allowed:
        options = ", ".join(sorted(allowed))
        raise ConfigError(f"{name} must be one of: {options}.")
    return raw


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false.")


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number.") from exc


def _base(name: str, default: str) -> str:
    raw = os.environ.get(name, default).strip() or default
    return raw.rstrip("/")
