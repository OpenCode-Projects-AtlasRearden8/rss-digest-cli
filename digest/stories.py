"""Story model, dedupe and filtering."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

TITLE_SIMILARITY = 0.92

_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "referrer",
    "igshid", "vero_id", "yclid", "sr_share", "sh", "si",
}


@dataclass
class Story:
    title: str
    link: str
    feed: str = "unknown feed"
    summary: str = ""
    published: str = ""
    summary_text: str = ""      # optional AI one-paragraph summary
    topics: list = field(default_factory=list)
    sources: list = field(default_factory=list)  # feeds that carried it

    def age_days(self, now: datetime | None = None) -> float:
        now = now or datetime.now(timezone.utc)
        try:
            then = datetime.fromisoformat(self.published)
        except ValueError:
            return float("inf")
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return max(0.0, (now - then).total_seconds() / 86400)


def normalize_url(url: str) -> str:
    """Strip tracking params and trivial case differences for dedupe."""
    url = url.strip()
    if not url:
        return ""
    parsed = urlparse(url)
    try:
        query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
                 if k.lower() not in _TRACKING_PARAMS]
    except ValueError:
        query = []
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return urlunparse((parsed.scheme, netloc, path, "", urlencode(query), ""))


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"[^a-z0-9 ]+", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def titles_similar(a: str, b: str) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Cheap length guard: wildly different lengths can't be duplicates.
    if len(na) > 2 * len(nb) or len(nb) > 2 * len(na):
        return False
    if na[:40] == nb[:40] and abs(len(na) - len(nb)) < 20:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= TITLE_SIMILARITY


def dedupe_stories(stories: list) -> list:
    """Collapse duplicates by normalized URL, then by near-identical titles.

    One entry per story keeps every distinct feed name that carried it,
    so the digest can credit all overlapping sources.
    """
    kept: list = []
    seen_urls: dict = {}
    seen_titles: list = []
    for story in stories:
        key = normalize_url(story.link)
        duplicate = None
        if key and key in seen_urls:
            duplicate = seen_urls[key]
        elif story.title:
            for i, (t_norm, idx) in enumerate(seen_titles):
                if titles_similar(t_norm, story.title):
                    duplicate = kept[idx]
                    break
        if duplicate is not None:
            if story.feed and story.feed not in duplicate.sources:
                duplicate.sources.append(story.feed)
        else:
            story.sources = [story.feed] if story.feed else []
            kept.append(story)
            if key:
                seen_urls[key] = story
            seen_titles.append((normalize_title(story.title), len(kept) - 1))
    return kept


def sort_stories(stories: list) -> list:
    """Newest first; undated stories sink to the end of their group."""
    def key(story: Story):
        if not story.published:
            return (1, 0.0, story.title.lower())
        return (0, -_epoch(story.published), story.title.lower())

    return sorted(stories, key=key)


def _epoch(iso: str) -> float:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def filter_recent(stories: list, max_age_days: float | None) -> list:
    if not max_age_days:
        return stories
    now = datetime.now(timezone.utc)
    keep = [s for s in stories if s.published == "" or s.age_days(now) <= max_age_days]
    return keep
