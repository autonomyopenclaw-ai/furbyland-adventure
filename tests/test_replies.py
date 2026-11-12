import random

from furbyland_adventure.replies import Reply, nudge_text, select_reply
from furbyland_adventure.x_client import XClient

from tests.fakes import FakeSession, tweet, user


def _reply(reply_id, text, likes, created_at, username="reader"):
    return Reply(
        id=reply_id,
        text=text,
        author_id=username,
        username=username,
        display_name=username,
        created_at=created_at,
        like_count=likes,
        replied_to_id="100",
    )


def test_most_liked_wins():
    replies = [
        _reply("1", "walk the quiet stairs", 2, "2026-01-01T00:00:00.000Z"),
        _reply("2", "listen by the mirror pond", 9, "2026-01-03T00:00:00.000Z"),
        _reply("3", "hum with the orchard", 4, "2026-01-02T00:00:00.000Z"),
    ]
    chosen = select_reply(replies, "most_liked", random.Random(0))
    assert chosen.id == "2"


def test_tie_goes_to_the_earliest_reply():
    replies = [
        _reply("20", "take the later bridge", 5, "2026-02-02T00:00:00.000Z"),
        _reply("10", "take the early bridge", 5, "2026-02-01T00:00:00.000Z"),
        _reply("30", "take the last bridge", 1, "2026-01-01T00:00:00.000Z"),
    ]
    chosen = select_reply(replies, "most_liked", random.Random(0))
    assert chosen.id == "10"


def test_numeric_id_breaks_a_remaining_tie():
    replies = [
        _reply("10", "path ten", 3, "2026-02-01T00:00:00.000Z"),
        _reply("2", "path two", 3, "2026-02-01T00:00:00.000Z"),
    ]
    chosen = select_reply(replies, "most_liked", random.Random(0))
    assert chosen.id == "2"


def test_missing_timestamp_loses_a_like_tie():
    replies = [
        _reply("8", "undated idea here", 4, ""),
        _reply("9", "dated idea here", 4, "2026-02-01T00:00:00.000Z"),
    ]
    chosen = select_reply(replies, "most_liked", random.Random(0))
    assert chosen.id == "9"


def test_random_uses_the_rng_instead_of_likes():
    replies = [
        _reply("a", "popular idea here", 10, "2020-01-01T00:00:00.000Z"),
        _reply("b", "quiet idea here", 1, "2020-01-02T00:00:00.000Z"),
    ]

    class Tail:
        def choice(self, items):
            return items[-1]

    assert select_reply(replies, "most_liked", random.Random(0)).id == "a"
    assert select_reply(replies, "random", Tail()).id == "b"


def test_search_results_are_parsed_before_selection():
    session = FakeSession()
    session.search_pages = [
        {
            "data": [
                tweet("10", "walk the quiet stairs", "5", "2026-01-02T00:00:00.000Z", 1, "100"),
                tweet("11", "listen by the mirror pond", "6", "2026-01-02T00:00:01.000Z", 4, "100"),
                tweet("12", "sing beside the mirror pond", "7", "2026-01-01T00:00:00.000Z", 4, "100"),
                tweet("13", "reply to someone else", "8", "2026-01-01T00:00:00.000Z", 99, "999"),
                tweet("14", "our own note about the path", "42", "2026-01-01T00:00:00.000Z", 99, "100"),
            ],
            "includes": {
                "users": [
                    user("5", "stairsfan"),
                    user("6", "pondfan"),
                    user("7", "earlyfan"),
                    user("8", "other"),
                    user("42", "adventurer"),
                ]
            },
            "meta": {"result_count": 5},
        }
    ]
    found = XClient(session).direct_replies("100", "100", "42")
    assert {reply.id for reply in found} == {"10", "11", "12"}
    chosen = select_reply(found, "most_liked", random.Random(0))
    assert chosen.id == "12"
    assert chosen.username == "earlyfan"
    assert chosen.like_count == 4


def test_search_follows_next_token():
    session = FakeSession()
    session.search_pages = [
        {
            "data": [tweet("10", "first page idea", "5", "2026-01-01T00:00:00.000Z", 1, "100")],
            "includes": {"users": [user("5", "one")]},
            "meta": {"result_count": 1, "next_token": "page-2"},
        },
        {
            "data": [tweet("11", "second page idea", "6", "2026-01-02T00:00:00.000Z", 3, "100")],
            "includes": {"users": [user("6", "two")]},
            "meta": {"result_count": 1},
        },
    ]
    found = XClient(session).direct_replies("100", "100", "42")
    assert [reply.id for reply in found] == ["10", "11"]
    search_calls = [call for call in session.calls if "search/recent" in call[1]]
    assert search_calls[1][2]["params"]["next_token"] == "page-2"


def test_nudge_fits_and_names_the_selection_rule():
    liked = nudge_text("most_liked")
    random_nudge = nudge_text("random")
    assert len(liked) <= 280
    assert len(random_nudge) <= 280
    assert "most-liked" in liked
    assert "random" in random_nudge
    assert "@" not in liked
