"""Stdlib-only RSS 2.0 / RDF / Atom feed parser.

No third-party feedparser dependency: we use xml.etree.ElementTree and
handle namespaced tags by normalizing tag names so RSS and Atom both
yield the same Story fields.
"""

from __future__ import annotations

import email.utils
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser


class FeedParseError(Exception):
    pass


@dataclass
class Entry:
    title: str = ""
    link: str = ""
    summary: str = ""
    published: str = ""  # ISO-8601 or empty
    guid: str = ""


@dataclass
class Feed:
    title: str = ""
    link: str = ""
    entries: list = field(default_factory=list)


class _HTMLTags(HTMLParser):
    """Extract visible text from HTML-ish feed content."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.chunks.append(data.strip())
            self.chunks.append(" ")


def html_to_text(text: str) -> str:
    """Convert HTML or escaped-HTML feed content to plain text."""
    if not text:
        return ""
    text = unescape(text)
    if "<" in text and ">" in text:
        p = _HTMLTags()
        try:
            p.feed(text)
            text = "".join(p.chunks)
        except Exception:  # malformed HTML: fall back to raw text
            pass
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str) -> str:
    """Parse RFC-822 or ISO dates into ISO-8601 UTC; '' if unparseable."""
    if not value:
        return ""
    value = value.strip()
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _localname(tag: str) -> str:
    """urn:namespace and '{ns}tag' -> 'tag'."""
    tag = tag.rsplit("}", 1)[-1]
    return tag.rsplit(":", 1)[-1]


def pick(node, *names):
    for name in names:
        for child in node:
            if _localname(child.tag) == name and (child.text or "").strip():
                return (child.text or "").strip()
    return ""


def _entry_link(node) -> str:
    links = [c for c in node if _localname(c.tag) == "link"]
    for child in links:
        rel = child.get("rel", "alternate")
        href = child.get("href", "")
        if rel == "alternate" and href:
            return href.strip()
    return (links[0].get("href", "").strip() if links else "")


def parse_feed(data: bytes) -> Feed:
    """Parse RSS 2.0, RDF/RSS 1.0 or Atom XML from raw bytes."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FeedParseError(str(exc)) from exc

    name = _localname(root.tag)
    feed = Feed()
    if name == "rss":
        channel = root.find("channel")
        if channel is None:
            raise FeedParseError("rss element without channel")
        feed.title = html_to_text(pick(channel, "title"))
        feed.link = pick(channel, "link")
        for item in channel:
            if _localname(item.tag) != "item":
                continue
            feed.entries.append(_make_entry(item))
    elif name == "feed":  # Atom (default or namespaced)
        feed.title = html_to_text(pick(root, "title"))
        feed.link = _entry_link(root)
        for entry in root:
            if _localname(entry.tag) != "entry":
                continue
            published = pick(entry, "published", "updated")
            feed.entries.append(_make_entry(entry, published=published))
    elif name == "RDF":
        channel = None
        for child in root:
            if _localname(child.tag) == "channel":
                channel = child
                break
        if channel is not None:
            feed.title = html_to_text(pick(channel, "title"))
            feed.link = pick(channel, "link")
        for item in root:
            if _localname(item.tag) == "item":
                feed.entries.append(_make_entry(item))
    else:
        raise FeedParseError(f"unsupported feed root element <{name}>")

    # Drop empty entries; keep everything else.
    feed.entries = [e for e in feed.entries if e.title or e.link]
    return feed


def _make_entry(node, published: str = "") -> Entry:
    summary = pick(node, "description", "summary", "content", "encoded")
    return Entry(
        title=html_to_text(pick(node, "title")),
        link=_entry_link(node) or pick(node, "link"),
        summary=html_to_text(summary),
        published=_parse_date(published or pick(node, "pubDate", "updated")),
        guid=(pick(node, "guid", "id").strip()),
    )
