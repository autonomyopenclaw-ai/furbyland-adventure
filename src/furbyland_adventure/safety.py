"""Decide which replies are safe to treat as story ideas.

Reply text is untrusted. It can be rude, spam, or an attempt to give this
bot new instructions. A rejected reply is skipped and is not quoted.
"""

from __future__ import annotations

import re

from furbyland_adventure.textutil import clean_whitespace, normalize_hidden

# Whole words only, so names like Dickens and words like "hello" stay usable.
_OFFENSIVE = re.compile(
    r"\b("
    r"fucks?|fucking|fucked|fucker|fuckers|"
    r"shits?|shitty|shithead|"
    r"bitches|bitch|"
    r"assholes?|"
    r"bastards?|"
    r"cunts?|"
    r"dicks?|dickhead|"
    r"porn|porno|pornography|nudes?|nsfw|"
    r"nigger\w*|faggot\w*|retard\w*|kike\w*|spic\w*|chink\w*|tranny|"
    r"sex|sexual"
    r")\b|"
    r"\bkill yourself\b|\bkys\b",
    re.IGNORECASE,
)

_INJECTION = re.compile(
    "|".join(
        [
            r"ignore (?:all |any |the )?(?:previous|prior|above|your) "
            r"(?:instructions|prompts|rules|directions)",
            r"disregard (?:the |your |all )?(?:previous |prior )?"
            r"(?:instructions|rules|prompt|guidelines)",
            r"forget (?:everything|all|your)(?: (?:previous|prior))? "
            r"(?:instructions|rules|prompt)",
            r"you are now (?:a |an )?(?:assistant|bot|dan|chatgpt|grok|model|ai|"
            r"unfiltered|jailbroken)\b",
            r"from now on,? you (?:will|must|should)",
            r"new (?:instructions|persona|role|prompt)\b",
            r"system prompt",
            r"developer mode",
            r"jailbreak",
            r"override (?:your |the )?(?:rules|instructions|prompt)",
            r"reveal (?:your |the )?(?:hidden |system )?(?:prompt|instructions)",
            r"print (?:your |the )?(?:hidden |system )?(?:prompt|instructions)",
            r"<\s*/?\s*(?:system|instructions|prompt)\s*>",
            r"\[/?\s*(?:system|instructions|inst)\s*\]",
            r"do not follow (?:the |your )?(?:rules|instructions|above)",
        ]
    ),
    re.IGNORECASE,
)

_SPAM_PHRASES = (
    "free crypto",
    "airdrop",
    "giveaway",
    "dm me",
    "check my bio",
    "check my profile",
    "onlyfans",
    "nft drop",
    "follow me for",
    "follow back",
    "click the link",
    "t.me/",
)

_URL = re.compile(r"https?://|www\.", re.IGNORECASE)


def rejection_reason(text: str) -> str | None:
    """Return a short reason, or None when the reply can be a story idea."""
    compact = clean_whitespace(normalize_hidden(text or ""))
    if sum(1 for character in compact if character.isalpha()) < 2:
        return "empty"
    if _INJECTION.search(compact):
        return "prompt-injection"
    if _OFFENSIVE.search(compact):
        return "offensive"
    if _spam(compact):
        return "spam"
    return None


def format_ignored(ignored: dict[str, int]) -> str:
    if not ignored:
        return ""
    parts = [f"{count} {reason}" for reason, count in sorted(ignored.items())]
    return "Ignored " + ", ".join(parts) + ". "


def _spam(text: str) -> bool:
    lowered = text.lower()
    if any(phrase in lowered for phrase in _SPAM_PHRASES):
        return True
    if len(_URL.findall(lowered)) > 1:
        return True
    if re.fullmatch(r"https?://\S+", lowered):
        return True
    if re.search(r"(.)\1{9,}", lowered):
        return True
    if len(re.findall(r"#\w+", text)) > 4:
        return True
    if len(text) > 1000:
        return True
    return False
