import unittest
from datetime import datetime, timedelta, timezone

from digest.stories import (
    Story,
    dedupe_stories,
    filter_recent,
    normalize_title,
    normalize_url,
    sort_stories,
    titles_similar,
)


def story(title, link, feed="Feed A", published="2026-11-03T08:00:00+00:00", summary=""):
    return Story(title=title, link=link, feed=feed, summary=summary, published=published)


class TestNormalizeUrl(unittest.TestCase):
    def test_strip_tracking(self):
        a = normalize_url("https://example.com/x?utm_source=rss&id=7&fbclid=abc")
        b = normalize_url("https://example.com/x?id=7")
        self.assertEqual(a, b)

    def test_trailing_slash_and_case(self):
        # netloc is case-insensitive, path stays case-sensitive
        self.assertEqual(
            normalize_url("https://Example.COM/Post/"),
            normalize_url("https://example.com/Post"),
        )
        self.assertNotEqual(
            normalize_url("https://example.com/Post"),
            normalize_url("https://example.com/post"),
        )


class TestTitleSimilarity(unittest.TestCase):
    def test_exact_and_punctuation(self):
        self.assertTrue(titles_similar("AI Studio Ships Local LLM Runner for Home Servers", "ai studio ships local llm runner for home servers!!"))

    def test_different(self):
        self.assertFalse(titles_similar("Chess morning opens", "Budgeting your taxes today"))

    def test_normalize(self):
        self.assertEqual(normalize_title("A—Quiet Morning!"), "a quiet morning")


class TestDedupe(unittest.TestCase):
    def test_url_dupes_merged(self):
        originals = [
            story("T1", "https://example.com/a?utm_source=x", "Feed A"),
            story("T1", "https://example.com/a", "Feed B"),
            story("T2", "https://example.com/b", "Feed C"),
        ]
        deduped = dedupe_stories(originals)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0].sources, ["Feed A", "Feed B"])
        self.assertEqual(deduped[1].sources, ["Feed C"])

    def test_fuzzy_title_dedupe(self):
        originals = [
            story("AI Studio Ships Local LLM Runner for Home Servers", "https://example.org/1", "A"),
            story("AI Studio Ships Local LLM Runner for Home Servers!!", "https://mirror.example.net/2", "B"),
        ]
        deduped = dedupe_stories(originals)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].sources, ["A", "B"])

    def test_empty_links_are_not_merged_by_url(self):
        deduped = dedupe_stories([story("A Title", "", "F1"), story("A Title", "", "F2")])
        self.assertEqual(len(deduped), 1)  # merged by title, not by URL


class TestFilterAndSort(unittest.TestCase):
    def test_max_age(self):
        old = story("Old", "https://e.com/old", published=(datetime.now(timezone.utc) - timedelta(days=10)).isoformat())
        today = story("New", "https://e.com/new")
        self.assertEqual([s.title for s in filter_recent([old, today], 3)], ["New"])
        self.assertEqual(len(filter_recent([old, today], None)), 2)

    def test_undated_sinks(self):
        a = story("Zed", "https://e.com/z")
        undated = story("Undated", "https://e.com/u", published="")
        old = story("Old", "https://e.com/old", published="2026-11-02T00:00:00+00:00")
        ordered = sort_stories([a, undated, old])
        self.assertEqual([s.title for s in ordered], ["Zed", "Old", "Undated"])


if __name__ == "__main__":
    unittest.main()
