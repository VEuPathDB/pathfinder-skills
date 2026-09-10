"""WDK transport. Auth is a COOKIE (Authorization=<token>), exactly one pair."""
import json
import os
import pathlib
import time

import httpx

from _sites import SITES, service_url

# scripts/ -> veupathdb-wdk-strategies/ -> pathfinder-skills/
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CACHE_DIR = pathlib.Path.home() / ".cache" / "veupathdb-wdk"
CACHE_TTL_S = 7 * 24 * 3600


class WDKError(Exception):
    def __init__(self, message, status=None, endpoint=None):
        self.status = status
        self.endpoint = endpoint
        super().__init__(message)

    def __str__(self):
        bits = []
        if self.status:
            bits.append(f"HTTP {self.status}")
        if self.endpoint:
            bits.append(self.endpoint)
        bits.append(super().__str__())
        return " | ".join(bits)


class GuestTokenError(WDKError):
    pass


def load_token(root=None):
    tok = os.environ.get("VEUPATHDB_BEARER_TOKEN")
    if tok:
        return tok.strip()
    env = pathlib.Path(root or REPO_ROOT) / ".env"
    if env.is_file():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line.startswith("VEUPATHDB_BEARER_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'") or None
    return None


def _is_delayed(body):
    return isinstance(body, dict) and body.get("message") == "WDK-DELAYED-RESULT"


class Client:
    def __init__(self, site_id, token=None, transport=None, backoff=2.0):
        self.site_id = site_id
        self.token = token
        self.backoff = backoff
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Cookie"] = f"Authorization={token}"
            headers["Authorization"] = f"Bearer {token}"
        self._http = httpx.Client(
            base_url=service_url(site_id),
            headers=headers,
            timeout=SITES[site_id]["timeout"],
            follow_redirects=True,
            transport=transport,
        )
        self._user_id = None

    def request(self, method, path, body=None, params=None, retries=3):
        last = None
        for attempt in range(retries):
            if attempt and self.backoff:
                time.sleep(self.backoff**attempt)
            try:
                r = self._http.request(method, path, json=body, params=params)
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last = WDKError(f"{type(e).__name__}: {e}", endpoint=path)
                continue
            if r.status_code >= 500:
                last = WDKError(r.text[:500], status=r.status_code, endpoint=path)
                continue
            if r.status_code >= 400:
                raise WDKError(r.text[:1000], status=r.status_code, endpoint=path)
            if r.status_code == 204 or not r.content:
                return None
            ctype = r.headers.get("content-type", "")
            data = r.json() if "json" in ctype else r.text
            if _is_delayed(data):
                last = WDKError("WDK-DELAYED-RESULT (result not ready)", endpoint=path)
                continue
            return data
        raise last

    def get(self, path, params=None):
        return self.request("GET", path, params=params)

    def post(self, path, body, idempotent=True):
        return self.request("POST", path, body=body, retries=3 if idempotent else 1)

    def put(self, path, body):
        return self.request("PUT", path, body=body)

    def patch(self, path, body):
        return self.request("PATCH", path, body=body)

    def delete(self, path):
        return self.request("DELETE", path)

    def user_id(self):
        if self._user_id is None:
            if not self.token:
                raise GuestTokenError(
                    "no token: set VEUPATHDB_BEARER_TOKEN (env or repo-root .env). "
                    "Register at the site to obtain a registered-user token.",
                    endpoint="/users/current",
                )
            me = self.get("/users/current")
            if me.get("isGuest"):
                raise GuestTokenError(
                    "token identifies a GUEST user; WDK refuses programmatic guest "
                    "access. Register at the site and supply a registered-user token.",
                    endpoint="/users/current",
                )
            self._user_id = int(me["id"])
        return self._user_id


def fetch_catalog(client, refresh=False):
    """Record types + compact search listings. Disk-cached 7 days per site."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        return json.loads(cache.read_text())
    record_types = client.get("/record-types")
    searches = {}
    for rt in record_types:
        try:
            listing = client.get(f"/record-types/{rt}/searches")
        except WDKError:
            continue  # some record types have no search listing; skip, don't fail
        searches[rt] = [
            {
                "name": s["urlSegment"],
                "displayName": s.get("displayName", ""),
                "description": s.get("description") or s.get("summary") or "",
                "paramNames": s.get("paramNames", []),
                "outputRecordClassName": s.get("outputRecordClassName", ""),
            }
            for s in listing
        ]
    catalog = {
        "cached_at": time.time(),
        "record_types": record_types,
        "searches": searches,
    }
    cache.write_text(json.dumps(catalog))
    return catalog
