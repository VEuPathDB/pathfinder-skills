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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="wdk.py", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("sites", help="list site ids, service URLs, project ids")
    sp.set_defaults(func=cmd_sites)

    sp = sub.add_parser("whoami", help="verify token; print numeric user id")
    sp.add_argument("site")
    sp.set_defaults(func=cmd_whoami)

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
