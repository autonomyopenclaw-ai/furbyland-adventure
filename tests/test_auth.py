import json
import os

import pytest

from furbyland_adventure.auth import run_auth
from furbyland_adventure.config import Settings
from furbyland_adventure.errors import ConfigError, UsernameMismatch, XApiError
from furbyland_adventure.x_client import User


class RecordingFactory:
    def __init__(self, boom=None):
        self.calls = []
        self.boom = boom

    def __call__(self, client_key, **kwargs):
        self.calls.append({"client_key": client_key, **kwargs})
        if self.boom and len(self.calls) == 1:
            raise RuntimeError(self.boom)
        return _Stage(kwargs)


class _Stage:
    def __init__(self, kwargs):
        self.kwargs = kwargs

    def fetch_request_token(self, url):
        assert url.endswith("/oauth/request_token")
        return {"oauth_token": "REQUESTTOKEN", "oauth_token_secret": "REQUESTSECRET"}

    def fetch_access_token(self, url):
        assert url.endswith("/oauth/access_token")
        assert self.kwargs["verifier"] == "1234567"
        return {"oauth_token": "ACCESSTOKEN", "oauth_token_secret": "ACCESSSECRET"}


def _settings(tmp_path, **overrides):
    values = dict(
        api_key="APPKEYVALUE",
        api_secret="CONSUMERSECRETVALUE",
        token_path=tmp_path / "tokens.json",
        api_base="https://api.x.com",
    )
    values.update(overrides)
    return Settings(**values)


def test_pin_flow_saves_tokens_and_never_prints_the_consumer_secret(tmp_path):
    output = []
    seen = {}

    def client_factory(settings, access_token, access_secret):
        seen["access_token"] = access_token
        seen["access_secret"] = access_secret
        return _Me("adventurer")

    factory = RecordingFactory()
    run_auth(
        _settings(tmp_path),
        pin="1234567",
        output_fn=output.append,
        session_factory=factory,
        client_factory=client_factory,
    )
    text = "\n".join(output)
    assert factory.calls[0]["callback_uri"] == "oob"
    assert "oauth/authorize?oauth_token=REQUESTTOKEN" in text
    assert "REQUESTSECRET" not in text
    assert "CONSUMERSECRETVALUE" not in text
    assert "ADVENTURE_ACCESS_TOKEN=ACCESSTOKEN" in text
    assert "ADVENTURE_ACCESS_TOKEN_SECRET=ACCESSSECRET" in text
    assert "ADVENTURE_USERNAME=adventurer" in text
    saved = json.loads((tmp_path / "tokens.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == "ACCESSTOKEN"
    assert saved["username"] == "adventurer"
    assert "CONSUMERSECRETVALUE" not in json.dumps(saved)
    mode = (tmp_path / "tokens.json").stat().st_mode & 0o777
    assert mode == 0o600
    assert seen["access_secret"] == "ACCESSSECRET"


def test_auth_mismatch_keeps_the_secret_out_of_the_error(tmp_path):
    output = []

    def client_factory(settings, access_token, access_secret):
        return _Me("othername")

    with pytest.raises(UsernameMismatch) as caught:
        run_auth(
            _settings(tmp_path, username="adventurer"),
            pin="1234567",
            output_fn=output.append,
            session_factory=RecordingFactory(),
            client_factory=client_factory,
        )
    text = "\n".join(output)
    assert "CONSUMERSECRETVALUE" not in text
    assert "CONSUMERSECRETVALUE" not in str(caught.value)
    assert "@othername" in str(caught.value)
    assert (tmp_path / "tokens.json").is_file()


def test_oauth_errors_redact_the_consumer_secret(tmp_path):
    output = []
    factory = RecordingFactory(boom="failed because CONSUMERSECRETVALUE was wrong")
    try:
        run_auth(
            _settings(tmp_path),
            pin="1234567",
            output_fn=output.append,
            session_factory=factory,
            client_factory=lambda *args: None,
        )
    except XApiError as exc:
        message = str(exc)
    else:
        raise AssertionError("expected an API error")
    assert "CONSUMERSECRETVALUE" not in message
    assert "[redacted]" in message
    assert "CONSUMERSECRETVALUE" not in "\n".join(output)


def test_bad_pin_stops_before_the_access_token_exchange(tmp_path):
    factory = RecordingFactory()
    try:
        run_auth(
            _settings(tmp_path),
            pin="nope",
            output_fn=lambda _line: None,
            session_factory=factory,
            client_factory=lambda *args: None,
        )
    except ConfigError:
        pass
    else:
        raise AssertionError("expected a config error")
    assert "verifier" not in factory.calls[-1]


class _Me:
    def __init__(self, username):
        self.username = username

    def get_me(self):
        return User(id="9", username=self.username, name="Adventure")


def test_token_path_comes_from_the_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("ADVENTURE_TOKEN_PATH", str(tmp_path / "from-env.json"))
    from furbyland_adventure.config import load_settings

    assert load_settings().token_path == tmp_path / "from-env.json"
    assert "ADVENTURE_TOKEN_PATH" in os.environ
