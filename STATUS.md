# STATUS.md — rss-digest-cli

Last verified: 2026-11-03

## What was built

A zero-dependency (stdlib-only) Python CLI that turns an OPML file or a plain
URL list into a **calm morning digest**: fetch feeds, dedupe stories, group by
topic, and render a print-friendly markdown or plain-text digest. Optional
one-paragraph AI summaries via any OpenAI-compatible endpoint, defaulting to a
local Ollama server.

Feature summary:

* **Sources**: OPML (any nesting, folders preserved as feed labels) or plain
  text lists (`#` comments, `| Friendly Name` suffixes, stdin piping, and
  repeatable URL arguments).
* **Fetching**: HTTP(S) and `file://`; conditional GET (ETag / Last-Modified);
  gzip/deflate; disk cache in `~/.cache/rss-digest` (override with
  `--cache-dir` or `$RSS_DIGEST_CACHE`); `--offline` mode; graceful stale-feed
  fallback with a visible note ("feed was unreachable; showing stale copy").
* **Parsing**: stdlib XML parser handles RSS 2.0, Atom (namespaced), and RDF/
  RSS 1.0; HTML snippets are reduced to text; RFC-822 and ISO dates both
  supported.
* **Dedupe**: tracking-parameter stripping (`utm_*`, `fbclid`, …) for both
  duplicate detection *and* displayed links; near-identical title detection;
  overlapping feeds credited together ("also in Harbor Notes Journal").
* **Topics**: fully offline keyword profiles (AI, local AI, tech, business,
  books/publishing, reselling, money/budgets, health/nursing, gaming, chess,
  science, world, life/productivity) plus word-overlap clustering for
  unmatched stories (`Related: …` sections) and a `General` bucket for
  stragglers.
* **Summaries (optional, privacy-first)**: only the title plus a capped
  feed-provided snippet (default 800 chars, `--snippet-chars`) is ever sent to
  the model; the linked article page is never fetched, so paywalled full text
  is never collected, cached, or transmitted. Endpoint failure degrades to a
  normal digest with a note.
* **Output**: markdown (headings + links) and plain text (74-column wrapped,
  numbered, print-friendly). Exit code 0 = all feeds served, 1 = some failed,
  2 = usage error.

## How to run it

```bash
# from this folder (no install needed)
python3 -m digest --sources examples/feeds.opml --format markdown --out digest.md
python3 -m digest "https://hnrss.org/frontpage" --limit 5

# AI summaries need local Ollama
ollama serve
digest --sources examples/feeds.opml --summarize

# or install (creates `digest` and `morning-digest` commands)
python3 -m pip install .
```

Useful files: `examples/sources.txt`, `examples/feeds.opml`, `README.md`.

## Verification results

Environment: Python 3.13.5, Linux.

1. **Unit/integration tests**: `python3 -m unittest discover -s tests` →
   *`Ran 58 tests … OK`* — 58/58 pass, all on local fixture feeds
   (`tests/fixtures/`): RSS 2.0, Atom, RDF, OPML, plain list, plus an
   in-process fake OpenAI-compatible HTTP server for the summarizer.
   Covered: parsing, date handling, HTML reduction, OPML/list loading,
   URL/title dedupe, date filtering & sorting, topic matching (including
   word-boundary false-positive checks), leftover clustering, markdown and
   plain rendering, file/offline/stale cache fallbacks, HTTP failure
   fallback, snippet privacy caps (no title/link leakage; snippet truncation),
   fake-endpoint success/500/UNKNOWN/unreachable paths, and end-to-end CLI
   runs (markdown file output, plain stdout, seeded-cache offline run,
   multi-feed exit codes, missing-sources usage error, graceful summary
   skipping).
2. **Compile check**: `python3 -m compileall digest tests` → clean.
3. **Package check**: `python3 -m pip install . --target …` builds cleanly;
   `digest` and `morning-digest` console scripts and example data files are
   installed; `digest --version` → `digest 0.1.0`.
4. **Live CLI demo**: two fixture feeds combined → markdown and plain digests
   show correct dedupe (cross-feed duplicate story merges into one entry with
   "also in …" credit), clean topic grouping, tracking parameters stripped
   from displayed links, and date-aware ordering.

## Known gaps / next steps

* **Summary quality** depends entirely on the local model; no automatic model
  recommendations or benchmarking.
* **Per-topic opt-in filters** (e.g. digest only "AI" and "Health") aren't a
  CLI flag yet — easy follow-up using `digest/topics.py` profiles.
* **OPML export** — sources are read, not yet written back (e.g. after editing
  feeds in a reader app).
* **Feed auto-discovery** (given a site URL, find `<link rel=alternate>`) is
  not implemented; you must paste exact feed URLs.
* **Politeness scheduling**: concurrent fetches are serial (good), but there's
  no rate-limit knob for very large lists; ETags cover most re-load costs.
* **Titles with only HTML entities** are unwrapped once; exotic double-encoded
  entities can rarely survive (cosmetic).
* **Parallelization / speed** for hundreds of feeds not tuned; still single
  fetch at a time with a 20 s timeout.
* No Windows-specific testing done (pure Python, but untested on Windows).

## Privacy recap

No secrets, no API keys, no telemetry, no accounts. The only network host
touched by default is the configured feed list; summaries reach out only to
your own Ollama/endpoint with capped feed snippets. Cache is local and
deletable.
