"""Optional one-paragraph summaries via an OpenAI-compatible endpoint.

Defaults to a local Ollama server (http://localhost:11434/v1). Privacy
first: we only ever send the feed-provided title and the first
`snippet_chars` characters of the feed snippet — we never fetch the
linked article page, so paywalled full text is never collected, cached,
or sent anywhere.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

DEFAULT_ENDPOINT = "http://localhost:11434/v1"
DEFAULT_MODEL = "llama3.2:3b"
DEFAULT_TIMEOUT = 60
DEFAULT_SNIPPET_CHARS = 800  # feed metadata snippet, never full article text

PROMPT_TEMPLATE = """You are a friendly editor writing a calm morning digest.
Summarize the story below in ONE short paragraph of plain English,
2 sentences maximum. Be factual and neutral. If the text is mostly a
title without detail, say briefly what it covers or reply with the
single word UNKNOWN instead of guessing.

Title: {title}
Feed snippet: {snippet}"""


class SummaryError(Exception):
    pass


def snippet_for(story, snippet_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    """Reduced, metadata-only text to send to the model."""
    snippet = (story.summary or "").strip()
    if len(snippet) > snippet_chars:
        snippet = snippet[:snippet_chars].rstrip() + "…"
    return snippet


def summarize_story(story, endpoint: str = DEFAULT_ENDPOINT, model: str = DEFAULT_MODEL,
                    timeout: int = DEFAULT_TIMEOUT, snippet_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    """Return a one-paragraph summary, or raise SummaryError."""
    if not story.title and not story.summary:
        raise SummaryError("story has no title or snippet to summarize")
    content = PROMPT_TEMPLATE.format(title=story.title or "(no title)", snippet=snippet_for(story, snippet_chars))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You write concise, neutral digest summaries."},
            {"role": "user", "content": content},
        ],
        "stream": False,
        "temperature": 0.3,
        "max_tokens": 120,
    }
    return _chat_completions(endpoint, payload, timeout)


def _chat_completions(endpoint: str, payload: dict, timeout: int) -> str:
    try:
        body = json.dumps(payload).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SummaryError(f"bad request payload: {exc}") from exc
    headers = {"Content-Type": "application/json", "User-Agent": "rss-digest-cli/0.1"}
    request = urllib.request.Request(
        f"{endpoint.rstrip('/')}/chat/completions", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise SummaryError(f"endpoint returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise SummaryError(f"cannot reach endpoint: {exc}") from exc
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
        choice = data["choices"][0]
        text = choice["message"]["content"] if "message" in choice else choice["text"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise SummaryError(f"unexpected response shape: {exc}") from exc
    text = _clean_summary(text)
    if not text:
        raise SummaryError("empty summary returned")
    return text


def _clean_summary(text: str) -> str:
    text = " ".join(text.split()).strip(" \"'“”")
    if text.lower().rstrip(".").strip() == "unknown":
        return ""
    if text.lower().startswith("summary:"):
        text = text[len("summary:"):].strip()
    return text


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
