"""Pick the reply that leads the next chapter."""

from __future__ import annotations

import random
from dataclasses import dataclass

from furbyland_adventure.errors import ConfigError


@dataclass(frozen=True)
class Reply:
    id: str
    text: str
    author_id: str
    username: str
    display_name: str
    created_at: str
    like_count: int
    replied_to_id: str | None


def select_reply(replies: list[Reply], mode: str, rng: random.Random) -> Reply:
    """Choose one reply.

    `most_liked` prefers the highest like count. Equal counts go to the
    earliest `created_at`, then the smallest id, so the choice is stable.
    `random` asks `rng` and ignores like counts.
    """
    if not replies:
        raise ValueError("no replies to choose from")
    if mode == "random":
        return rng.choice(list(replies))
    if mode != "most_liked":
        raise ConfigError("ADVENTURE_SELECTION must be most_liked or random.")

    def sort_key(reply: Reply) -> tuple[int, str, tuple]:
        # ISO-8601 timestamps sort chronologically as strings.
        return (-reply.like_count, reply.created_at or "9999", _id_key(reply.id))

    return min(replies, key=sort_key)


def _id_key(value: str) -> tuple:
    if value.isdigit():
        return (0, int(value))
    return (1, value)


def nudge_text(selection: str) -> str:
    if selection == "random":
        how = "One reply will be chosen at random to lead the next chapter."
    else:
        how = "The most-liked reply will lead the next chapter."
    return (
        "Still quiet on the path. Reply to the chapter, not to this note, "
        f"with a kind idea for what should happen next. {how}"
    )
