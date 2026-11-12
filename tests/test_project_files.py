from furbyland_adventure.state import StateStore
from furbyland_adventure.textutil import extract_post_block

from tests.conftest import ROOT


def test_sample_premise_opening_fits_in_one_post():
    premise = (ROOT / "premises" / "sample.md").read_text(encoding="utf-8")
    opening = extract_post_block(premise)
    assert opening
    assert len(opening) <= 280
    assert opening.endswith("?")


def test_seed_state_is_a_story_that_has_not_started():
    state = StateStore(ROOT / "state" / "story.json").load()
    assert state.chapter == 0
    assert state.current_post_id is None
    assert state.chapters == []


def test_schedule_is_commented_out_until_someone_opts_in():
    text = (ROOT / ".github" / "workflows" / "advance-story.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch" in text
    assert "X_API_KEY" in text
    assert "ADVENTURE_ACCESS_TOKEN_SECRET" in text
    saw_schedule = False
    for line in text.splitlines():
        stripped = line.strip()
        if "schedule:" in stripped or "cron:" in stripped:
            saw_schedule = True
            assert stripped.startswith("#"), line
    assert saw_schedule


def test_secrets_are_gitignored_and_the_example_is_placeholders():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".secrets/" in ignore
    assert "\n.env\n" in f"\n{ignore}\n"
    assert "!.env.example" in ignore
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in (
        "X_API_KEY",
        "X_API_SECRET",
        "ADVENTURE_ACCESS_TOKEN",
        "ADVENTURE_ACCESS_TOKEN_SECRET",
        "ADVENTURE_USERNAME",
    ):
        assert name in example
    assert "your_api_key_here" in example
    assert "your_api_secret_here" in example
