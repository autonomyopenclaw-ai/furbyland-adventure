"""Plain-text helpers. Chapters are ordinary characters, capped at 280."""

from __future__ import annotations

import re

_HIDDEN = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
_POST_BLOCK = re.compile(r"<!--\s*post\s*-->(.*?)<!--\s*/post\s*-->", re.IGNORECASE | re.DOTALL)
_MENTION = re.compile(r"@([A-Za-z0-9_]{1,15})")


def normalize_hidden(text: str) -> str:
    """Drop characters that can hide or reorder text inside a reply."""
    return _HIDDEN.sub("", text or "")


def clean_whitespace(text: str) -> str:
    text = normalize_hidden(text).replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def scrub_mentions(text: str, allowed: str | None) -> str:
    """Remove @ so a post does not notify anyone. Keep one handle when allowed."""
    allowed_name = (allowed or "").lstrip("@").lower()

    def replace(match: re.Match[str]) -> str:
        handle = match.group(1)
        if allowed_name and handle.lower() == allowed_name:
            return f"@{handle}"
        return handle

    return _MENTION.sub(replace, text)


def safe_handle(username: str) -> str | None:
    username = (username or "").strip().lstrip("@")
    if re.fullmatch(r"[A-Za-z0-9_]{1,15}", username):
        return username
    return None


def excerpt(text: str, limit: int) -> str:
    """Short, single-line quote of untrusted reply text. Mentions are not kept."""
    cleaned = scrub_mentions(clean_whitespace(text), None).replace('"', "'")
    if limit < 1:
        return ""
    if len(cleaned) <= limit:
        return cleaned
    cut = cleaned[: limit - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    cut = cut.rstrip(".,;:!? ")
    if not cut:
        cut = cleaned[: limit - 1].rstrip()
    return cut + "…"


def ensure_question(text: str) -> str:
    text = clean_whitespace(text)
    if "?" in text:
        return text
    suffix = " What should happen next?"
    if not text:
        return suffix.strip()
    return text.rstrip(" .!") + suffix


def roll_summary(previous: str, addition: str, limit: int = 500) -> str:
    previous = clean_whitespace(previous)
    addition = clean_whitespace(addition)
    if not previous:
        combined = addition
    elif not addition:
        combined = previous
    else:
        combined = f"{previous} {addition}"
    if len(combined) <= limit:
        return combined
    tail = combined[-limit:]
    if " " in tail:
        tail = tail.split(" ", 1)[1]
    return tail.strip()


def extract_post_block(premise: str) -> str | None:
    match = _POST_BLOCK.search(premise or "")
    if not match:
        return None
    block = clean_whitespace(match.group(1))
    return block or None


def premise_prose(premise: str) -> str:
    """Premise text with the optional post block and markdown headings removed."""
    without_block = _POST_BLOCK.sub(" ", premise or "")
    lines = []
    for line in without_block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return clean_whitespace(" ".join(lines))


def credit_phrase(suggestion: str, username: str, allow_mentions: bool, idea_len: int = 80) -> str:
    idea = excerpt(suggestion, idea_len)
    handle = safe_handle(username) if allow_mentions else None
    who = f"@{handle}" if handle else "a reader"
    return f'{who} suggested "{idea}"'


def fit_posts(text: str, limit: int, split: bool, max_parts: int = 4) -> list[str]:
    """Return 1+ posts, each at most `limit` characters, ending in a question."""
    if limit < 20:
        raise ValueError("limit too small")
    text = clean_whitespace(text)
    if not text:
        text = "The story pauses on the path. What should happen next?"
    if "?" not in text:
        text = ensure_question(text)
    if len(text) <= limit:
        return [text]
    if not split:
        return [shorten_to_limit(text, limit)]
    parts = _pack(text, limit, max_parts)
    if "?" not in parts[-1]:
        parts[-1] = shorten_to_limit(ensure_question(parts[-1]), limit)
    return [part for part in parts if part]


def shorten_to_limit(text: str, limit: int) -> str:
    text = clean_whitespace(text)
    if len(text) <= limit and "?" in text:
        return text
    ending = " What next?"
    if len(ending) > limit:
        ending = "?"
    room = limit - len(ending)
    prefix = text[:room]
    if room < len(text) and " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0]
    prefix = prefix.rstrip(" .,;:!-")
    candidate = f"{prefix}{ending}" if prefix else ending.lstrip()
    if len(candidate) > limit:
        candidate = candidate[: limit - 1].rstrip() + "?"
    if "?" not in candidate:
        candidate = candidate[: limit - 1] + "?"
    return candidate[:limit]


def idea_in_text(text: str, suggestion: str) -> bool:
    idea = excerpt(suggestion, 80).lower()
    lowered = text.lower()
    if idea and idea in lowered:
        return True
    short = idea[:12].strip(" …")
    return len(short) >= 4 and short in lowered


def _pack(text: str, limit: int, max_parts: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) <= limit:
            pieces.append(sentence)
        else:
            pieces.extend(_hard_chunks(sentence, limit))
    if not pieces:
        return [shorten_to_limit(text, limit)]
    parts: list[str] = []
    current = ""
    for piece in pieces:
        proposed = piece if not current else f"{current} {piece}"
        if len(proposed) <= limit:
            current = proposed
        else:
            if current:
                parts.append(current)
            current = piece
    if current:
        parts.append(current)
    if len(parts) > max_parts:
        head = parts[: max_parts - 1]
        tail = " ".join(parts[max_parts - 1 :])
        head.append(shorten_to_limit(tail, limit))
        parts = head
    return parts


def _hard_chunks(sentence: str, limit: int) -> list[str]:
    words = sentence.split(" ")
    chunks: list[str] = []
    current = ""
    for word in words:
        if len(word) > limit:
            word = word[:limit]
        proposed = word if not current else f"{current} {word}"
        if len(proposed) <= limit:
            current = proposed
        else:
            if current:
                chunks.append(current)
            current = word
    if current:
        chunks.append(current)
    return chunks
