"""Small X API v2 client using an OAuth 1.0a session.

HTTP errors become XApiError messages. Callers never see a raw traceback
for a 401, 403, or 429.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests
from requests_oauthlib import OAuth1Session

from furbyland_adventure.config import Settings
from furbyland_adventure.errors import XApiError
from furbyland_adventure.replies import Reply

_MAX_PAGES = 5


@dataclass(frozen=True)
class User:
    id: str
    username: str
    name: str


def redact(text: str, secrets: list[str]) -> str:
    redacted = text
    for secret in secrets:
        if secret and len(secret) >= 6:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def build_x_client(settings: Settings) -> XClient:
    session = OAuth1Session(
        settings.api_key,
        client_secret=settings.api_secret,
        resource_owner_key=settings.access_token,
        resource_owner_secret=settings.access_token_secret,
    )
    return XClient(session, api_base=settings.api_base, secrets=settings.secret_values())


class XClient:
    def __init__(
        self,
        session: object,
        api_base: str = "https://api.x.com",
        secrets: list[str] | None = None,
    ) -> None:
        self.session = session
        self.api_base = api_base.rstrip("/")
        self.secrets = list(secrets or [])

    def get_me(self) -> User:
        payload = self._request(
            "GET",
            "/2/users/me",
            params={"user.fields": "id,name,username"},
            purpose="confirm the signed-in account",
        )
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("id") or not data.get("username"):
            raise XApiError("X did not return an account id and username from GET /2/users/me.")
        return User(
            id=str(data["id"]),
            username=str(data["username"]),
            name=str(data.get("name") or data["username"]),
        )

    def post_tweet(self, text: str, reply_to: str | None) -> str:
        if len(text) > 280:
            raise XApiError("Refusing to post a chapter longer than 280 characters.")
        body: dict = {"text": text}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        payload = self._request("POST", "/2/tweets", json=body, purpose="post a chapter")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not data.get("id"):
            raise XApiError("X accepted the post but did not return an id. Nothing was saved.")
        return str(data["id"])

    def post_thread(self, segments: list[str], reply_to: str | None) -> list[str]:
        if not segments:
            raise XApiError("There is no text to post.")
        ids: list[str] = []
        parent = reply_to
        for segment in segments:
            try:
                post_id = self.post_tweet(segment, parent)
            except XApiError as exc:
                if not ids:
                    raise
                raise XApiError(
                    f"{exc} Posted {len(ids)} of {len(segments)} parts "
                    f"(ids: {', '.join(ids)}). The state file was not updated."
                ) from exc
            ids.append(post_id)
            parent = post_id
        return ids

    def direct_replies(self, conversation_id: str, post_id: str, own_user_id: str) -> list[Reply]:
        """Replies whose replied-to id is this chapter, excluding our own posts.

        Recent search only returns posts from about the last 7 days, and it
        needs a paid X API plan. A 403 is reported by `_request`.
        """
        query = f"conversation_id:{conversation_id} is:reply -is:retweet"
        replies: list[Reply] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(_MAX_PAGES):
            params = {
                "query": query,
                "max_results": 100,
                "tweet.fields": (
                    "id,text,author_id,created_at,public_metrics,"
                    "conversation_id,referenced_tweets"
                ),
                "expansions": "author_id",
                "user.fields": "id,username,name",
            }
            if token:
                params["next_token"] = token
            payload = self._request(
                "GET",
                "/2/tweets/search/recent",
                params=params,
                purpose="read replies",
            )
            replies.extend(_replies_from_page(payload, post_id, own_user_id))
            meta = payload.get("meta") if isinstance(payload, dict) else None
            next_token = meta.get("next_token") if isinstance(meta, dict) else None
            if not next_token or next_token in seen_tokens:
                break
            seen_tokens.add(str(next_token))
            token = str(next_token)
        return replies

    def _request(self, method: str, path: str, purpose: str, **kwargs: object) -> dict:
        url = f"{self.api_base}{path}"
        kwargs.setdefault("timeout", 30)
        try:
            if method == "GET":
                response = self.session.get(url, **kwargs)  # type: ignore[attr-defined]
            elif method == "POST":
                response = self.session.post(url, **kwargs)  # type: ignore[attr-defined]
            else:
                raise XApiError(f"Unsupported HTTP method {method}.")
        except requests.RequestException as exc:
            raise XApiError(
                f"Could not reach X while trying to {purpose}. "
                f"Check the network and try again. ({exc.__class__.__name__})"
            ) from exc
        return self._interpret(response, purpose)

    def _interpret(self, response: object, purpose: str) -> dict:
        status = int(getattr(response, "status_code", 0) or 0)
        payload = _read_payload(response)
        headers = getattr(response, "headers", {}) or {}
        if status == 401:
            raise XApiError(self._message_401(payload), status_code=401)
        if status == 403:
            raise XApiError(self._message_403(payload, purpose), status_code=403)
        if status == 429:
            raise XApiError(self._message_429(headers), status_code=429)
        if status >= 400 or payload is None:
            detail = self._safe(_api_detail(payload)) or _body_snippet(response)
            raise XApiError(
                f"X returned HTTP {status} while trying to {purpose}. {detail}".strip(),
                status_code=status or None,
            )
        if payload.get("errors") and "data" not in payload and not payload.get("meta"):
            detail = self._safe(_api_detail(payload)) or "X returned an error."
            raise XApiError(f"X returned an error while trying to {purpose}. {detail}")
        return payload

    def _message_401(self, payload: dict | None) -> str:
        detail = self._safe(_api_detail(payload)) or "none"
        return (
            "X rejected these credentials (HTTP 401). "
            "Check X_API_KEY, X_API_SECRET, ADVENTURE_ACCESS_TOKEN, and "
            "ADVENTURE_ACCESS_TOKEN_SECRET. The key and the tokens have to come "
            "from the same app. If you reset the app secret or its permissions, "
            "run `adventure auth` again. This tool never prints the consumer secret. "
            f"Detail: {detail}."
        )

    def _message_403(self, payload: dict | None, purpose: str) -> str:
        detail = self._safe(_api_detail(payload))
        lowered = detail.lower()
        if "duplicate" in lowered:
            extra = (
                "This text was already posted. Run `adventure status` and "
                "do not post the same chapter again."
            )
        elif purpose == "read replies":
            extra = (
                "Reading replies uses recent search, which needs a paid X API plan. "
                "The Free plan can post but cannot list replies. In the developer "
                "portal, attach this app to a Project and enable pay-per-use credits "
                "or a Basic or Pro plan, then run `adventure advance` again."
            )
        else:
            extra = (
                "Confirm the app permission is Read and Write, and that these "
                "access tokens were created after that permission was saved. "
                "If you changed permissions, run `adventure auth` again."
            )
        return (
            f"X refused the request (HTTP 403) while trying to {purpose}. {extra} "
            f"Detail: {detail or 'none'}."
        )

    def _message_429(self, headers: object) -> str:
        reset = _header(headers, "x-rate-limit-reset")
        if reset and reset.isdigit():
            stamp = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            when = f" Wait until {stamp.strftime('%Y-%m-%d %H:%M:%S')} UTC (reset {reset})."
        else:
            when = " Wait a few minutes before trying again."
        return (
            "X rate limit reached (HTTP 429). Nothing further was posted."
            f"{when} Posting and searching have separate limits."
        )

    def _safe(self, text: str) -> str:
        return redact(text, self.secrets)[:300]


def _replies_from_page(payload: dict, post_id: str, own_user_id: str) -> list[Reply]:
    users = {}
    includes = payload.get("includes") if isinstance(payload, dict) else None
    if isinstance(includes, dict):
        for user in includes.get("users") or []:
            if isinstance(user, dict) and user.get("id"):
                users[str(user["id"])] = user
    found: list[Reply] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        author_id = str(item.get("author_id") or "")
        if author_id and author_id == str(own_user_id):
            continue
        replied_to = _replied_to_id(item)
        if replied_to != post_id:
            continue
        metrics = item.get("public_metrics") if isinstance(item.get("public_metrics"), dict) else {}
        user = users.get(author_id, {})
        try:
            likes = int(metrics.get("like_count") or 0)
        except (TypeError, ValueError):
            likes = 0
        found.append(
            Reply(
                id=str(item.get("id") or ""),
                text=str(item.get("text") or ""),
                author_id=author_id,
                username=str(user.get("username") or "reader"),
                display_name=str(user.get("name") or "reader"),
                created_at=str(item.get("created_at") or ""),
                like_count=likes,
                replied_to_id=replied_to,
            )
        )
    return found


def _replied_to_id(item: dict) -> str | None:
    for reference in item.get("referenced_tweets") or []:
        if isinstance(reference, dict) and reference.get("type") == "replied_to":
            reply_id = reference.get("id")
            return str(reply_id) if reply_id else None
    return None


def _read_payload(response: object) -> dict | None:
    try:
        data = response.json()  # type: ignore[attr-defined]
    except (ValueError, AttributeError):
        return None
    if isinstance(data, dict):
        return data
    return None


def _api_detail(payload: dict | None) -> str:
    if not isinstance(payload, dict):
        return ""
    parts: list[str] = []
    for key in ("title", "detail", "message", "reason"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
    errors = payload.get("errors")
    if isinstance(errors, list):
        for item in errors[:3]:
            if isinstance(item, dict):
                message = item.get("message") or item.get("detail")
                if isinstance(message, str) and message.strip():
                    parts.append(message.strip())
            elif isinstance(item, str) and item.strip():
                parts.append(item.strip())
    return " ".join(parts)


def _body_snippet(response: object) -> str:
    text = getattr(response, "text", "") or ""
    if not isinstance(text, str):
        return ""
    return text[:200]


def _header(headers: object, name: str) -> str:
    if not hasattr(headers, "get"):
        return ""
    value = headers.get(name) or headers.get(name.title()) or headers.get(name.upper())
    return str(value) if value else ""
