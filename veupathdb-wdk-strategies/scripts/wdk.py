#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx"]
# ///
"""VEuPathDB WDK CLI — build search strategies from the command line.

Run `wdk.py --help` for subcommands, `wdk.py <sub> --help` for details.
"""
import argparse
import json
import sys

from _sites import SITES, UnknownSiteError, strategy_url


def emit(obj) -> None:
    print(json.dumps(obj, indent=1, ensure_ascii=False))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def client(site_id):
    from _client import Client, load_token

    return Client(site_id, token=load_token())


def cmd_sites(args) -> None:
    emit(
        {
            sid: {"service": cfg["base_url"], "project": cfg["project_id"]}
            for sid, cfg in sorted(SITES.items())
        }
    )


def cmd_whoami(args) -> None:
    c = client(args.site)
    me = c.get("/users/current")
    if me.get("isGuest"):
        fail(
            "token identifies a GUEST user; register at the site and supply a "
            "registered-user bearer token"
        )
    emit({"site": args.site, "user_id": me["id"], "email": me.get("email")})


def cmd_record_types(args) -> None:
    emit(client(args.site).get("/record-types"))


def _parse_excluded_prefixes(arg):
    if arg is None:
        return None
    out = []
    for item in arg:
        for p in item.split(","):
            p = p.strip()
            if p:
                out.append(p)
    if not out and any(item == "" or item.strip() == "" for item in arg):
        return ()
    return tuple(out) if out else ()


def cmd_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), refresh=args.refresh, excluded_param_prefixes=prefixes)
    print("\n".join(catalog_lines(cat, record_type=args.record_type)))


def cmd_catalog(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), refresh=args.refresh, excluded_param_prefixes=prefixes)
    lines = catalog_lines(cat, record_type=args.record_type)
    print(f"# {args.site}: {len(lines)} searches (record_type\tname\tdisplayName\tdescription)")
    print("\n".join(lines))


def cmd_find_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import score_searches

    prefixes = _parse_excluded_prefixes(getattr(args, "exclude_param_prefix", None))
    cat = fetch_catalog(client(args.site), excluded_param_prefixes=prefixes)
    hits = score_searches(cat, args.query, limit=args.limit)
    if not hits:
        fail(
            f"no searches match '{args.query}'. Broaden the query, or run "
            f"'wdk.py catalog {args.site}' and reason over the full listing "
            "(recommended: in a sub-agent)"
        )
    emit(hits)


def _resolve_or_fail(cat, name, site, client_inst=None):
    from _shaping import resolve_search

    rt, suggestions = resolve_search(cat, name)
    if rt is None:
        if client_inst is not None:
            from _client import fetch_catalog
            raw_cat = fetch_catalog(client_inst, excluded_param_prefixes=())
            raw_rt, _ = resolve_search(raw_cat, name)
            if raw_rt is not None:
                fail(
                    f"search '{name}' on {site} is unavailable: it uses excluded "
                    "parameter prefix(es) (e.g. 'eda_') which are not supported via WDK directly."
                )
        fail(
            f"unknown search '{name}' on {site}. Did you mean: "
            f"{', '.join(suggestions) or '(no close match)'}? "
            f"Run 'wdk.py catalog {site}' for the full list."
        )
    return rt


def cmd_inspect(args) -> None:
    from _client import fetch_catalog
    from _shaping import build_sheet, get_search_detail

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    emit(build_sheet(get_search_detail(c, rt, args.search), query=args.query))


def cmd_inspect_record_type(args) -> None:
    from _client import fetch_record_type
    from _shaping import shape_record_type

    c = client(args.site)
    raw = fetch_record_type(c, args.record_type, refresh=args.refresh)
    f = getattr(args, "filter", None) or getattr(args, "query", None)
    emit(
        shape_record_type(
            raw,
            query=f,
            name_only=getattr(args, "name_only", False),
            exclude=getattr(args, "exclude", None),
        )
    )


def _parse_kv(pairs):
    out = {}
    for pair in pairs or []:
        if "=" not in pair:
            fail(f"--context expects key=value, got '{pair}'")
        k, val = pair.split("=", 1)
        out[k] = val
    return out


