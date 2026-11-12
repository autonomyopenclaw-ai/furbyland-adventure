"""Turn a premise and replies into the next post, then remember it."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timezone

from furbyland_adventure.config import Settings
from furbyland_adventure.errors import ConfigError, UsernameMismatch
from furbyland_adventure.replies import Reply, nudge_text, select_reply
from furbyland_adventure.safety import format_ignored, rejection_reason
from furbyland_adventure.state import ChapterRecord, StateStore, StoryState
from furbyland_adventure.textutil import (
    clean_whitespace,
    credit_phrase,
    ensure_question,
    excerpt,
    extract_post_block,
    fit_posts,
    idea_in_text,
    roll_summary,
    safe_handle,
    scrub_mentions,
)
from furbyland_adventure.writer import Draft, TemplateWriter
from furbyland_adventure.x_client import User, XClient

GENERIC_CHAPTER = (
    "The travelers take a kinder turn and wait for a better idea. What should happen next?"
)


@dataclass
class RunResult:
    action: str
    dry_run: bool
    message: str
    posts: list[str] = field(default_factory=list)
    post_ids: list[str] = field(default_factory=list)
    chapter: int = 0
    username: str = ""
    selected_reply_id: str | None = None
    ignored: dict[str, int] = field(default_factory=dict)


class Adventure:
    def __init__(
        self,
        settings: Settings,
        client: XClient | None,
        writer: object,
        store: StateStore,
        now=None,
        rng: random.Random | None = None,
    ) -> None:
        self.settings = settings
        self.client = client
        self.writer = writer
        self.template = TemplateWriter()
        self.store = store
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.rng = rng

    def start(self, premise: str, *, dry_run: bool, force: bool) -> RunResult:
        state = self.store.load()
        if state.chapter > 0 and not force:
            raise ConfigError(
                f"A story is already in progress at chapter {state.chapter} "
                f"(post {state.current_post_id}). Run `adventure advance`, "
                "or `adventure start --force` to replace that state and begin again."
            )
        draft, used_block = self._opening_draft(premise)
        segments = finalize_chapter(
            draft.text,
            max_chars=self.settings.max_chars,
            split=self.settings.split_long,
            allow_handle=None,
            scrub=False,
        )
        summary = roll_summary("", draft.summary or segments[0])
        if dry_run:
            source = "the premise file" if used_block else draft.source
            return RunResult(
                action="start",
                dry_run=True,
                posts=segments,
                chapter=1,
                message=(
                    "Dry run: nothing will be posted and the state file will not change.\n"
                    f"Writer: {source}."
                ),
            )
        me = require_user(self._client(), self.settings.username)
        ids = self._client().post_thread(segments, reply_to=None)
        new_state = StoryState(
            version=1,
            chapter=1,
            current_post_id=ids[-1],
            thread_root_id=ids[0],
            summary=summary,
            chapters=[
                ChapterRecord(
                    number=1,
                    post_ids=ids,
                    text="\n\n".join(segments),
                    created_at=self._iso(),
                )
            ],
            username=me.username,
            updated_at=self._iso(),
        )
        self.store.save(new_state)
        return RunResult(
            action="start",
            dry_run=False,
            posts=segments,
            post_ids=ids,
            chapter=1,
            username=me.username,
            message=(
                f"Posted chapter 1 as @{me.username}. "
                f"State saved to {self.settings.state_path}."
            ),
        )

    def advance(self, *, dry_run: bool) -> RunResult:
        state = self.store.load()
        if state.chapter < 1 or not state.current_post_id or not state.thread_root_id:
            raise ConfigError(
                "There is no story yet. Edit the premise and run `adventure start` first."
            )
        me = require_user(self._client(), self.settings.username)
        fetched = self._client().direct_replies(
            conversation_id=state.thread_root_id,
            post_id=state.current_post_id,
            own_user_id=me.id,
        )
        kept: list[Reply] = []
        ignored: dict[str, int] = {}
        for reply in fetched:
            reason = rejection_reason(reply.text)
            if reason is None:
                kept.append(reply)
            else:
                ignored[reason] = ignored.get(reason, 0) + 1
        if not kept:
            return self._no_replies(state, dry_run=dry_run, ignored=ignored, username=me.username)
        chosen = select_reply(kept, self.settings.selection, self._rng())
        allow_handle = safe_handle(chosen.username) if self.settings.credit_mentions else None
        credit = credit_phrase(chosen.text, chosen.username, allow_handle is not None)
        draft = self.writer.next_chapter(
            summary=state.summary,
            chapter_number=state.chapter + 1,
            suggestion=chosen.text,
            credit=credit,
            max_chars=self.settings.max_chars,
            allow_mentions=allow_handle is not None,
        )
        segments = finalize_chapter(
            draft.text,
            max_chars=self.settings.max_chars,
            split=self.settings.split_long,
            allow_handle=allow_handle,
            scrub=True,
        )
        if not _credits(segments, chosen.text, allow_handle):
            draft = self.template.next_chapter(
                summary=state.summary,
                chapter_number=state.chapter + 1,
                suggestion=chosen.text,
                credit=credit,
                max_chars=self.settings.max_chars,
                allow_mentions=allow_handle is not None,
            )
            segments = finalize_chapter(
                draft.text,
                max_chars=self.settings.max_chars,
                split=self.settings.split_long,
                allow_handle=allow_handle,
                scrub=True,
            )
        summary = roll_summary(state.summary, draft.summary)
        new_chapter = state.chapter + 1
        ignored_note = format_ignored(ignored)
        choice = (
            f"reply {chosen.id} by @{chosen.username} "
            f"({chosen.like_count} likes, {self.settings.selection})"
        )
        if dry_run:
            return RunResult(
                action="advance",
                dry_run=True,
                posts=segments,
                chapter=new_chapter,
                username=me.username,
                selected_reply_id=chosen.id,
                ignored=ignored,
                message=(
                    "Dry run: nothing will be posted and the state file will not change.\n"
                    f"Usable replies: {len(kept)}. {ignored_note}"
                    f"Would continue from {choice}.\n"
                    f"Writer: {draft.source}."
                ),
            )
        ids = self._client().post_thread(segments, reply_to=state.current_post_id)
        state.chapter = new_chapter
        state.current_post_id = ids[-1]
        state.summary = summary
        state.nudged_chapter = None
        state.last_nudge_post_id = None
        state.username = me.username
        state.updated_at = self._iso()
        state.chapters.append(
            ChapterRecord(
                number=new_chapter,
                post_ids=ids,
                text="\n\n".join(segments),
                created_at=state.updated_at,
                chosen_reply_id=chosen.id,
                idea=excerpt(chosen.text, 120),
                credit=credit,
            )
        )
        self.store.save(state)
        warning = getattr(self.writer, "last_warning", "")
        extra = f" {warning}" if warning else ""
        return RunResult(
            action="advance",
            dry_run=False,
            posts=segments,
            post_ids=ids,
            chapter=new_chapter,
            username=me.username,
            selected_reply_id=chosen.id,
            ignored=ignored,
            message=(
                f"Posted chapter {new_chapter} as @{me.username} from {choice}. "
                f"{ignored_note}State saved to {self.settings.state_path}.{extra}"
            ),
        )

    def _no_replies(
        self,
        state: StoryState,
        *,
        dry_run: bool,
        ignored: dict[str, int],
        username: str,
    ) -> RunResult:
        ignored_note = format_ignored(ignored)
        already_nudged = state.nudged_chapter == state.chapter
        if self.settings.no_replies == "skip" or already_nudged:
            if self.settings.no_replies == "skip":
                why = "ADVENTURE_NO_REPLIES=skip, so nothing was posted."
            else:
                why = "A nudge was already posted for this chapter, so nothing new was posted."
            return RunResult(
                action="skip",
                dry_run=dry_run,
                chapter=state.chapter,
                username=username,
                ignored=ignored,
                message=f"No usable replies. {ignored_note}{why}",
            )
        segments = fit_posts(nudge_text(self.settings.selection), self.settings.max_chars, False)
        if dry_run:
            return RunResult(
                action="nudge",
                dry_run=True,
                posts=segments,
                chapter=state.chapter,
                username=username,
                ignored=ignored,
                message=(
                    "Dry run: nothing will be posted and the state file will not change.\n"
                    f"No usable replies. {ignored_note}Would post a nudge."
                ),
            )
        ids = self._client().post_thread(segments, reply_to=state.current_post_id)
        state.nudged_chapter = state.chapter
        state.last_nudge_post_id = ids[-1]
        state.updated_at = self._iso()
        state.username = username
        self.store.save(state)
        return RunResult(
            action="nudge",
            dry_run=False,
            posts=segments,
            post_ids=ids,
            chapter=state.chapter,
            username=username,
            ignored=ignored,
            message=(
                f"No usable replies. {ignored_note}"
                "Posted a nudge and left the chapter where it is, "
                f"so later replies to it still count. State saved to {self.settings.state_path}."
            ),
        )

    def _opening_draft(self, premise: str) -> tuple[Draft, bool]:
        block = extract_post_block(premise)
        if block:
            text = ensure_question(clean_whitespace(block))
            if len(text) <= self.settings.max_chars:
                return Draft(text=text, summary=excerpt(text, 240), source="premise"), True
        draft = self.writer.opening(premise, self.settings.max_chars)
        return draft, False

    def _client(self) -> XClient:
        if self.client is None:
            raise ConfigError(
                "This command needs X credentials. Set the variables in .env.example "
                "and run `adventure auth` if you do not have adventure tokens yet."
            )
        return self.client

    def _rng(self) -> random.Random:
        if self.rng is not None:
            return self.rng
        if self.settings.random_seed is None:
            return random.Random()
        return random.Random(self.settings.random_seed)

    def _iso(self) -> str:
        moment = self.now()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        return moment.replace(microsecond=0).isoformat()


def require_user(client: XClient, expected: str) -> User:
    """Confirm GET /2/users/me before any post. Refuse if the handle differs."""
    if not expected:
        raise ConfigError(
            "Set ADVENTURE_USERNAME to the adventure account's handle before posting."
        )
    me = client.get_me()
    if me.username.lower() != expected.lstrip("@").lower():
        raise UsernameMismatch(
            f"Authenticated as @{me.username}, but ADVENTURE_USERNAME is "
            f"@{expected.lstrip('@')}. Refusing to post. The access tokens are for "
            "a different account. Run `adventure auth` while logged in as the "
            "adventure account, then update ADVENTURE_ACCESS_TOKEN and "
            "ADVENTURE_ACCESS_TOKEN_SECRET."
        )
    return me


def finalize_chapter(
    text: str,
    *,
    max_chars: int,
    split: bool,
    allow_handle: str | None,
    scrub: bool,
) -> list[str]:
    cleaned = clean_whitespace(text)
    if scrub:
        cleaned = scrub_mentions(cleaned, allow_handle)
        if rejection_reason(cleaned):
            cleaned = GENERIC_CHAPTER
    return fit_posts(cleaned, max_chars, split)


def _credits(segments: list[str], suggestion: str, allow_handle: str | None) -> bool:
    text = " ".join(segments)
    if not idea_in_text(text, suggestion):
        return False
    if allow_handle:
        return f"@{allow_handle.lower()}" in text.lower()
    return "@" not in text


def render_status(settings: Settings, state: StoryState) -> str:
    if state.chapter:
        chapter_line = f"Chapter: {state.chapter}"
    else:
        chapter_line = "Chapter: not started"
    if settings.username:
        expected = f"Expected account: @{settings.username}"
    else:
        expected = "Expected account: not set (ADVENTURE_USERNAME)"
    lines = [
        f"State file: {settings.state_path}",
        expected,
        chapter_line,
        f"Selection: {settings.selection}",
        f"If nobody replies: {settings.no_replies}",
        f"Credit @mentions: {'yes' if settings.credit_mentions else 'no'}",
        (
            "Long chapters: split into a short thread"
            if settings.split_long
            else "Long chapters: shortened to one post"
        ),
        f"Writer: {settings.writer_label()}",
    ]
    if state.current_post_id:
        handle = state.username or settings.username
        if handle:
            lines.append(f"Latest chapter: https://x.com/{handle}/status/{state.current_post_id}")
        else:
            lines.append(f"Latest chapter id: {state.current_post_id}")
    if state.thread_root_id and state.thread_root_id != state.current_post_id:
        lines.append(f"Thread root id: {state.thread_root_id}")
    if state.summary:
        lines.append(f"Summary: {state.summary}")
    if state.chapter and state.nudged_chapter == state.chapter:
        lines.append(
            "A nudge was already posted for this chapter. "
            "The bot is still waiting for a reply to the chapter itself."
        )
    return "\n".join(lines)
