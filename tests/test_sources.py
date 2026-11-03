import os
import unittest

from digest.sources import load_source_file, parse_opml, parse_url_list, validate_url

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


class TestSources(unittest.TestCase):
    def test_opml(self):
        sources = load_source_file(os.path.join(FIXTURES, "list.opml"))
        urls = [s.url for s in sources]
        self.assertEqual(len(sources), 3)
        self.assertIn("https://example.org/arcadia/feed", urls)
        self.assertIn("https://harbor.example.com/feed", urls)
        names = {s.name for s in sources}
        self.assertIn("Arcadia Tech Stream", names)
        self.assertIn("Harbor Notes Journal", names)
        unnamed = [s for s in sources if not s.name]
        self.assertEqual(len(unnamed), 1)

    def test_url_list(self):
        sources = parse_url_list(
            "# comment\n\nhttps://a.example.com/feed | A Feed\n   https://b.example.com/rss?x=1  # trailing tag\n"
        )
        self.assertEqual([s.url for s in sources],
                         ["https://a.example.com/feed", "https://b.example.com/rss?x=1"])
        self.assertEqual(sources[0].name, "A Feed")

    def test_url_list_selects_by_extension(self):
        with open(os.path.join(FIXTURES, "list.txt"), "rb") as fh:
            text = fh.read().decode("utf-8")
        self.assertIn("https://example.org/arcadia/feed", parse_url_list(text)[0].url)

    def test_validate(self):
        self.assertTrue(validate_url("https://example.com/f"))
        self.assertTrue(validate_url("file:///tmp/feed.xml"))
        self.assertFalse(validate_url("ftp://example.com/f"))
        self.assertFalse(validate_url("not-a-url"))

    def test_opml_without_feeds(self):
        with self.assertRaises(ValueError):
            parse_opml(b"<opml><body><outline text='empty'/></body></opml>")


if __name__ == "__main__":
    unittest.main()
