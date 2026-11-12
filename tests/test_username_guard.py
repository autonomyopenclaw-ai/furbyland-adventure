import pytest

from furbyland_adventure.engine import Adventure, require_user
from furbyland_adventure.errors import UsernameMismatch, XApiError
from furbyland_adventure.state import StateStore
from furbyland_adventure.x_client import XClient

from tests.fakes import PREMISE, FakeResponse, FakeSession, make_settings, template_writer


def test_username_guard_refuses_a_different_account_before_posting(tmp_path):
    session = FakeSession()
    session.me["username"] = "someoneelse"
    client = XClient(session, secrets=["secretvalue"])
    with pytest.raises(UsernameMismatch) as caught:
        require_user(client, "adventurer")
    assert "@someoneelse" in str(caught.value)
    assert "@adventurer" in str(caught.value)
    assert session.posted_texts() == []

    adventure = Adventure(
        make_settings(tmp_path),
        client,
        template_writer(),
        StateStore(tmp_path / "story.json"),
    )
    with pytest.raises(UsernameMismatch):
        adventure.start(PREMISE, dry_run=False, force=False)
    assert session.posted_texts() == []
    assert not (tmp_path / "story.json").exists()


def test_matching_username_is_allowed_to_post(tmp_path):
    session = FakeSession()
    client = XClient(session)
    me = require_user(client, "adventurer")
    assert me.username == "adventurer"
    adventure = Adventure(
        make_settings(tmp_path),
        client,
        template_writer(),
        StateStore(tmp_path / "story.json"),
    )
    result = adventure.start(PREMISE, dry_run=False, force=False)
    assert result.chapter == 1
    assert result.post_ids
    assert session.posted_texts()


def test_users_me_401_names_the_fix_and_hides_secrets():
    session = FakeSession()
    session.fail["me"] = FakeResponse(
        401,
        {"title": "Unauthorized", "detail": "bad secretvalue in the signature"},
    )
    client = XClient(session, secrets=["secretvalue"])
    with pytest.raises(XApiError) as caught:
        client.get_me()
    message = str(caught.value)
    assert caught.value.status_code == 401
    assert "401" in message
    assert "adventure auth" in message
    assert "consumer secret" in message
    assert "secretvalue" not in message
    assert "[redacted]" in message


def test_search_403_explains_the_paid_plan():
    session = FakeSession()
    session.fail["search"] = FakeResponse(
        403,
        {
            "title": "Forbidden",
            "detail": "Sorry, you are not authorized to use this endpoint.",
        },
    )
    client = XClient(session)
    with pytest.raises(XApiError) as caught:
        client.direct_replies("100", "100", "42")
    message = str(caught.value)
    assert caught.value.status_code == 403
    assert "paid" in message.lower()
    assert "recent search" in message.lower()


def test_rate_limit_includes_the_reset_time():
    session = FakeSession()
    session.fail["search"] = FakeResponse(
        429,
        {"title": "Too Many Requests"},
        headers={"x-rate-limit-reset": "1700000000"},
    )
    client = XClient(session)
    with pytest.raises(XApiError) as caught:
        client.direct_replies("100", "100", "42")
    message = str(caught.value)
    assert caught.value.status_code == 429
    assert "1700000000" in message
    assert "UTC" in message
    assert "Nothing further was posted" in message


def test_duplicate_post_is_explained():
    session = FakeSession()
    session.fail["post"] = FakeResponse(
        403,
        {
            "title": "Forbidden",
            "detail": "You are not allowed to create a Tweet with duplicate content.",
        },
    )
    client = XClient(session)
    with pytest.raises(XApiError) as caught:
        client.post_tweet("Hello there. What next?", None)
    assert "already posted" in str(caught.value)


def test_client_refuses_a_chapter_over_280_without_calling_x():
    session = FakeSession()
    client = XClient(session)
    with pytest.raises(XApiError):
        client.post_tweet("a" * 281, None)
    assert session.calls == []


def test_reply_post_targets_the_chapter():
    session = FakeSession()
    client = XClient(session)
    client.post_tweet("The fox waits. What next?", "555")
    body = session.calls[0][2]["json"]
    assert body["text"] == "The fox waits. What next?"
    assert body["reply"]["in_reply_to_tweet_id"] == "555"


def test_non_json_error_does_not_crash():
    session = FakeSession()
    session.fail["me"] = FakeResponse(500, "<html>down</html>")
    with pytest.raises(XApiError) as caught:
        XClient(session).get_me()
    assert "500" in str(caught.value)
