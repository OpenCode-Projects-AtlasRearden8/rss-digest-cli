"""Render grouped stories as markdown or plain, print-friendly text."""

from __future__ import annotations

import textwrap
import time
from datetime import datetime, timezone

from .stories import normalize_url

WIDTH = 74


def _display_link(story) -> str:
    """Show the link without tracking parameters (utm_*, fbclid, …)."""
    return normalize_url(story.link) or story.link


def _fmt_sources(story) -> str:
    """First source, plus an 'also in' hint for overlapping feeds."""
    sources = list(story.sources or [story.feed])
    primary = sources[0]
    extra = ", ".join(sources[1:])
    if extra:
        primary += f" (also in {extra})"
    return primary


def _fmt_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    dt_local = dt.astimezone()
    if dt_local.date() == datetime.now(dt_local.tzinfo).date():
        return dt_local.strftime("today %I:%M %p")
    return dt_local.strftime("%b %d %Y %H:%M")


def _source_label(story) -> str:
    label = _fmt_sources(story)
    when = _fmt_date(story.published)
    return f"{label} · {when}" if when else label


def render_markdown(sections: dict, title: str = "Morning Digest", notes: list = None) -> str:
    lines = [f"# {title}", ""]
    total = sum(len(stories) for stories in sections.values())
    lines.append(f"{total} stories · {len(sections)} sections · {_weekday()}")
    lines.append("")
    if notes:
        lines.extend(note for note in notes)
        lines.append("")
    for section, stories in sections.items():
        if not stories:
            continue
        lines.append(f"## {section} ({len(stories)})")
        lines.append("")
        for story in stories:
            heading = story.title or story.link or "(untitled)"
            lines.append(f"### [{heading}]({_display_link(story)})" if story.link else f"### {heading}")
            lines.append("")
            meta = _source_label(story)
            if story.summary_text:
                lines.append("_Summary:_")
                lines.append("")
                lines.append(story.summary_text)
                lines.append("")
                lines.append(f"— {meta}")
            else:
                lines.append(f"{meta}")
                lines.append("")
            if story.summary and not story.summary_text:
                wrapped = textwrap.wrap(story.summary, width=WIDTH)
                if wrapped:
                    lines.append(" ".join(wrapped))
                lines.append("")
        lines.append("")
    return _trim_preferred(lines)


def render_plain(sections: dict, title: str = "Morning Digest", notes: list = None) -> str:
    bar = "=" * WIDTH
    out = [bar, title.center(WIDTH), f"{_weekday()}".center(WIDTH).rstrip(), bar, ""]
    if notes:
        for note in notes:
            out.extend(_wrap_plain(note))
        out.append("")
    for section, stories in sections.items():
        if not stories:
            continue
        out.append("")
        out.append(f"{section.upper()}")
        out.append("-" * min(len(section), WIDTH))
        out.append("")
        for i, story in enumerate(stories):
            heading = story.title or story.link or "(untitled)"
            out.extend(_wrap_plain(heading, bullet=f"{i + 1}. "))
            meta = _source_label(story)
            out.extend(_wrap_plain(meta, indent=3, prefix=" "))
            if story.summary_text:
                out.append(f" {' ' * 2}-> summary:")
                out.extend(_wrap_plain(story.summary_text, indent=6, prefix=" "))
            elif story.summary:
                out.extend(_wrap_plain(story.summary, indent=6, prefix=" "))
            if story.link:
                out.append(f"   {_display_link(story)}")
            out.append("")
    return "\n".join(out).rstrip() + "\n"


def _wrap_plain(text: str, width: int = WIDTH, indent: int = 0, bullet: str = "", prefix: str = "") -> list:
    spaces = " " * indent
    initial = spaces + prefix + bullet
    wrap_width = max(20, width - indent - len(prefix) - len(bullet))
    lines = textwrap.wrap(text, width=wrap_width) or [""]
    return [initial + lines[0]] + [spaces + " " * (len(prefix) + len(bullet)) + line for line in lines[1:]]


def _trim_preferred(lines: list) -> str:
    text = "\n".join(lines)
    return re_strip_blank_runs(text)


def re_strip_blank_runs(text: str) -> str:
    import re

    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip() + "\n"


def _weekday() -> str:
    today = datetime.now(timezone.utc).astimezone()
    return today.strftime("%A, %B %d %Y")


def _epoch(iso: str):
    try:
        return time.mktime(datetime.fromisoformat(iso).timetuple())
    except (ValueError, TypeError):
        return 0.0
