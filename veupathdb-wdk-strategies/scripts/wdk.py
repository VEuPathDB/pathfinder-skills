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


def cmd_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    cat = fetch_catalog(client(args.site), refresh=args.refresh)
    print("\n".join(catalog_lines(cat, record_type=args.record_type)))


def cmd_catalog(args) -> None:
    from _client import fetch_catalog
    from _shaping import catalog_lines

    cat = fetch_catalog(client(args.site), refresh=args.refresh)
    lines = catalog_lines(cat, record_type=args.record_type)
    print(f"# {args.site}: {len(lines)} searches (record_type\tname\tdisplayName\tdescription)")
    print("\n".join(lines))


def cmd_find_searches(args) -> None:
    from _client import fetch_catalog
    from _shaping import score_searches

    hits = score_searches(fetch_catalog(client(args.site)), args.query, limit=args.limit)
    if not hits:
        fail(
            f"no searches match '{args.query}'. Broaden the query, or run "
            f"'wdk.py catalog {args.site}' and reason over the full listing "
            "(recommended: in a sub-agent)"
        )
    emit(hits)


def _resolve_or_fail(cat, name, site):
    from _shaping import resolve_search

    rt, suggestions = resolve_search(cat, name)
    if rt is None:
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
    rt = _resolve_or_fail(cat, args.search, args.site)
    emit(build_sheet(get_search_detail(c, rt, args.search), query=args.query))


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
    rt = _resolve_or_fail(cat, args.search, args.site)
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
    sp.set_defaults(func=cmd_searches)

    sp = sub.add_parser(
        "catalog",
        help="full compact search catalog (primary discovery input; ~25-75k tokens)",
    )
    sp.add_argument("site")
    sp.add_argument("--record-type")
    sp.add_argument("--refresh", action="store_true")
    sp.set_defaults(func=cmd_catalog)

    sp = sub.add_parser("find-searches", help="lexical search-name lookup (convenience)")
    sp.add_argument("site")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=20)
    sp.set_defaults(func=cmd_find_searches)

    sp = sub.add_parser("inspect", help="shaped parameter sheet for one search")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("--query", help="hint used to shortlist huge vocabularies")
    sp.set_defaults(func=cmd_inspect)

    sp = sub.add_parser("param-options", help="browse/filter a parameter's vocabulary")
    sp.add_argument("site")
    sp.add_argument("search")
    sp.add_argument("param")
    sp.add_argument("--query", help="case-insensitive substring filter")
    sp.add_argument("--context", nargs="*", metavar="PARENT=VALUE",
                    help="values for params this vocabulary depends on")
    sp.add_argument("--limit", type=int, default=200)
    sp.set_defaults(func=cmd_param_options)

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
