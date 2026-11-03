import os
import unittest

from digest.feedparse import parse_feed
from digest.output import render_markdown, render_plain
from digest.stories import Story, sort_stories
from digest.topics import group_stories

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def stories_from(name):
    with open(os.path.join(FIXTURES, name), "rb") as fh:
        data = fh.read()
    feed = parse_feed(data)
    return [
        Story(title=e.title, link=e.link, summary=e.summary, published=e.published, feed=name)
        for e in feed.entries
    ]


class TestRendering(unittest.TestCase):
    def setUp(self):
        self.sections = group_stories(sort_stories(stories_from("rss_basic.xml") + stories_from("atom_sample.xml")))
        story = self.sections["General"][0] if "General" in self.sections else None
        if story:
            story.summary_text = "One calm paragraph, written by a friendly model."

    def test_markdown(self):
        text = render_markdown(self.sections, title="Morning Digest", notes=["- stub note"])
        self.assertTrue(text.startswith("# Morning Digest"))
        self.assertIn("## ", text)
        self.assertIn("](https://", text)
        self.assertIn("One calm paragraph, written by a friendly model.", text)

    def test_plain_friendly(self):
        text = render_plain(self.sections, notes=["- stub note"])
        self.assertIn("=" * 74, text)
        self.assertIn("MORNING DIGEST", text.upper())
        for line in text.splitlines():
            self.assertLessEqual(len(line), 100, line)

    def test_no_stories(self):
        text = render_plain({"General": []}, notes=["nothing yet"])
        self.assertIn("nothing yet", text)


if __name__ == "__main__":
    unittest.main()
