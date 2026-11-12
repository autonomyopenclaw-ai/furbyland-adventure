"""In-memory HTTP stand-in for the X API."""

from __future__ import annotations

import json

from furbyland_adventure.config import Settings
from furbyland_adventure.writer import TemplateWriter


class FakeResponse:
    def __init__(self, status, payload, headers=None):
        self.status_code = status
        self._payload = payload
        self.headers = headers or {}
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        if not isinstance(self._payload, dict):
            raise ValueError("not json")
        return self._payload


class FakeSession:
    def __init__(self):
        self.calls = []
        self.me = {"id": "42", "name": "Adventure", "username": "adventurer"}
        self.search_pages = [{"meta": {"result_count": 0}}]
        self._search_i = 0
        self.fail = {}
        self._next_id = 1000

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if "/2/users/me" in url:
            if "me" in self.fail:
                return self.fail["me"]
            return FakeResponse(200, {"data": dict(self.me)})
        if "/2/tweets/search/recent" in url:
            if "search" in self.fail:
                return self.fail["search"]
            if self._search_i >= len(self.search_pages):
                page = {"meta": {"result_count": 0}}
            else:
                page = self.search_pages[self._search_i]
                self._search_i += 1
            return FakeResponse(200, page)
        return FakeResponse(404, {"title": "Not Found", "detail": url, "status": 404})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        if "post" in self.fail:
            return self.fail["post"]
        self._next_id += 1
        text = (kwargs.get("json") or {}).get("text", "")
        return FakeResponse(200, {"data": {"id": str(self._next_id), "text": text}})

    def posted_texts(self):
        texts = []
        for method, _url, kwargs in self.calls:
            if method == "POST":
                texts.append((kwargs.get("json") or {}).get("text", ""))
        return texts


def make_settings(tmp_path, **overrides) -> Settings:
    values = dict(
        username="adventurer",
        state_path=tmp_path / "story.json",
        premise_path=tmp_path / "premise.md",
        token_path=tmp_path / "tokens.json",
        api_key="key",
        api_secret="secretvalue",
        access_token="token",
        access_token_secret="tokensecret",
        llm="none",
    )
    values.update(overrides)
    return Settings(**values)


def template_writer():
    return TemplateWriter()


PREMISE = (
    "<!-- post -->\n"
    "The lantern fox waits beside the humming hill. Which path do you choose?\n"
    "<!-- /post -->\n"
)


def tweet(tweet_id, text, author_id, created_at, likes, replied_to):
    return {
        "id": tweet_id,
        "text": text,
        "author_id": author_id,
        "created_at": created_at,
        "public_metrics": {"like_count": likes},
        "referenced_tweets": [{"type": "replied_to", "id": replied_to}],
    }


def user(user_id, username, name=None):
    return {"id": user_id, "username": username, "name": name or username}
