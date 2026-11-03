import gzip
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timezone

from digest.feedparse import parse_feed
from digest.fetcher import Cache, FetchedBody, FetchError, fetch, is_cache_old

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def rss_bytes():
    with open(os.path.join(FIXTURES, "rss_basic.xml"), "rb") as fh:
        return fh.read()


def make_cache():
    directory = tempfile.mkdtemp(prefix="digest-cache-")
    cache = Cache(directory)
    return cache, directory


def seed(cache: Cache, url: str, body: bytes, age_hours: float = 40.0):
    record = {
        "url": url,
        "etag": '"v1"',
        "last_modified": "Fri, 30 Oct 2026 10:00:00 GMT",
        "fetched_at": iso_when(age_hours),
        "body_b64": _b64(body),
    }
    cache.entries[url] = record
    # write through so a fresh Cache instance in the same dir still sees it
    path = cache._path_for(url)
    os.makedirs(cache.directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh)
    return record


def _b64(body: bytes) -> str:
    import base64

    return base64.b64encode(body).decode("ascii")


def iso_when(hours_ago: float):
    from datetime import timedelta

    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


class TestFileFetch(unittest.TestCase):
    def setUp(self):
        self.cache, self.dir = make_cache()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def file_url(self):
        return "file://" + os.path.join(FIXTURES, "rss_basic.xml")

    def test_file_fetch(self):
        body = fetch(self.file_url(), self.cache)
        self.assertTrue(body.fresh)
        feed = parse_feed(body.body)
        self.assertEqual(feed.title, "Arcadia Tech Stream")

    def test_file_fallback_to_cache(self):
        url = self.file_url()
        seed(self.cache, url, rss_bytes())
        body = fetch(url, self.cache, offline=True)
        self.assertTrue(body.stale)
        self.assertEqual(parse_feed(body.body).title, "Arcadia Tech Stream")


class TestOfflineAndStale(unittest.TestCase):
    def setUp(self):
        self.cache, self.dir = make_cache()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_offline_uses_cache(self):
        url = "https://example.com/feed.xml"
        seed(self.cache, url, rss_bytes())
        body = fetch(url, self.cache, offline=True)
        self.assertTrue(body.stale)
        self.assertFalse(body.fresh)
        parse_feed(body.body)

    def test_offline_without_cache_raises(self):
        with self.assertRaises(FetchError):
            fetch("https://example.com/feed.xml", self.cache, offline=True)

    def test_failed_http_falls_back_to_stale(self):
        url = "https://127.0.0.1:9/feed.xml"  # nothing listens on port 9
        seed(self.cache, url, rss_bytes())
        body = fetch(url, self.cache)
        self.assertTrue(body.stale)
        self.assertTrue(parse_feed(body.body).title == "Arcadia Tech Stream")

    def test_failed_http_without_cache_raises(self):
        with self.assertRaises(FetchError):
            fetch("https://127.0.0.1:9/feed.xml", self.cache)

    def test_cache_old_check(self):
        url = "https://example.com/feed.xml"
        seed(self.cache, url, rss_bytes(), age_hours=0.1)
        self.assertFalse(is_cache_old(url, self.cache))
        seed(self.cache, url, rss_bytes(), age_hours=40)
        self.assertTrue(is_cache_old(url, self.cache))


if __name__ == "__main__":
    unittest.main()
