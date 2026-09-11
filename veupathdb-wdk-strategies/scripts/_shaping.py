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


def get_search_detail_for_params(client, rt, name, user_params=None):
    """Fetch search detail, automatically applying contextParamValues if user_params
    contains parent parameters that control dependent child vocabularies.
    """
    detail = get_search_detail(client, rt, name)
    if not user_params:
        return detail

    parents = {
        p["name"]
        for p in detail.get("parameters", [])
        if p.get("dependentParams")
    }
    context = {
        p_name: (
            user_params[p_name][0]
            if isinstance(user_params[p_name], (list, tuple)) and user_params[p_name]
            else str(user_params[p_name])
        )
        for p_name in parents
        if p_name in user_params
    }
    if context:
        detail = get_search_detail(client, rt, name, context=context)
    return detail


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


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip().startswith("["):
        return json.loads(value)
    return [value]


def _effective_default(p):
    """Return the usable default value for a parameter, or None if the parameter
    has no usable default (e.g. multi-pick with empty initialDisplayValue '[]'
    where an empty selection is not allowed)."""
    raw = p.get("initialDisplayValue")
    if raw is None:
        return None
    ptype = p.get("type")
    min_count = p.get("minSelectedCount")
    if min_count is None and not p.get("allowEmptyValue", False):
        min_count = 1
    if ptype == "multi-pick-vocabulary":
        items = _as_list(raw)
        if not items and min_count and min_count > 0:
            return None
        return raw
    if not p.get("allowEmptyValue", False) and str(raw).strip() == "":
        return None
    return raw


def build_sheet(search_data, query=None):
    params = search_data.get("parameters", [])
    visible = [p for p in params if p.get("isVisible", True)]
    hidden = [p["name"] for p in params if not p.get("isVisible", True)]
    visible_names = {p["name"] for p in visible}
    entries, deps, template = [], [], {}
    for p in visible:
        eff_default = _effective_default(p)
        e = {
            "name": p["name"],
            "type": p["type"],
            "displayName": p.get("displayName", ""),
            "required": not p.get("allowEmptyValue", False),
            "default": eff_default,
        }
        help_text = strip_html(p.get("help") or "")
        if help_text:
            e["help"] = help_text[:300]
        if p.get("vocabulary") is not None:
            e.update(_vocab_entry(p, query))
        if p["type"] == "input-step":
            e["note"] = "wired via stepTree; submitted as empty string"
        entries.append(e)
        template[p["name"]] = eff_default
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


def param_options(search_data, param_name, query=None, limit=200):
    by_name = {p["name"]: p for p in search_data.get("parameters", [])}
    if param_name not in by_name:
        return {
            "error": "unknown parameter",
            "did_you_mean": difflib.get_close_matches(
                param_name, list(by_name), n=5, cutoff=0.5
            ),
            "valid": sorted(by_name),
        }
    p = by_name[param_name]
    v = p.get("vocabulary")
    if v is None:
        return {"param": param_name, "type": p["type"], "total": 0, "shown": 0,
                "options": [], "note": "parameter has no vocabulary (free-text)"}
    if is_tree(v):
        entries = tree_entries(v)
    else:
        entries = [
            {"term": row[0], "display": row[1], "parent": row[2], "leaf": True}
            for row in v
        ]
    if query:
        q = query.lower()
        entries = [
            e
            for e in entries
            if q in e["term"].lower() or q in (e["display"] or "").lower()
        ]
    total_all = len(tree_entries(v)) if is_tree(v) else len(v)
    return {
        "param": param_name,
        "type": p["type"],
        "total": total_all,
        "shown": min(len(entries), limit),
        "options": entries[:limit],
    }


class ParamError(Exception):
    pass


COUNT_FIELDS = (
    "displayViewTotalCount",
    "viewTotalCount",
    "displayTotalCount",
    "totalCount",
)