def cmd_param_options(args) -> None:
    from _client import fetch_catalog
    from _shaping import get_search_detail, param_options

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    detail = get_search_detail(c, rt, args.search)
    parents = [
        p["name"]
        for p in detail["parameters"]
        if args.param in p.get("dependentParams", [])
    ]
    note = None
    if parents:
        given = _parse_kv(args.context)
        context = {
            name: given.get(
                name,
                next(
                    q.get("initialDisplayValue")
                    for q in detail["parameters"]
                    if q["name"] == name
                ),
            )
            for name in parents
        }
        detail = get_search_detail(c, rt, args.search, context=context)
        used = ", ".join(f"{k}={v}" for k, v in context.items())
        defaulted = [k for k in parents if k not in given]
        note = f"vocabulary read under {used}"
        if defaulted:
            note += (
                f" ({'/'.join(defaulted)} defaulted — pass --context "
                f"{defaulted[0]}=... to change)"
            )
    out = param_options(detail, args.param, query=args.query, limit=args.limit)
    if note and "error" not in out:
        out["context_note"] = note
    emit(out)


def _load_params(raw):
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"--params is not valid JSON: {e}")
    if not isinstance(params, dict):
        fail("--params must be a JSON object of {param: value}")
    return params


def _prepared(args):
    from _client import fetch_catalog
    from _shaping import ParamError, encode_params, get_search_detail_for_params

    c = client(args.site)
    cat = fetch_catalog(c)
    rt = _resolve_or_fail(cat, args.search, args.site, client_inst=c)
    params = _load_params(args.params)
    detail = get_search_detail_for_params(c, rt, args.search, params)
    try:
        wire = encode_params(detail, params)
    except ParamError as e:
        fail(str(e))
    return c, rt, wire, detail


def cmd_count(args) -> None:
    from _shaping import extract_count, run_report

    c, rt, wire, _ = _prepared(args)
    resp = run_report(c, rt, args.search, wire, num_records=1)
    count, field = extract_count(resp.get("meta", {}))
    emit(
        {
            "search": args.search,
            "count": count if count is not None else "unmeasured",
            "count_field": field,
            "counts": {
                k: resp.get("meta", {}).get(k)
                for k in (
                    "displayViewTotalCount",
                    "viewTotalCount",
                    "displayTotalCount",
                    "totalCount",
                )
            },
        }
    )


def cmd_preview(args) -> None:
    from _shaping import run_report, shape_records

    c, rt, wire, detail = _prepared(args)
    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    else:
        attrs = detail.get("defaultAttributes")
    emit(
        shape_records(
            run_report(c, rt, args.search, wire, num_records=args.limit, attributes=attrs)
        )
    )


def cmd_create_strategy(args) -> None:
    from _client import fetch_catalog
    from _shaping import ParamError
    from _strategy import SpecError, build_strategy

    c = client(args.site)
    try:
        spec = json.loads(args.spec)
    except json.JSONDecodeError as e:
        fail(f"--spec is not valid JSON: {e}")
    try:
        emit(build_strategy(c, fetch_catalog(c), spec, args.name))
    except (SpecError, ParamError) as e:
        fail(str(e))


def cmd_strategy(args) -> None:
    from _strategy import shape_strategy

    c = client(args.site)
    uid = c.user_id()
    emit(shape_strategy(args.site, c.get(f"/users/{uid}/strategies/{args.id}")))


def cmd_list_strategies(args) -> None:
    from _sites import strategy_url

    c = client(args.site)
    uid = c.user_id()
    strategies = c.get(f"/users/{uid}/strategies")
    emit(
        [
            {
                "strategy_id": s.get("strategyId", s.get("id")),
                "name": s.get("name"),
                "url": strategy_url(args.site, s.get("strategyId", s.get("id"))),
            }
            for s in strategies
        ]
    )


def cmd_delete_strategy(args) -> None:
    if not args.yes:
        fail("refusing to delete without --yes")
    c = client(args.site)
    uid = c.user_id()
    c.delete(f"/users/{uid}/strategies/{args.id}")
    emit({"deleted": args.id})


