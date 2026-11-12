"""PIN-based (out-of-band) 3-legged OAuth 1.0a for the adventure account.

The consumer secret is used to sign requests and is never printed.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from requests_oauthlib import OAuth1Session

from furbyland_adventure.config import Settings
from furbyland_adventure.errors import ConfigError, UsernameMismatch, XApiError
from furbyland_adventure.x_client import User, XClient, redact

_PIN = re.compile(r"[0-9]{4,10}")
Output = Callable[[str], None]
InputFn = Callable[[str], str]
SessionFactory = Callable[..., object]
ClientFactory = Callable[[Settings, str, str], object]


def run_auth(
    settings: Settings,
    *,
    pin: str | None = None,
    input_fn: InputFn = input,
    output_fn: Output = print,
    session_factory: SessionFactory = OAuth1Session,
    client_factory: ClientFactory | None = None,
) -> None:
    if not settings.api_key or not settings.api_secret:
        raise ConfigError(
            "Set X_API_KEY and X_API_SECRET before authorizing. "
            "They are the app's consumer key and secret. This tool never prints the consumer secret."
        )
    try:
        requestor = session_factory(
            settings.api_key,
            client_secret=settings.api_secret,
            callback_uri="oob",
        )
        request_token = requestor.fetch_request_token(f"{settings.api_base}/oauth/request_token")
    except XApiError:
        raise
    except Exception as exc:
        raise XApiError(_oauth_failure("request a PIN login", exc, settings)) from exc
    oauth_token = _field(request_token, "oauth_token")
    oauth_secret = _field(request_token, "oauth_token_secret")
    if not oauth_token or not oauth_secret:
        raise XApiError(
            "X did not return a request token. Check the app keys and that OAuth 1.0a is enabled."
        )
    output_fn("Open this URL in a browser where you are logged in as the adventure account:")
    output_fn(f"{settings.api_base}/oauth/authorize?oauth_token={oauth_token}")
    output_fn("Approve access, then paste the PIN. The consumer secret is not shown.")
    if pin is None:
        pin = input_fn("PIN: ")
    pin = (pin or "").strip()
    if not _PIN.fullmatch(pin):
        raise ConfigError("The PIN should be the short numeric code X showed after you approved the app.")
    try:
        exchanger = session_factory(
            settings.api_key,
            client_secret=settings.api_secret,
            resource_owner_key=oauth_token,
            resource_owner_secret=oauth_secret,
            verifier=pin,
        )
        access = exchanger.fetch_access_token(f"{settings.api_base}/oauth/access_token")
    except XApiError:
        raise
    except Exception as exc:
        raise XApiError(
            _oauth_failure(
                "exchange the PIN",
                exc,
                settings,
                extra=[oauth_token, oauth_secret],
            )
        ) from exc
    access_token = _field(access, "oauth_token")
    access_secret = _field(access, "oauth_token_secret")
    if not access_token or not access_secret:
        raise XApiError(
            "X did not return access tokens. Request a new PIN and run `adventure auth` again."
        )
    factory = client_factory or _default_client_factory
    client = factory(settings, access_token, access_secret)
    me = client.get_me()
    if not isinstance(me, User):
        raise XApiError("Could not confirm the account username after authorization.")
    _save_tokens(settings.token_path, me, access_token, access_secret)
    output_fn(f"Authorized as @{me.username} (user id {me.id}).")
    output_fn(f"Saved tokens to {settings.token_path} (this path is gitignored).")
    output_fn("Add these environment variables locally and as GitHub Actions secrets:")
    output_fn(f"ADVENTURE_ACCESS_TOKEN={access_token}")
    output_fn(f"ADVENTURE_ACCESS_TOKEN_SECRET={access_secret}")
    output_fn(f"ADVENTURE_USERNAME={me.username}")
    if settings.username and me.username.lower() != settings.username.lower():
        raise UsernameMismatch(
            f"Authorized @{me.username}, but ADVENTURE_USERNAME is @{settings.username}. "
            "The tokens above belong to the account that approved the PIN. "
            "Log in as the adventure account and run `adventure auth` again, "
            "or set ADVENTURE_USERNAME to the handle that was just confirmed. "
            "The bot will not post until they match."
        )
    if not settings.username:
        output_fn(
            "ADVENTURE_USERNAME was not set. Set it to the handle above before posting. "
            "The bot refuses to post if the tokens belong to a different account."
        )


def _default_client_factory(settings: Settings, access_token: str, access_secret: str) -> XClient:
    session = OAuth1Session(
        settings.api_key,
        client_secret=settings.api_secret,
        resource_owner_key=access_token,
        resource_owner_secret=access_secret,
    )
    return XClient(session, api_base=settings.api_base, secrets=settings.secret_values())


def _save_tokens(path: Path, me: User, access_token: str, access_secret: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    payload = {
        "username": me.username,
        "user_id": me.id,
        "access_token": access_token,
        "access_token_secret": access_secret,
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _oauth_failure(
    action: str,
    exc: Exception,
    settings: Settings,
    extra: list[str] | None = None,
) -> str:
    text = redact(str(exc), [settings.api_key, settings.api_secret, *(extra or [])])[:400]
    return (
        f"Could not {action} (OAuth 1.0a). "
        "Check X_API_KEY and X_API_SECRET, and in the developer portal set the app to "
        "Read and Write with OAuth 1.0a enabled. "
        f"X said: {text or exc.__class__.__name__}"
    )


def _field(payload: object, name: str) -> str:
    if isinstance(payload, dict):
        value = payload.get(name) or ""
        return str(value)
    return ""
