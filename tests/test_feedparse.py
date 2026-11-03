import os
import unittest

from digest.feedparse import FeedParseError, html_to_text, parse_feed

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        return fh.read()


class TestRSS(unittest.TestCase):
    def setUp(self):
        self.feed = parse_feed(fixture("rss_basic.xml"))

    def test_channel(self):
        self.assertEqual(self.feed.title, "Arcadia Tech Stream")
        self.assertEqual(self.feed.link, "https://example.org/arcadia")

    def test_entries(self):
        titles = [e.title for e in self.feed.entries]
        self.assertIn("Paperwork Organizer App Gets ADHD-Friendly Checklists", titles)
        self.assertEqual(len(self.feed.entries), 5)

    def test_date(self):
        first = self.feed.entries[0]
        self.assertEqual(first.published, "2026-11-03T08:15:00+00:00")

    def test_html_summary(self):
        story = [e for e in self.feed.entries if "Paperwork" in e.title][0]
        self.assertIn("bold HTML", story.summary)
        self.assertNotIn("<img", story.summary)

    def test_guid(self):
        first = self.feed.entries[0]
        self.assertEqual(first.guid, "https://example.org/ai/local-llm-runner")


class TestAtom(unittest.TestCase):
    def setUp(self):
        self.feed = parse_feed(fixture("atom_sample.xml"))

    def test_channel(self):
        self.assertEqual(self.feed.title, "Harbor Notes Journal")
        self.assertEqual(self.feed.link, "https://harbor.example.com/")

    def test_entry_links(self):
        self.assertTrue(all(e.link.startswith("https://harbor.example.com/") for e in self.feed.entries))

    def test_blank_title_falls_back(self):
        entry = self.feed.entries[3]
        self.assertEqual(entry.title, "")
        self.assertTrue(entry.summary)

    def test_content_html_decoded(self):
        entry = self.feed.entries[0]
        self.assertIn("KDP authors are self-publishing more audiobooks", entry.summary)
        self.assertNotIn("<p>", entry.summary)


class TestRDF(unittest.TestCase):
    def test_rdf(self):
        feed = parse_feed(fixture("rdf_sample.xml"))
        self.assertEqual(feed.title, "Vorg Science Desk")
        self.assertEqual(len(feed.entries), 1)
        self.assertEqual(feed.entries[0].link, "https://vorg.example.edu/lunar-oddity")


class TestMisc(unittest.TestCase):
    def test_invalid(self):
        with self.assertRaises(FeedParseError):
            parse_feed(b"not xml at all <><")

    def test_html_to_text(self):
        self.assertEqual(html_to_text("plain"), "plain")
        self.assertEqual(html_to_text("a &amp; b"), "a & b")
        self.assertEqual(html_to_text("<p>Hello</p><script>evil()</script>world"), "Hello world")


if __name__ == "__main__":
    unittest.main()
