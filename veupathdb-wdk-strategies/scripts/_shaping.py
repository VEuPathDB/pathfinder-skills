"""Response shaping: compact, context-friendly views of WDK payloads."""
import difflib
import html
import json
import re

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

FAKE = "@@fake@@"
DIRECT_MAX = 200
TREE_MAX_LINES = 80


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


def is_tree(vocab):
    return isinstance(vocab, dict)


def tree_entries(node, parent=None, out=None):
    out = [] if out is None else out
    term = node["data"]["term"]
    kids = node.get("children", [])
    if term != FAKE:
        out.append(
            {
                "term": term,
                "display": node["data"].get("display", term),
                "parent": parent,
                "leaf": not kids,
            }
        )
    for c in kids:
        tree_entries(c, None if term == FAKE else term, out)
    return out


def expand_to_leaves(tree, selected):
    """Selected node terms (parents or leaves) -> the leaf terms they cover."""
    sel = set(selected)
    leaves, seen = [], set()

    def walk(node, under):
        term = node["data"]["term"]
        kids = node.get("children", [])
        hit = under or term in sel
        if hit and not kids and term != FAKE and term not in seen:
            seen.add(term)
            leaves.append(term)
        for c in kids:
            walk(c, hit)

    walk(tree, False)
    known = {e["term"] for e in tree_entries(tree)}
    unknown = [s for s in selected if s not in known]
    return leaves, unknown


def flat_terms(vocab_list):
    return [row[0] for row in vocab_list]


def resolve_search(catalog, name):
    names = all_search_names(catalog)
    if name in names:
        return names[name], None
    return None, difflib.get_close_matches(name, list(names), n=5, cutoff=0.5)


def get_search_detail(client, rt, name, context=None):
    path = f"/record-types/{rt}/searches/{name}"
    if context:
        data = client.post(
            f"{path}?expandParams=true", {"contextParamValues": context}
        )
    else:
        data = client.get(path, params={"expandParams": "true"})
    return data["searchData"]


def _render_tree(tree):
    lines, more = [], []

    def walk(node, depth):
        term = node["data"]["term"]
        kids = node.get("children", [])
        if term != FAKE:
            n_desc = len([e for e in tree_entries(node)]) - 1
            label = f"{'  ' * depth}{term}" + (f" /{n_desc}" if kids else "")
            if len(lines) < TREE_MAX_LINES:
                lines.append(label)
            elif depth <= 1:
                more.append(f"{term} /{n_desc}")
        for c in kids:
            walk(c, depth + (0 if term == FAKE else 1))

    walk(tree, 0)
    return lines, more


def _shortlist(terms, query, k):
    if not query:
        return terms[:k]
    words = [w for w in re.split(r"\W+", query.lower()) if len(w) >= 2]
    scored = sorted(
        terms, key=lambda t: -sum(1 for w in words if w in t.lower())
    )
    return scored[:k]


def _vocab_entry(p, query):
    v = p["vocabulary"]
    out = {}
    if is_tree(v):
        lines, more = _render_tree(v)
        out["vocabulary_tree"] = lines
        note = "selecting a parent term selects all of its children"
        if more:
            note += (
                f"; tree truncated at {TREE_MAX_LINES} lines, remaining top-level: "
                + ", ".join(more[:15])
            )
        out["note"] = note
    else:
        rows = [
            row[0] if row[0] == row[1] else f"{row[0]} — {row[1]}" for row in v
        ]
        if len(rows) <= DIRECT_MAX:
            out["allowed_values"] = rows
        else:
            out["allowed_values"] = _shortlist(rows, query, DIRECT_MAX)
            out["note"] = (
                f"{len(rows)} values total; showing {DIRECT_MAX}. Use: wdk.py "
                f"param-options <site> <search> {p['name']} --query <keyword>"
            )
    return out


def build_sheet(search_data, query=None):
    params = search_data.get("parameters", [])
    visible = [p for p in params if p.get("isVisible", True)]
    hidden = [p["name"] for p in params if not p.get("isVisible", True)]
    visible_names = {p["name"] for p in visible}
    entries, deps, template = [], [], {}
    for p in visible:
        e = {
            "name": p["name"],
            "type": p["type"],
            "displayName": p.get("displayName", ""),
            "required": not p.get("allowEmptyValue", False),
            "default": p.get("initialDisplayValue"),
        }
        help_text = strip_html(p.get("help") or "")
        if help_text:
            e["help"] = help_text[:300]
        if p.get("vocabulary") is not None:
            e.update(_vocab_entry(p, query))
        if p["type"] == "input-step":
            e["note"] = "wired via stepTree; submitted as empty string"
        entries.append(e)
        template[p["name"]] = p.get("initialDisplayValue")
        for dep in p.get("dependentParams", []):
            if dep in visible_names:
                deps.append(
                    f"'{p['name']}' controls the vocabulary of '{dep}'; re-read "
                    f"options for '{dep}' after choosing '{p['name']}'"
                )
    return {
        "search": search_data["urlSegment"],
        "displayName": search_data.get("displayName", ""),
        "recordType": search_data.get("outputRecordClassName", ""),
        "description": strip_html(search_data.get("description") or "")[:500],
        "required": [e for e in entries if e["required"]],
        "optional": [e for e in entries if not e["required"]],
        "dependencies": deps,
        "params_template": template,
        "hidden_params_submitted_automatically": hidden,
    }
