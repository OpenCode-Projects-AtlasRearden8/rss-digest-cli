"""Command line entry point for rss-digest-cli."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

from . import __version__
from .feedparse import FeedParseError, parse_feed
from .fetcher import Cache, FetchError, fetch, is_cache_old
from .output import render_markdown, render_plain
from .sources import load_source_file, parse_url_list, validate_url
from .stories import Story, dedupe_stories, filter_recent, sort_stories
from .summarize import (
    DEFAULT_ENDPOINT,
    DEFAULT_MODEL,
    DEFAULT_SNIPPET_CHARS,
    SummaryError,
    summarize_story,
)
from .topics import group_stories

EXIT_OK = 0
EXIT_PARTIAL = 1
EXIT_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digest",
        description="Turn an OPML/URL list into a calm morning digest (markdown or plain text).",
        epilog="Examples:\n"
               "  digest --sources feeds.opml --format markdown --out digest.md\n"
               "  digest --sources feeds.txt --limit 15\n"
               "  digest --sources feeds.txt --summarize           # uses local Ollama\n"
               "  echo \"https://example.org/feed.xml\" | python -m digest",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sources", "-s", help="OPML or plain-text URL list file")
    parser.add_argument("urls", nargs="*", metavar="url", help="feed URLs (optional, repeatable)")
    parser.add_argument("--format", "-f", choices=("markdown", "plain"), default="markdown")
    parser.add_argument("--out", "-o", help="write digest to file (default: stdout)")
    parser.add_argument("--limit", type=int, default=0, help="max stories per section (0 = no limit)")
    parser.add_argument("--total-limit", type=int, default=0, help="max stories overall (0 = no limit)")
    parser.add_argument("--max-age-days", type=float, default=3.0, help="skip older stories (default 3, 0 = keep all)")
    parser.add_argument("--summarize", action="store_true", help="add one-paragraph AI summaries")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help=f"OpenAI-compatible API (default {DEFAULT_ENDPOINT})")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"model name (default {DEFAULT_MODEL})")
    parser.add_argument("--snippet-chars", type=int, default=DEFAULT_SNIPPET_CHARS,
                        help=f"max feed snippet characters sent to the model (default {DEFAULT_SNIPPET_CHARS})")
    parser.add_argument("--offline", action="store_true", help="serve only from cache; never touch the network")
    parser.add_argument("--cache-dir", default=os.environ.get("RSS_DIGEST_CACHE", default_cache_dir()),
                        help="cache directory (default: ~/.cache/rss-digest)")
    parser.add_argument("--no-cache", action="store_true", help="skip reading/writing the cache")
    parser.add_argument("--title", default="Morning Digest", help="digest title")
    parser.add_argument("--verbose", "-v", action="store_true", help="log fetch notes to stderr")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def default_cache_dir() -> str:
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = xdg or os.path.expanduser("~/.cache")
    return os.path.join(base, "rss-digest")


def collect_urls(args) -> list:
    urls = []
    if args.sources:
        urls.extend(load_source_file(args.sources))
    if args.urls:
        from .sources import Source

        urls.extend(Source(u) for u in args.urls)
    if not urls and not sys.stdin.isatty():
        urls.extend(parse_url_list(sys.stdin.read()))
    if not urls:
        return urls
    cleaned = []
    for source in urls:
        if validate_url(source.url):
            cleaned.append(source)
        else:
            warn(f"skipping invalid URL: {source.url!r}")
    return cleaned


def warn(message: str):
    print(f"note: {message}", file=sys.stderr)


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    sources = collect_urls(args)
    if not sources:
        parser.print_usage(sys.stderr)
        warn("no feed URLs given (use --sources FILE, a URL argument, or pipe URLs on stdin)")
        return EXIT_ERROR

    cache = Cache("" if args.no_cache else args.cache_dir)
    stories = []
    feed_notes = []
    failures = 0
    for source in sources:
        try:
            body = fetch(source.url, cache, offline=args.offline)
        except FetchError as exc:
            failures += 1
            feed_notes.append(f"- feed unreachable, no cache: {source.name or source.url}")
            feed_notes.append(f"  ({exc})")
            if args.verbose:
                warn(f"{source.url}: {exc}")
            continue
        if body.stale and args.verbose:
            warn(f"{source.url}: using stale cache ({body.status_note})")
        try:
            feed = parse_feed(body.body)
        except FeedParseError as exc:
            failures += 1
            feed_notes.append(f"- feed could not be parsed: {source.name or source.url}")
            feed_notes.append(f"  ({exc})")
            if args.verbose:
                warn(f"{source.url}: parse error: {exc}")
            continue
        feed_name = source.name or feed.title or source.url
        if body.stale:
            note = _stale_note(source, feed, body)
            if note:
                feed_notes.append(note)
        for entry in feed.entries:
            if not entry.title and not entry.link:
                continue
            stories.append(
                Story(
                    title=entry.title or entry.link,
                    link=entry.link,
                    feed=feed_name,
                    summary=entry.summary,
                    published=entry.published,
                )
            )
        if args.verbose:
            warn(f"{source.url}: {len(feed.entries)} entries")

    stories = dedupe_stories(stories)
    max_age = args.max_age_days if args.max_age_days and args.max_age_days > 0 else None
    stories = filter_recent(stories, max_age)
    stories = sort_stories(stories)
    if args.total_limit and args.total_limit > 0:
        stories = stories[: args.total_limit]

    if args.summarize:
        _apply_summaries(stories, args)

    sections = group_stories(stories)
    if args.limit and args.limit > 0:
        sections = {k: v[: args.limit] for k, v in sections.items()}

    all_notes = list(feed_notes)
    total = sum(len(v) for v in sections.values())
    if not stories:
        all_notes.insert(0, "No stories this morning — the world can wait for one more day.")
    else:
        all_notes.insert(0, f"{total} stories from {len({s.feed for s in stories})} feeds · "
                             f"{datetime.now(timezone.utc).astimezone().strftime('%H:%M %Z')}")
        if args.summarize:
            summarized = sum(1 for s in stories if s.summary_text)
            all_notes.insert(1, f"{summarized} AI summaries (from feed snippets only; full article text is never fetched or sent)")

    render = render_plain if args.format == "plain" else render_markdown
    text = render(sections, title=args.title, notes=all_notes)

    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        except OSError as exc:
            warn(f"cannot write {args.out}: {exc}")
            return EXIT_ERROR
    else:
        print(text)

    return EXIT_PARTIAL if failures else EXIT_OK


def _stale_note(source, feed, body) -> str:
    when = ""
    if body.fetched_at:
        try:
            dt = datetime.fromisoformat(body.fetched_at)
            when = f" (cached {dt.astimezone().strftime('%b %d %H:%M')})"
        except ValueError:
            pass
    reason = body.status_note or "unreachable"
    return f"- feed was {reason}; showing stale copy: {feed.title or source.name or source.url}{when}"


def _apply_summaries(stories, args):
    try:
        probe = _probe_endpoint(args.endpoint)
        if probe:
            warn(f"summary endpoint ready: {args.endpoint} (model {args.model})")
        else:
            warn(f"summary endpoint not reachable ({args.endpoint}); summaries will be skipped if it stays down")
    except Exception:
        probe = False
    done = 0
    for story in stories:
        try:
            text = summarize_story(
                story,
                endpoint=args.endpoint,
                model=args.model,
                snippet_chars=args.snippet_chars,
            )
        except SummaryError as exc:
            warn(f"summary skipped: {exc}")
            if probe is False:
                break
            continue
        story.summary_text = text
        done += 1
    if done:
        warn(f"{done}/{len(stories)} summaries generated")


def _probe_endpoint(endpoint: str, timeout: float = 2.0) -> object:
    try:
        request = urllib.request.Request(f"{endpoint.rstrip('/')}/models")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _probe_up(probe) -> bool:
    return probe is True
