import os
import unittest

from digest.feedparse import parse_feed
from digest.stories import Story, sort_stories
from digest.topics import group_stories, match_topic

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def stories_from(name):
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        data = fh.read()
    feed = parse_feed(data)
    return [
        Story(title=e.title, link=e.link, summary=e.summary, published=e.published, feed=name)
        for e in feed.entries
    ]


def topic_of(title, summary=""):
    return match_topic(Story(title=title, link="", summary=summary))


class TestMatch(unittest.TestCase):
    def test_named_topics(self):
        self.assertEqual(topic_of("OpenAI launches a new LLM"), "AI & Machine Learning")
        self.assertEqual(topic_of("Ollama 0.5 runs local LLM on a homelab", "self-host your gguf weights"), "Local AI & Self-Hosting")
        self.assertEqual(topic_of("Final Fantasy XIV patch adds a fishing duty"), "Gaming")
        self.assertEqual(topic_of("Vienna Gambit checkmate drills"), "Chess")
        self.assertEqual(topic_of("KDP self-publishing tips for authors"), "Books & Publishing")
        self.assertEqual(topic_of("eBay reselling inventory is selling fast"), "Selling & Marketplaces")

    def test_short_keywords_do_not_match_inside_words(self):
        # 'ai' must not match inside 'chair' or 'train'; falls to leftover cluster
        self.assertIsInstance(topic_of("Chair daily repair corner"), tuple)
        # but a real 'AI' word still matches
        self.assertEqual(topic_of("A new AI model"), "AI & Machine Learning")

    def test_leftover_signature(self):
        result = topic_of("Zorgle blorf qux stone", "unusual words here")
        self.assertIsInstance(result, tuple)


class TestGrouping(unittest.TestCase):
    def test_fixture_groups_sum(self):
        stories = stories_from("rss_basic.xml") + stories_from("atom_sample.xml") + stories_from("rdf_sample.xml")
        sections = group_stories(sort_stories(stories))
        grouped_total = sum(len(v) for v in sections.values())
        self.assertEqual(grouped_total, len(stories))
        self.assertTrue(all(isinstance(k, str) for k in sections))

    def test_fixture_has_expected_sections(self):
        stories = stories_from("rss_basic.xml")
        sections = group_stories(sort_stories(stories))
        names = set(sections)
        self.assertIn("Gaming", names)
        self.assertIn("Chess", names)

    def test_leftover_cluster(self):
        stories = [
            Story(title="Zorgler blorf update", link="https://e.com/1", summary="qux zorble blorf"),
            Story(title="Another blorf qux zorble report", link="https://e.com/2", summary="blorf qux"),
        ]
        sections = group_stories(sort_stories(stories))
        self.assertEqual(sum(len(v) for v in sections.values()), 2)
        self.assertTrue(any(k.startswith("Related:") for k in sections))

    def test_single_stragger_goes_to_general(self):
        stories = [Story(title="Zorgler blorf update", link="https://e.com/1", summary="qux zorble blorf")]
        sections = group_stories(sort_stories(stories))
        self.assertIn("General", sections)


if __name__ == "__main__":
    unittest.main()
