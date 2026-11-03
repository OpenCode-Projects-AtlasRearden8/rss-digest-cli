# rss-digest-cli

Turn an OPML or URL list into a **calm morning digest** — a small, print-friendly
roundup of your RSS/Atom feeds with stories deduped and grouped by topic.
Written in plain Python with zero third-party dependencies in the core.

Made by [Asdale Dynamics, LLC](https://dylanasdale.github.io) as part of a
beginner-first, local-first toolkit: you keep your reading list, your cache,
and your paragraphs — no accounts, no tracking, no cloud required.

## How it works

```
sources (OPML or .txt, one feed URL per line)
        │
        ▼
fetch feeds (HTTP or file://) ── cache to ~/.cache/rss-digest/
        │                            └─ stale? reuse cached copy + a note
        ▼
parse RSS 2.0 / Atom / RDF  (stdlib XML parser)
        │
        ▼
dedupe (strip utm_* links, merge near-identical titles, credit all feeds)
        │
        ▼
group by topic (offline keyword matching + word-overlap leftovers)
        │
        ▼
render markdown or plain text ── optional AI one-liners (Ollama or any
                                 OpenAI-compatible endpoint)
```

## Requirements

* Python 3.10+ (standard library only)
* Optional: [Ollama](https://ollama.com) for AI summaries — nothing else

## Install

```bash
cd rss-digest-cli
python3 -m pip install .
```

Or just run it from the folder:

```bash
python3 -m digest --sources feeds.opml
```

Both a `digest` and a `morning-digest` command are installed when pip-installed.

## Usage

```bash
# OPML file → markdown digest on stdout
digest --sources feeds.opml

# plain URL list → write digest.md
digest --sources sources.txt --format markdown --out digest.md

# limit each section to 3 stories, keep nothing older than 2 days
digest --sources feeds.opml --limit 3 --max-age-days 2

# add one-paragraph AI summaries (uses local Ollama at localhost:11434)
digest --sources feeds.opml --summarize

# never touch the network; serve from yesterday's cache
digest --sources feeds.opml --offline

# single feed (repeatable) or pipe a list in
digest https://hnrss.org/frontpage https://simonwillison.net/atom/everything/
echo "https://hnrss.org/frontpage" | python3 -m digest
```

### Handy flags

| Flag | What it does |
| --- | --- |
| `--format markdown\|plain` | Output style (markdown default, plain is print-friendly) |
| `--out FILE` | Write to a file instead of stdout |
| `--limit N` / `--total-limit N` | Cap per section / overall story count |
| `--max-age-days F` | Skip stories older than this (default 3, `0` keeps all) |
| `--summarize` | Add one-paragraph AI summaries |
| `--endpoint URL` / `--model NAME` | OpenAI-compatible API (default Ollama `http://localhost:11434/v1`, model `llama3.2:3b`) |
| `--offline` | Use only the cache — no network calls at all |
| `--cache-dir DIR` / `--no-cache` | Where cached feeds live / disable caching |
| `--title` | Digest heading (default "Morning Digest") |
| `--verbose` | Log per-feed fetch notes to stderr |

### Source files

* **OPML** (`.opml`/`.xml`) — nothing to configure, folders become labels:
  see `examples/feeds.opml`.
* **Plain text** (`.txt`) — one feed URL per line; `#` starts a comment and a
  `| Name` suffix gives the feed a friendly name: see `examples/sources.txt`.

Missing feeds, dead URLs, and unparsable XML never abort the run: the digest
still comes out, with a short note about what couldn't be fetched. Cached
copies are reused for stale feeds.

## Privacy (the short version)

* **No accounts. No telemetry. No cloud** unless you point it at one yourself.
* Summaries only ever send the story **title** plus a short feed-provided
  snippet (first 800 characters by default, tunable with `--snippet-chars`).
  The tool **never opens the linked article page**, so paywalled full text is
  never collected, cached, or sent anywhere — there is nothing paywalled to
  leak.
* The cache lives on your disk (`~/.cache/rss-digest` by default). Delete the
  folder and everything is forgotten.

## Where topics come from

Grouping is fully offline: goal-specific keyword lists (AI, local AI, tech,
business, books, side hustles, money, health, gaming, chess, and friends)
score each story; unmatched stories are clustered by word overlap into small
`Related: …` sections; singletons land in `General`. The word lists are plain
Python dictionaries in `digest/topics.py` — easy to edit for your own feeds.

## AI summaries (optional)

Nothing happens unless you pass `--summarize`. The default endpoint is a local
Ollama server:

```bash
ollama serve          # usually already running
ollama pull llama3.2:3b
digest --sources feeds.opml --summarize
```

Any OpenAI-compatible endpoint works, including Ollama, LM Studio, llama.cpp
server, LM Studio llamafile and friends:

```bash
digest --summarize --endpoint http://localhost:1234/v1 --model qwen2.5:7b
```

If the endpoint is down the digest still renders — summaries are skipped with
a note. If your feeds include ads or worse, keep `--snippet-chars` small; the
tool never sends your list of feeds, your OPML, feed URLs, or story links.

## For people reading the code

```
digest/
  cli.py        command line, fetch loop, digest assembly
  sources.py    OPML + plain-text source lists
  fetcher.py    HTTP/file fetch, conditional GET, disk cache, stale fallback
  feedparse.py  stdlib RSS 2.0 / Atom / RDF parser
  stories.py    dedupe (URL normalize, title similarity), date filtering
  topics.py     offline topic matching and leftover clustering
  output.py     markdown + print-friendly plain-text renderers
  summarize.py  OpenAI-compatible chat client (snippet-only, capped)
tests/          58 automated tests with local fixture feeds (no network)
```

Run the test suite:

```bash
python3 -m unittest discover -s tests
```

## Roadmap / known gaps

See `STATUS.md` for the honest list: encoding edge cases on odd servers,
no per-topic filtering yet, and a fetch politeness scheduler that hasn't
met a rolling 1 000-feed list yet.

## License

MIT — Copyright (c) 2026 Asdale Dynamics, LLC. See `LICENSE`.
Education and tools only; never medical advice.