def encode_params(search_data, user_params):
    params = search_data.get("parameters", [])
    by_name = {p["name"]: p for p in params}
    unknown = sorted(set(user_params) - set(by_name))
    if unknown:
        hints = {
            u: difflib.get_close_matches(u, list(by_name), n=3, cutoff=0.5)
            for u in unknown
        }
        raise ParamError(
            f"unknown parameter(s) {unknown}; did you mean: {hints}? "
            f"valid: {sorted(by_name)}"
        )
    wire, missing = {}, []
    for p in params:
        name, ptype = p["name"], p["type"]
        if ptype == "input-step":
            wire[name] = ""
            continue
        supplied = name in user_params and user_params[name] is not None
        value = user_params[name] if supplied else _effective_default(p)
        if value is None:
            if not p.get("allowEmptyValue", False) and p.get("isVisible", True):
                missing.append(name)
            wire[name] = ""
            continue
        vocab = p.get("vocabulary")
        if ptype == "multi-pick-vocabulary":
            items = [str(i) for i in _as_list(value)]
            min_count = p.get("minSelectedCount")
            if min_count is None and not p.get("allowEmptyValue", False):
                min_count = 1
            if not items and min_count and min_count > 0:
                search_name = search_data.get("urlSegment", "")
                raise ParamError(
                    f"parameter '{name}' cannot be empty (requires at least {min_count} selection(s); "
                    f"browse options with: uv run scripts/wdk.py param-options <site> {search_name} {name})"
                )
            if is_tree(vocab):
                leaves, bad = expand_to_leaves(vocab, items)
                if bad:
                    all_terms = [e["term"] for e in tree_entries(vocab)]
                    hints = {
                        b: difflib.get_close_matches(b, all_terms, n=3, cutoff=0.5)
                        for b in bad
                    }
                    raise ParamError(f"unknown value(s) for '{name}': {hints}")
                items = leaves
            elif isinstance(vocab, list):
                valid = set(flat_terms(vocab))
                bad = [i for i in items if i not in valid]
                if bad:
                    hints = {
                        b: difflib.get_close_matches(b, sorted(valid), n=3, cutoff=0.5)
                        for b in bad
                    }
                    raise ParamError(f"unknown value(s) for '{name}': {hints}")
            wire[name] = json.dumps(items)
        else:
            sval = str(value)
            if (
                ptype == "single-pick-vocabulary"
                and isinstance(vocab, list)
                and sval not in set(flat_terms(vocab))
            ):
                hint = difflib.get_close_matches(
                    sval, flat_terms(vocab), n=3, cutoff=0.5
                )
                raise ParamError(
                    f"'{sval}' is not in the vocabulary of '{name}'; "
                    f"did you mean {hint}?"
                )
            wire[name] = sval
    if missing:
        hints = []
        search_name = search_data.get("urlSegment", "")
        for m in missing:
            p_obj = next((x for x in params if x["name"] == m), None)
            if p_obj and p_obj.get("type") == "multi-pick-vocabulary":
                hints.append(
                    f"'{m}' requires at least 1 selection; browse options with: "
                    f"uv run scripts/wdk.py param-options <site> {search_name} {m}"
                )
        msg = f"required parameter(s) with no value and no default: {missing}"
        if hints:
            msg += f" ({'; '.join(hints)})"
        raise ParamError(msg)
    return wire


def extract_count(meta):
    for field in COUNT_FIELDS:
        if meta.get(field) is not None:
            return meta[field], field
    return None, None


def shape_records(response):
    meta = response.get("meta", {})
    count, field = extract_count(meta)
    return {
        "count": count if count is not None else "unmeasured",
        "count_field": field,
        "counts": {f: meta.get(f) for f in COUNT_FIELDS},
        "records": [
            {
                "id": {part["name"]: part["value"] for part in r.get("id", [])},
                "displayName": r.get("displayName"),
                "attributes": r.get("attributes", {}),
            }
            for r in response.get("records", [])
        ],
    }


def run_report(client, rt, search, wire_params, num_records=1, attributes=None):
    body = {
        "searchConfig": {"parameters": wire_params},
        "reportConfig": {"pagination": {"offset": 0, "numRecords": num_records}},
    }
    if attributes:
        body["reportConfig"]["attributes"] = attributes
    return client.post(f"/record-types/{rt}/searches/{search}/reports/standard", body)


