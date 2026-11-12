from furbyland_adventure.engine import finalize_chapter
from furbyland_adventure.textutil import excerpt, fit_posts, scrub_mentions
from furbyland_adventure.writer import TemplateWriter


def test_exact_limit_is_unchanged():
    text = ("a" * 279) + "?"
    assert len(text) == 280
    assert fit_posts(text, 280, split=False) == [text]


def test_over_limit_is_shortened_to_one_question():
    text = ("word " * 80) + "and then they rest"
    parts = fit_posts(text, 280, split=False)
    assert len(parts) == 1
    assert len(parts[0]) <= 280
    assert "?" in parts[0]


def test_long_chapter_can_split_into_a_short_thread():
    sentence = "The lantern fox walks onward through the humming trees."
    text = " ".join([sentence] * 12) + " Which way now?"
    parts = fit_posts(text, 80, split=True)
    assert len(parts) > 1
    assert all(len(part) <= 80 for part in parts)
    assert "?" in parts[-1]
    single = fit_posts(text, 80, split=False)
    assert len(single) == 1
    assert len(single[0]) <= 80


def test_blank_text_becomes_a_question():
    parts = fit_posts("   ", 280, split=False)
    assert len(parts) == 1
    assert "?" in parts[0]
    assert len(parts[0]) <= 280


def test_mentions_are_removed_unless_one_handle_is_allowed():
    text = "Hello @bob and @alice, the pond is calm. What next?"
    assert "@" not in scrub_mentions(text, None)
    assert "bob" in scrub_mentions(text, None)
    kept = scrub_mentions(text, "bob")
    assert "@bob" in kept
    assert "@alice" not in kept


def test_excerpt_drops_mentions_and_quotes():
    quote = excerpt('go @carol and say "hello there friend"', 80)
    assert "@" not in quote
    assert '"' not in quote
    assert "carol" in quote


def test_finalize_replaces_an_unsafe_chapter_and_strips_mentions():
    parts = finalize_chapter(
        "Oh shit @bob what now?",
        max_chars=280,
        split=False,
        allow_handle=None,
        scrub=True,
    )
    assert len(parts) == 1
    assert len(parts[0]) <= 280
    assert "shit" not in parts[0].lower()
    assert "@" not in parts[0]
    assert "?" in parts[0]


def test_template_chapter_stays_within_a_short_limit():
    draft = TemplateWriter().next_chapter(
        summary="A fox waits.",
        chapter_number=4,
        suggestion="listen by the mirror pond and sing the lost chorus for a long time",
        credit='a reader suggested "listen by the mirror pond"',
        max_chars=80,
        allow_mentions=False,
    )
    assert len(draft.text) <= 80
    assert "?" in draft.text
    assert "@" not in draft.text
    assert "reader" in draft.text