def cmd_results(args) -> None:
    from _shaping import get_search_detail, shape_records

    c = client(args.site)
    uid = c.user_id()
    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    else:
        attrs = ["primary_key"]
        try:
            step = c.get(f"/users/{uid}/steps/{args.step}")
            rt = step.get("recordClassName")
            search_name = step.get("searchName")
            if rt and search_name:
                detail = get_search_detail(c, rt, search_name)
                da = detail.get("defaultAttributes")
                if da:
                    attrs = da
        except Exception:
            pass
    body = {
        "reportConfig": {
            "pagination": {"offset": 0, "numRecords": args.limit},
            "attributes": attrs,
        }
    }
    emit(shape_records(c.post(f"/users/{uid}/steps/{args.step}/reports/standard", body)))


def cmd_download_url(args) -> None:
    from _sites import service_url

    c = client(args.site)
    if args.config:
        try:
            config = json.loads(args.config)
        except json.JSONDecodeError as e:
            fail(f"--config is not valid JSON: {e}")
    else:
        config = {
            "attributes": ["primary_key"],
            "includeHeader": True,
            "attachmentType": "plain",
        }
    resp = c.post(
        "/temporary-results",
        {"stepId": args.step, "reportName": args.report, "reportConfig": config},
        idempotent=False,
    )
    emit({"download_url": f"{service_url(args.site)}/temporary-results/{resp['id']}"})


def cmd_fetch_record(args) -> None:
    from _sites import project_id

    c = client(args.site)
    rt = args.record_type
    if args.primary_key:
        try:
            pk_val = json.loads(args.primary_key)
            if isinstance(pk_val, dict):
                pk = [{"name": k, "value": str(v)} for k, v in pk_val.items()]
            elif isinstance(pk_val, list):
                pk = pk_val
            else:
                fail("--primary-key must be a JSON object or array of {name, value}")
        except json.JSONDecodeError as e:
            fail(f"--primary-key is not valid JSON: {e}")
    elif args.id:
        if rt in ("gene", "organism"):
            pk = [
                {"name": "source_id", "value": args.id},
                {"name": "project_id", "value": project_id(args.site)},
            ]
        elif rt == "transcript":
            if not args.gene_id:
                fail("record-type transcript requires --gene-id or --primary-key")
            pk = [
                {"name": "gene_source_id", "value": args.gene_id},
                {"name": "source_id", "value": args.id},
                {"name": "project_id", "value": project_id(args.site)},
            ]
        else:
            pk = [{"name": "source_id", "value": args.id}]
    else:
        fail("either ID argument or --primary-key is required")

    if args.attributes:
        attrs = [a.strip() for a in args.attributes.split(",") if a.strip()]
    elif rt == "gene":
        attrs = [
            "primary_key",
            "source_id",
            "name",
            "product",
            "organism",
            "gene_type",
            "exon_count",
            "transcript_count",
            "location_text",
        ]
    else:
        attrs = ["primary_key"]

    tbls = [t.strip() for t in args.tables.split(",") if t.strip()] if args.tables else []

    payload = {
        "primaryKey": pk,
        "attributes": attrs,
        "tables": tbls,
    }
    res = c.post(f"/record-types/{rt}/records", payload, idempotent=True)
    from _shaping import shape_record

    emit(shape_record(res, filter_query=getattr(args, "filter", None)))