def shape_record_type(raw, query=None, name_only=False, exclude=None):
    rt_name = raw.get("urlSegment") or raw.get("name")
    display_name = raw.get("displayName", "")
    pk = raw.get("primaryKeyColumnRefs", [])

    raw_attrs = raw.get("attributes", [])
    raw_tables = raw.get("tables", [])

    q = query.lower() if query else None

    exclude_patterns = []
    if exclude:
        if isinstance(exclude, str):
            exclude_patterns = [p.strip().lower() for p in exclude.split(",") if p.strip()]
        elif isinstance(exclude, (list, tuple)):
            exclude_patterns = [str(p).strip().lower() for p in exclude if str(p).strip()]

    attrs = []
    for a in raw_attrs:
        name = a.get("name", "")
        disp = a.get("displayName", "")
        dtype = a.get("columnDataType", "STRING")
        name_l = name.lower()
        disp_l = disp.lower()

        if exclude_patterns and any(p in name_l or p in disp_l for p in exclude_patterns):
            continue

        if q is not None:
            if name_only:
                if q not in name_l:
                    continue
            else:
                if q not in name_l and q not in disp_l:
                    continue

        attrs.append({"name": name, "displayName": disp, "type": dtype})

    tables = []
    for t in raw_tables:
        name = t.get("name", "")
        disp = t.get("displayName", "")
        cols = [c.get("name", "") for c in t.get("attributes", [])]
        name_l = name.lower()
        disp_l = disp.lower()
        cols_l = [c.lower() for c in cols]

        if exclude_patterns and any(p in name_l or p in disp_l for p in exclude_patterns):
            continue

        if q is not None:
            if name_only:
                if q not in name_l and not any(q in c for c in cols_l):
                    continue
            else:
                if q not in name_l and q not in disp_l and not any(q in c for c in cols_l):
                    continue

        tables.append({"name": name, "displayName": disp, "columns": cols})

    out = {
        "record_type": rt_name,
        "displayName": display_name,
        "primary_key": pk,
        "total_attributes": len(raw_attrs),
        "total_tables": len(raw_tables),
    }

    if q or exclude_patterns or name_only:
        if q:
            out["filter"] = query
        if name_only:
            out["name_only"] = True
        if exclude_patterns:
            out["exclude"] = exclude_patterns if len(exclude_patterns) > 1 else exclude_patterns[0]
        out["matching_attributes"] = len(attrs)
        out["matching_tables"] = len(tables)
        if q:
            out["attributes"] = attrs
        else:
            if len(attrs) > 60:
                out["attributes"] = attrs[:50]
                out["attributes_note"] = (
                    f"showing first 50 of {len(attrs)} attributes; use --filter to filter further"
                )
            else:
                out["attributes"] = attrs
        out["tables"] = tables
    else:
        if len(attrs) > 60:
            out["attributes"] = attrs[:50]
            out["attributes_note"] = (
                f"showing first 50 of {len(raw_attrs)} attributes; use --filter to filter"
            )
        else:
            out["attributes"] = attrs
        out["tables"] = tables
    return out


def clean_table_row(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if k in ("sort_key", "sortKey", "clustalInput"):
            continue
        if isinstance(v, str) and (v.startswith("<input") or v.startswith("<button")):
            continue
        out[k] = v
    return out


def shape_record(raw: dict, filter_query: str | None = None) -> dict:
    raw_tables = raw.get("tables", {})
    raw_attrs = raw.get("attributes", {})

    tables = {}
    for t_name, rows in raw_tables.items():
        cleaned = [clean_table_row(r) for r in rows]
        if filter_query:
            q = filter_query.lower()
            cleaned = [
                r
                for r in cleaned
                if q
                in " ".join(
                    str(v.get("displayText", v) if isinstance(v, dict) else v)
                    for v in r.values()
                ).lower()
            ]
        tables[t_name] = cleaned

    attrs = raw_attrs
    if filter_query and not raw_tables:
        q = filter_query.lower()
        attrs = {
            k: v
            for k, v in raw_attrs.items()
            if q in k.lower() or q in str(v).lower()
        }

    out = {
        "id": raw.get("id"),
        "displayName": raw.get("displayName"),
        "recordClassName": raw.get("recordClassName"),
    }
    if filter_query:
        out["filter"] = filter_query
    out["attributes"] = attrs
    out["tables"] = tables
    return out

