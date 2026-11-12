import json

from furbyland_adventure.cli import main
from furbyland_adventure.state import StateStore, StoryState
from furbyland_adventure.x_client import XClient

from tests.fakes import PREMISE, FakeResponse, FakeSession


def _creds(monkeypatch):
    monkeypatch.setenv("X_API_KEY", "key")
    monkeypatch.setenv("X_API_SECRET", "secretvalue")
    monkeypatch.setenv("ADVENTURE_ACCESS_TOKEN", "token")
    monkeypatch.setenv("ADVENTURE_ACCESS_TOKEN_SECRET", "tokensecret")
    monkeypatch.setenv("ADVENTURE_USERNAME", "adventurer")


def test_start_dry_run_prints_the_premise_and_does_not_save(capsys, tmp_path):
    premise = tmp_path / "opening.md"
    premise.write_text(PREMISE, encoding="utf-8")
    code = main(["start", "--dry-run", "--premise", str(premise)])
    assert code == 0
    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "lantern fox" in out
    assert not (tmp_path / "story.json").exists()


def test_advance_without_credentials_fails_clearly(capsys):
    code = main(["advance", "--dry-run"])
    assert code == 2
    err = capsys.readouterr().err
    assert "ADVENTURE_USERNAME" in err
    assert "Traceback" not in err


def test_auth_without_keys_fails_clearly(capsys):
    code = main(["auth"])
    assert code == 2
    err = capsys.readouterr().err
    assert "X_API_KEY" in err
    assert "consumer secret" in err.lower()
    assert "Traceback" not in err


def test_status_dry_run_is_local(capsys):
    code = main(["status", "--dry-run"])
    assert code == 0
    out = capsys.readouterr().out
    assert "not started" in out
    assert "skipped" in out


def test_cli_start_posts_when_the_username_matches(monkeypatch, capsys, tmp_path):
    _creds(monkeypatch)
    premise = tmp_path / "opening.md"
    premise.write_text(PREMISE, encoding="utf-8")
    session = FakeSession()
    monkeypatch.setattr(
        "furbyland_adventure.cli.build_x_client",
        lambda settings: XClient(session, secrets=["secretvalue"]),
    )
    code = main(["start", "--premise", str(premise)])
    assert code == 0
    out = capsys.readouterr().out
    assert "https://x.com/adventurer/status/1001" in out
    state = json.loads((tmp_path / "story.json").read_text(encoding="utf-8"))
    assert state["chapter"] == 1
    assert state["current_post_id"] == "1001"


def test_cli_refuses_the_wrong_account_without_a_traceback(monkeypatch, capsys, tmp_path):
    _creds(monkeypatch)
    StateStore(tmp_path / "story.json").save(
        StoryState(chapter=1, current_post_id="100", thread_root_id="100", summary="Begun.")
    )
    session = FakeSession()
    session.me["username"] = "someoneelse"
    monkeypatch.setattr(
        "furbyland_adventure.cli.build_x_client",
        lambda settings: XClient(session, secrets=["secretvalue"]),
    )
    code = main(["advance"])
    assert code == 3
    err = capsys.readouterr().err
    assert "someoneelse" in err
    assert "Traceback" not in err
    assert session.posted_texts() == []


def test_cli_rate_limit_does_not_crash(monkeypatch, capsys, tmp_path):
    _creds(monkeypatch)
    StateStore(tmp_path / "story.json").save(
        StoryState(chapter=1, current_post_id="100", thread_root_id="100", summary="Begun.")
    )
    session = FakeSession()
    session.fail["search"] = FakeResponse(
        429,
        {"title": "Too Many Requests"},
        headers={"x-rate-limit-reset": "1700000000"},
    )
    monkeypatch.setattr(
        "furbyland_adventure.cli.build_x_client",
        lambda settings: XClient(session, secrets=["secretvalue"]),
    )
    code = main(["advance"])
    assert code == 4
    err = capsys.readouterr().err
    assert "429" in err
    assert "Traceback" not in err
    assert session.posted_texts() == []
    assert "secretvalue" not in err
