"""Response shaping: compact, context-friendly views of WDK payloads."""
import html
import json
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def strip_html(text):
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def _is_boolean(name):
    return name.startswith("boolean_question_")


def catalog_lines(catalog, record_type=None):
    lines = []
    for rt, searches in catalog["searches"].items():
        if record_type and rt != record_type:
            continue
        for s in searches:
            if _is_boolean(s["name"]):
                continue
            desc = strip_html(s["description"])[:250]
            lines.append(f"{rt}\t{s['name']}\t{s['displayName']}\t{desc}")
    return lines


def all_search_names(catalog):
    """Map search name -> record type. Prefer non-'gene' rt for duplicates
    (gene searches live under 'transcript' in WDK)."""
    names = {}
    for rt, searches in catalog["searches"].items():
        for s in searches:
            if s["name"] not in names or names[s["name"]] == "gene":
                names[s["name"]] = rt
    return names
