"""Feed fetching with a local file cache and graceful stale-feed fallback.

Design goals (local-first, calm mornings):
  * Conditional GET via ETag / Last-Modified keeps re-runs cheap and polite.
  * Every successful fetch is cached to disk (JSON per feed).
  * If a feed is unreachable or expires, we fall back to the cached copy and
    label it as stale instead of dropping it silently.
  * `file://` URLs are supported so offline fixtures and testing work.
"""

from __future__ import annotations

import hashlib
import json
import ssl
import time
import urllib.error
import urllib.request
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlparse

USER_AGENT = "rss-digest-cli/0.1 (+https://github.com/dylanasdale) calm-morning-digest"
DEFAULT_TIMEOUT = 20
STALE_AGE_SECONDS = 60 * 60 * 6  # cached copy older than this is "stale"


class FetchError(Exception):
    pass


@dataclass
class FetchedBody:
    body: bytes = b""
    fresh: bool = False       # True if obtained during this run
    stale: bool = False       # True if served from an old cache
    fetched_at: str = ""      # ISO timestamp of the underlying content
    status_note: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.body)


@dataclass
class Cache:
    directory: str
    entries: dict = field(default_factory=dict)
    _loaded: bool = False

    def _path_for(self, url: str) -> str:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
        return f"{self.directory.rstrip('/')}/{key}.json"

    def load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            import os

            with os.scandir(self.directory) as scan:
                for entry in scan:
                    if entry.is_file() and entry.name.endswith(".json"):
                        try:
                            with open(entry.path, encoding="utf-8") as fh:
                                record = json.load(fh)
                            if record.get("url"):
                                self.entries[record["url"]] = record
                        except (OSError, ValueError):
                            continue
        except OSError:
            pass

    def get(self, url: str) -> dict:
        self.load()
        return self.entries.get(url, {})

    def put(self, url: str, body: bytes, etag: str = "", last_modified: str = "", content_type: str = ""):
        record = {
            "url": url,
            "etag": etag,
            "last_modified": last_modified,
            "content_type": content_type,
            "fetched_at": _now_iso(),
            "body_b64": _b64_encode(body),
        }
        import os

        os.makedirs(self.directory, exist_ok=True)
        path = self._path_for(url)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh)
        os.replace(tmp, path)
        self.load()
        self.entries[url] = record


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_age_seconds(iso: str) -> float:
    try:
        then = datetime.fromisoformat(iso)
    except ValueError:
        return float("inf")
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds()


def _b64_encode(body: bytes) -> str:
    import base64

    return base64.b64encode(body).decode("ascii")


def _b64_decode(text: str) -> bytes:
    import base64

    return base64.b64decode(text.encode("ascii"))


def _decompress(body: bytes, encoding: str) -> bytes:
    if encoding == "gzip":
        try:
            import gzip

            return gzip.decompress(body)
        except OSError:
            return body
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def fetch(url: str, cache: Cache, timeout: int = DEFAULT_TIMEOUT, offline: bool = False) -> FetchedBody:
    """Fetch a feed URL; on any failure fall back to (possibly stale) cache."""
    try:
        if not offline and url.startswith("file://"):
            return _fetch_file(url, cache)
        if not offline and url.startswith("http"):
            return _fetch_http(url, cache, timeout)
    except FetchError:
        if not offline:
            return _from_cache(url, cache, reason="fetch failed")
        raise
    return _from_cache(url, cache, reason="offline mode" if offline else "unsupported scheme")


def _fetch_file(url: str, cache: Cache) -> FetchedBody:
    path = urlparse(url).path or ()
    try:
        with open(urlparse(url).path, "rb") as fh:
            body = fh.read()
    except OSError as exc:
        raise FetchError(f"file unreadable: {exc}") from exc
    if not body:
        raise FetchError("file is empty")
    etag = f'"{hashlib.sha256(body).hexdigest()[:16]}"'
    previous = cache.get(url)
    if not previous or previous.get("etag") != etag:
        cache.put(url, body, etag=etag, content_type="application/xml")
    return FetchedBody(body=body, fresh=True, fetched_at=cache.get(url).get("fetched_at", _now_iso()))


def _fetch_http(url: str, cache: Cache, timeout: int) -> FetchedBody:
    previous = cache.get(url)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/xml, text/xml, application/atom+xml, */*"}
    if previous.get("etag"):
        headers["If-None-Match"] = previous["etag"]
    if previous.get("last_modified"):
        headers["If-Modified-Since"] = previous["last_modified"]
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
            encoding = (response.headers.get("Content-Encoding") or "").strip().lower()
            body = _decompress(raw, encoding)
            if status == 304 or not body:
                return _from_cache(url, cache, reason="server says not modified")
            etag = response.headers.get("ETag", "")
            last_modified = response.headers.get("Last-Modified", "")
            content_type = response.headers.get("Content-Type", "")
            if previous and previous.get("etag") == etag and previous.get("body_b64"):
                body = _b64_decode(previous["body_b64"])
            else:
                cache.put(url, body, etag, last_modified, content_type)
            return FetchedBody(body=body, fresh=True, fetched_at=previous.get("fetched_at") or _now_iso())
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return _from_cache(url, cache, reason="not modified")
        return _from_cache(url, cache, reason=f"HTTP {exc.code} {exc.reason}")
    except (urllib.error.URLError, TimeoutError, ssl.SSLError, ConnectionError, OSError) as exc:
        return _from_cache(url, cache, reason=str(exc))


def _from_cache(url: str, cache: Cache, reason: str) -> FetchedBody:
    record = cache.get(url)
    if not record or not record.get("body_b64"):
        raise FetchError(f"no cached copy ({reason})")
    age = _iso_age_seconds(record.get("fetched_at", ""))
    return FetchedBody(
        body=_b64_decode(record["body_b64"]),
        fresh=False,
        stale=True,
        fetched_at=record.get("fetched_at", ""),
        status_note=reason,
    )


def is_cache_old(url: str, cache: Cache) -> bool:
    record = cache.get(url)
    return _iso_age_seconds(record.get("fetched_at", "")) > STALE_AGE_SECONDS if record else True


def wait(seconds: float):
    time.sleep(seconds)
