"""Load digest sources from an OPML file or a plain URL list.

Accepted inputs:
  * OPML (.opml/.xml): parses <outline xmlUrl="..."> elements, grouped by
    any nesting, preserving the outline text as feed name.
  * Plain text (.txt) or URLs given on the command line: one feed URL per
    line; '#' and blank lines are comments. Optional "| Name" suffix sets
    a display name; optional topic tags like " #tech" are ignored.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class Source:
    url: str
    name: str = ""


def _looks_like_opml(text: str) -> bool:
    lower = text.lstrip()[:512].lower()
    return "<opml" in lower or ("xml" in lower and "outline" in lower)


def _clean_url(url: str) -> str:
    url = url.strip().strip('"').strip("'")
    return url


def parse_opml(data: bytes) -> list:
    root = ET.fromstring(data)
    sources = []

    def walk(node):
        for child in node:
            tag = _tag(child)
            xml_url = (child.get("xmlUrl") or "").strip()
            name = (child.get("title") or child.get("text") or "").strip()
            if tag == "outline" and xml_url:
                sources.append(Source(_clean_url(xml_url), name))
            else:
                walk(child)  # descend into body/head/group outlines

    walk(root)
    if not sources:
        raise ValueError("OPML file contains no <outline xmlUrl=...> feeds")
    return sources


def _tag(node) -> str:
    return node.tag.rsplit("}", 1)[-1].lower()


def parse_url_list(text: str) -> list:
    sources = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # allow "https://... | Friendly Name" and trailing "#tag" tokens
        name = ""
        if "|" in line:
            line, _, name = line.partition("|")
            line, name = line.strip(), name.strip()
        url = _clean_url(line.split()[0]) if line.split() else ""
        if not url:
            continue
        sources.append(Source(url, name))
    return sources


def load_source_file(path: str) -> list:
    with open(path, "rb") as fh:
        data = fh.read()
    text = data.decode("utf-8-sig", errors="replace")
    if _looks_like_opml(text):
        return parse_opml(data)
    return parse_url_list(text)


def validate_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https", "file") and bool(parsed.netloc or parsed.path)
