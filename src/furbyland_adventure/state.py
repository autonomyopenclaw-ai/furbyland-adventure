"""Story memory. The file holds post ids and a short summary, never secrets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from furbyland_adventure.errors import ConfigError


@dataclass
class ChapterRecord:
    number: int
    post_ids: list[str]
    text: str
    created_at: str
    chosen_reply_id: str | None = None
    idea: str | None = None
    credit: str | None = None

    def to_dict(self) -> dict:
        return {
            "number": self.number,
            "post_ids": list(self.post_ids),
            "text": self.text,
            "created_at": self.created_at,
            "chosen_reply_id": self.chosen_reply_id,
            "idea": self.idea,
            "credit": self.credit,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> ChapterRecord:
        return cls(
            number=int(raw.get("number") or 0),
            post_ids=[str(item) for item in raw.get("post_ids") or []],
            text=str(raw.get("text") or ""),
            created_at=str(raw.get("created_at") or ""),
            chosen_reply_id=_optional_str(raw.get("chosen_reply_id")),
            idea=_optional_str(raw.get("idea")),
            credit=_optional_str(raw.get("credit")),
        )


@dataclass
class StoryState:
    version: int = 1
    chapter: int = 0
    current_post_id: str | None = None
    thread_root_id: str | None = None
    summary: str = ""
    chapters: list[ChapterRecord] = field(default_factory=list)
    nudged_chapter: int | None = None
    last_nudge_post_id: str | None = None
    username: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "chapter": self.chapter,
            "current_post_id": self.current_post_id,
            "thread_root_id": self.thread_root_id,
            "summary": self.summary,
            "chapters": [chapter.to_dict() for chapter in self.chapters],
            "nudged_chapter": self.nudged_chapter,
            "last_nudge_post_id": self.last_nudge_post_id,
            "username": self.username,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> StoryState:
        chapters = []
        for item in raw.get("chapters") or []:
            if isinstance(item, dict):
                chapters.append(ChapterRecord.from_dict(item))
        return cls(
            version=int(raw.get("version") or 1),
            chapter=int(raw.get("chapter") or 0),
            current_post_id=_optional_str(raw.get("current_post_id")),
            thread_root_id=_optional_str(raw.get("thread_root_id")),
            summary=str(raw.get("summary") or ""),
            chapters=chapters,
            nudged_chapter=_optional_int(raw.get("nudged_chapter")),
            last_nudge_post_id=_optional_str(raw.get("last_nudge_post_id")),
            username=_optional_str(raw.get("username")),
            updated_at=_optional_str(raw.get("updated_at")),
        )


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> StoryState:
        if not self.path.exists():
            return StoryState()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"State file {self.path} is not valid JSON ({exc}). "
                "Fix it, or move it aside, before running the bot again."
            ) from exc
        if not isinstance(raw, dict):
            raise ConfigError(f"State file {self.path} must contain a JSON object.")
        return StoryState.from_dict(raw)

    def save(self, state: StoryState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)
