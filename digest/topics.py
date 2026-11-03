"""Group stories into calm, readable topic sections.

Offline keyword matching against broad topic profiles; leftovers are
clustered by shared word overlap so unusual feeds still land somewhere
sensible. No network calls, no external APIs.
"""

from __future__ import annotations

import re

ISSUE = re.compile(r"[^a-z0-9']+")
STOPWORDS = frozenset(
    """the a an and or but for nor on in at to from by of with about into
    over after is are was were be been being it its this that these those
    as new how why what when who your you our we us they their will can
    could would should just get got more most than then now not no yes up
    down out off all any each few other some such only own same so too
    very s t don also first two may might said says one still vs its.
    company inc""".split()
)

TOPIC_PROFILES = {
    "AI & Machine Learning": [
        "ai", "artificial intelligence", "machine learning", "llm", "llms",
        "chatgpt", "openai", "claude", "anthropic", "gemini", "copilot",
        "gpt", "generative", "prompt", "prompts", "transformer", "agent",
        "agents", "rag", "deep learning", "neural", "foundation model",
        "mcp", "model context protocol",
    ],
    "Local AI & Self-Hosting": [
        "ollama", "llama.cpp", "local llm", "self-host", "selfhost",
        "self-hosted", "home server", "homelab", "raspberry pi", "npu",
        "open weights", "quantized", "gguf", "offline",
    ],
    "Tech & Software": [
        "software", "app", "apps", "linux", "windows", "apple", "android",
        "iphone", "browser", "open source", "github", "git", "code",
        "coding", "programming", "developer", "python", "javascript",
        "rust", "terminal", "cli", "api", "security", "privacy", "data",
        "cloud", "tech", "chip", "semiconductor", "cyber", "bluetooth",
    ],
    "Business & Work": [
        "business", "small business", "llc", "entrepreneur", "marketing",
        "entrepreneurship", "side hustle", "freelance", "bookkeeping",
        "tax", "taxes", "accounting", "hiring", "career", "salary",
        "workplace", "boss", "employed",
    ],
    "Books & Publishing": [
        "book", "books", "kdp", "kindle", "self-publishing", "author",
        "ebook", "audiobook", "publishing", "manuscript", "writing",
        "writer", "editor", "isbn", "draft",
    ],
    "Selling & Marketplaces": [
        "ebay", "reselling", "flipping", "thrift", "consignment",
        "marketplace", "etsy", "craigslist", "inventory", "sold",
        "listing", "seller", "shipping",
    ],
    "Money & Budgets": [
        "budget", "budgeting", "personal finance", "investing", "savings",
        "debt", "frugal", "mortgage", "retirement", "insurance", "money",
        "spending", "income", "emergency fund",
    ],
    "Health & Nursing": [
        "health", "nurse", "nursing", "hospital", "clinic", "patient",
        "medical", "wellness", "sleep", "burnout", "mindfulness",
        "mental health", "care",
    ],
    "Gaming": [
        "game", "games", "gaming", "ffxiv", "final fantasy", "xiv",
        "steam", "nintendo", "playstation", "xbox", "expansion", "raid",
        "mmo", "esports", "indie game", "patch", "dungeon",
    ],
    "Chess": [
        "chess", "gambit", "endgame", "blitz", "fide", "checkmate",
        "lichess", "evaluated", "tournament",
    ],
    "Science & Space": [
        "science", "research", "study", "space", "nasa", "physics",
        "biology", "climate", "astronomy", "rocket", "mars", "moon",
        "telescope",
    ],
    "World & Society": [
        "election", "government", "policy", "senate", "congress",
        "president", "world", "war", "court", "law", "regulation",
        "city", "state", "weather",
    ],
    "Life & Productivity": [
        "productivity", "adhd", "habits", "routine", "focus", "todo",
        "paperwork", "organize", "declutter", "minimal", "note",
        "journal", "calm", "checklist", "plan", "goals",
    ],
}

PLURAL_HINTS = {
    "book": "books",
    "game": "games",
    "author": "authors",
}

_MIN_WORD_LENGTH = 4


_KEYWORD_CACHE = {}


def _keyword_regex(keyword: str):
    pattern = _KEYWORD_CACHE.get(keyword)
    if pattern is None:
        escaped = re.escape(keyword)
        pattern = re.compile(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])")
        _KEYWORD_CACHE[keyword] = pattern
    return pattern


def match_topic(story) -> object:
    """Primary topic name, or ('@leftover', signature) when unmatched."""
    text = _bag(f"{story.title} {story.summary}")
    best_topic, best_hits = "", 0
    for topic, keywords in TOPIC_PROFILES.items():
        hits = 0
        for keyword in keywords:
            hits += len(_keyword_regex(keyword).findall(text))
        if hits > best_hits:
            best_topic, best_hits = topic, hits
    if best_topic:
        return best_topic
    words = _words(f"{story.title} {story.summary}")
    if not words:
        return "General"
    return ("@leftover", frozenset(words[:8]))


def group_stories(stories) -> dict:
    """Ordered dict: topic -> stories (newest first). Unmatched stories
    are clustered by word overlap; lone stragglers fold into General."""
    named: dict = {}
    leftovers: list = []
    for index, story in enumerate(stories):
        matched = match_topic(story)
        if isinstance(matched, tuple):
            leftovers.append((index, story, set(matched[1])))
        else:
            named.setdefault(matched, []).append((index, story))

    sections: list = []
    for topic, members in named.items():
        sections.append((topic, members))

    # Greedy keyword-overlap clustering for leftovers (2+ shared words).
    clusters: list = []
    for index, story, signature in leftovers:
        home = None
        for cluster in clusters:
            if len(signature & cluster["sig"]) >= 2:
                home = cluster
                break
        if home is None:
            home = {"sig": set(signature), "members": []}
            clusters.append(home)
        else:
            home["sig"] |= signature
        home["members"].append((index, story))

    singles: list = []
    for cluster in clusters:
        if len(cluster["members"]) == 1:
            singles.append(cluster["members"][0])
            continue
        label = "General"
        top = sorted(
            cluster["sig"],
            key=lambda word: (-sum(1 for c in clusters if word in c["sig"]), word),
        )[:2] or ["General"]
        if top and top[0]:
            label = "/".join(word.capitalize() for word in top[:2])
        sections.append((f"Related: {label}", cluster["members"]))

    # deterministic section order: biggest first, then name, then earliest story
    ordered: dict = {}
    for topic, members in sorted(
        sections,
        key=lambda pair: (-len(pair[1]), min(i for i, _ in pair[1]), pair[0].lower()),
    ):
        ordered[topic] = _sorted_members(members)
    if singles:
        ordered.setdefault("General", []).extend(_sorted_members(singles))
        ordered = dict(sorted(ordered.items(), key=lambda kv: kv[0] == "General"))
    if not ordered:
        ordered["General"] = []
    return ordered


def _sorted_members(members):
    from .stories import sort_stories

    return sort_stories([story for _, story in members])


def _bag(text: str) -> str:
    """Lowercased, padded text so short keywords match on word edges."""
    padded = f" {text.lower()} "
    return padded


def _words(text: str) -> list:
    tokens = ISSUE.sub(" ", text.lower()).split()
    return [w for w in tokens if len(w) >= _MIN_WORD_LENGTH and w not in STOPWORDS]
