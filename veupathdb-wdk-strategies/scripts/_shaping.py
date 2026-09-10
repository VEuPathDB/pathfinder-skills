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


def score_searches(catalog, query, limit=20):
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 2]
    scored = []
    for rt, searches in catalog["searches"].items():
        for s in searches:
            if _is_boolean(s["name"]):
                continue
            name = s["name"].lower()
            disp = s["displayName"].lower()
            desc = strip_html(s["description"]).lower()
            score = sum(
                (3 if w in name else 0)
                + (2 if w in disp else 0)
                + (1 if w in desc else 0)
                for w in words
            )
            if score:
                scored.append((score, rt, s))
    if not scored:
        return []
    scored.sort(key=lambda t: (-t[0], t[2]["name"]))
    top = scored[0][0]
    return [
        {
            "record_type": rt,
            "name": s["name"],
            "displayName": s["displayName"],
            "relevance": round(score / top, 2),
        }
        for score, rt, s in scored[:limit]
    ]