def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wdk.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sites", help="list site ids, service URLs, project ids")
    sp.set_defaults(func=cmd_sites)

    sp = sub.add_parser("whoami", help="verify token; print numeric user id")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_whoami)

    sp = sub.add_parser("record-types", help="list record type url segments")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_record_types)

    sp = sub.add_parser("searches", help="list searches for one record type")
    sp.add_argument("site")
    sp.add_argument("record_type")
    sp.add_argument("--refresh", action="store_true", help="bypass 7-day disk cache")
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_searches)

    sp = sub.add_parser(
        "catalog",
        help="full compact search catalog (primary discovery input; ~25-75k tokens)",
    )
    sp.add_argument("site")
    sp.add_argument("--record-type")
    sp.add_argument("--refresh", action="store_true")
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_catalog)

    sp = sub.add_parser("find-searches", help="lexical search-name lookup (convenience)")
    sp.add_argument("site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument(
        "--exclude-param-prefix",
        action="append",
        help="exclude searches with params starting with prefix (default: eda_; pass '' to disable)",
    )
    sp.set_defaults(func=cmd_find_searches)

    sp = sub.add_parser(
        "inspect-search",
        aliases=["inspect"],
        help="shaped parameter sheet for one search",
    )
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument(
        "--filter",
        "--query",
        dest="query",
        help="hint used to shortlist huge vocabularies",
    )
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser(
        "inspect-record-type",
        help="inspect a record type schema (primary key, attributes, tables)",
    )
    sp.add_argument("site")
    sp.add_argument("record_type")
    sp.add_argument(
        "--filter",
        "--query",
        dest="filter",
        help="filter attributes and tables by keyword",
    )
    sp.add_argument(
        "--name-only",
        action="store_true",
        help="only match filter keyword against attribute/table name, not displayName",
    )
    sp.add_argument(
        "--exclude",
        metavar="PATTERN",
        help="exclude attributes/tables matching pattern (substring or comma-separated, e.g. 'pan_')",
    )
    sp.add_argument(
        "--refresh", action="store_true", help="bypass 7-day disk cache"
    )
    sp.set_defaults(func=cmd_inspect_record_type)

    sp = sub.add_parser(
        "param-options", help="browse/filter a parameter's vocabulary"
    )
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("param")
    sp.add_argument(
        "--filter",
        "--query",
        dest="query",
        help="case-insensitive substring filter",
    )
    sp.add_argument(
        "--context",
        nargs="*",
        metavar="PARENT=VALUE",
        help="values for params this vocabulary depends on",
    )
    sp.add_argument("--limit", type=int, default=200)
    sp.set_defaults(func=cmd_param_options)

    sp = sub.add_parser("count", help="result count without creating anything (anonymous report)")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True, help='JSON object, e.g. \'{"organism": ["Plasmodium"]}\'')
    sp.set_defaults(func=cmd_count)

    sp = sub.add_parser("preview", help="sample records without creating anything")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--params", required=True)
    sp.add_argument("--limit", type=int, default=5)
    sp.add_argument("--attributes", help="comma-separated attribute names")
    sp.set_defaults(func=cmd_preview)

    sp = sub.add_parser("create-strategy", help="create steps + strategy from a declarative JSON spec")
    sp.add_argument("site")
    sp.add_argument("--spec", required=True, help="JSON node tree; see references/strategies.md")
    sp.add_argument("--name", default="wdk.py strategy")
    sp.set_defaults(func=cmd_create_strategy)

    sp = sub.add_parser("strategy", help="strategy detail: tree, counts, url")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.set_defaults(func=cmd_strategy)

    sp = sub.add_parser("list-strategies", help="list your strategies on a site")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_list_strategies)

    sp = sub.add_parser("delete-strategy", help="delete a strategy (destructive)")
    sp.add_argument("site")
    sp.add_argument("id", type=int)
    sp.add_argument("--yes", action="store_true")
    sp.set_defaults(func=cmd_delete_strategy)

    sp = sub.add_parser("results", help="records for an existing step")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--attributes")
    sp.set_defaults(func=cmd_results)

    sp = sub.add_parser("download-url", help="temporary download URL for a step's results")
    sp.add_argument("site")
    sp.add_argument("--step", type=int, required=True)
    sp.add_argument("--report", default="attributesTabular")
    sp.add_argument("--config", help="JSON reportConfig override")
    sp.set_defaults(func=cmd_download_url)

    sp = sub.add_parser("fetch-record", help="fetch a single record (e.g. gene) with attributes/tables")
    sp.add_argument("site")
    sp.add_argument("id", nargs="?", help="record primary identifier (e.g. AGAP001212)")
    sp.add_argument("--record-type", default="gene", help="record type (default: gene)")
    sp.add_argument("--gene-id", help="parent gene ID if record-type is transcript")
    sp.add_argument("--primary-key", help="JSON override for primaryKey list/dict")
    sp.add_argument("--attributes", help="comma-separated attribute names")
    sp.add_argument("--tables", help="comma-separated table names (e.g. GeneTranscripts, Orthologs)")
    sp.add_argument(
        "--filter",
        "--query",
        dest="filter",
        help="case-insensitive substring filter for table rows and attributes",
    )
    sp.set_defaults(func=cmd_fetch_record)

    return p


def main() -> None:
    from _client import WDKError

    args = build_parser().parse_args()
    try:
        args.func(args)
    except (UnknownSiteError, WDKError) as e:
        fail(str(e))


if __name__ == "__main__":
    main()
