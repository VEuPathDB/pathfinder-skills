"""WDK transport. Auth is a COOKIE (Authorization=<token>), exactly one pair."""
import difflib
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


def config_dir() -> pathlib.Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = pathlib.Path(xdg) if xdg else (pathlib.Path.home() / ".config")
    return base / "veupathdb"


def token_path() -> pathlib.Path:
    return config_dir() / "token"


def save_token(token: str) -> pathlib.Path:
    tok = token.strip()
    if not tok:
        raise ValueError("Cannot save empty token")
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    p = token_path()
    p.write_text(tok + "\n", encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


def delete_token() -> bool:
    p = token_path()
    if p.is_file():
        p.unlink()
        return True
    return False


def load_token(root=None) -> str | None:
    tok = os.environ.get("VEUPATHDB_BEARER_TOKEN")
    if tok:
        return tok.strip()
    p = token_path()
    if p.is_file():
        try:
            val = p.read_text(encoding="utf-8").strip()
            if val:
                return val
        except OSError:
            pass
    return None


def verify_token(site_id: str, token: str) -> dict:
    """Verify that a token belongs to a registered VEuPathDB user.

    Returns the user dict from /users/current.
    Raises GuestTokenError or WDKError on failure.
    """
    tok = token.strip()
    if not tok:
        raise ValueError("Token cannot be empty")
    c = Client(site_id, token=tok)
    user = c.get("/users/current")
    if not isinstance(user, dict):
        raise WDKError(f"Unexpected response from /users/current: {user}", endpoint="/users/current")
    if user.get("isGuest"):
        raise GuestTokenError(
            "Token identifies a GUEST user; register at the site to obtain a registered-user token.",
            endpoint="/users/current",
        )
    return user


def login_with_credentials(
    site_id: str, email: str, password: str, redirect_url: str | None = None
) -> tuple[str, dict]:
    """Authenticate against VEuPathDB with email and password.

    Returns (token, user_dict).
    Raises WDKError on failure.
    """
    site_url = service_url(site_id)
    payload = {
        "email": email.strip(),
        "password": password,
        "redirectUrl": redirect_url or site_url,
    }
    with httpx.Client(
        base_url=site_url, timeout=SITES[site_id]["timeout"], follow_redirects=False
    ) as http:
        resp = http.post("/login", json=payload)

    # 1. Extract Authorization cookie from Set-Cookie headers
    token = None
    for header in resp.headers.get_list("set-cookie"):
        for part in header.split(";"):
            part = part.strip()
            if part.startswith("Authorization="):
                token = part.split("=", 1)[1].strip('"')
                break
        if token:
            break

    if not token and "Authorization" in resp.cookies:
        token = resp.cookies["Authorization"]

    # 2. If token not found, inspect response for error message
    if not token:
        msg = "Invalid email or password"
        if resp.status_code >= 400:
            msg = f"Login failed (HTTP {resp.status_code}): {resp.text[:300]}"
        else:
            try:
                data = resp.json()
                if isinstance(data, dict):
                    if data.get("message"):
                        msg = data["message"]
                    elif data.get("success") is False:
                        msg = "Authentication failed: invalid username or password"
            except Exception:
                pass
        raise WDKError(
            msg,
            status=resp.status_code if resp.status_code != 200 else 401,
            endpoint="/login",
        )

    # 3. Verify token against /users/current
    user = verify_token(site_id, token)
    return token, user


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
                    "no token: run 'wdk.py login' or set VEUPATHDB_BEARER_TOKEN. "
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


DEFAULT_EXCLUDED_PARAM_PREFIXES = ("eda_",)


def get_excluded_param_prefixes() -> tuple[str, ...]:
    env_val = os.environ.get("WDK_EXCLUDED_PARAM_PREFIXES")
    if env_val is not None:
        if not env_val.strip():
            return ()
        return tuple(p.strip() for p in env_val.split(",") if p.strip())
    return DEFAULT_EXCLUDED_PARAM_PREFIXES


def filter_catalog_searches(catalog: dict, excluded_prefixes: tuple[str, ...] | None = None) -> dict:
    """Return catalog with searches filtered out if any param matches an excluded prefix."""
    if excluded_prefixes is None:
        excluded_prefixes = get_excluded_param_prefixes()
    if not excluded_prefixes:
        return catalog

    filtered_searches = {}
    for rt, searches in catalog.get("searches", {}).items():
        filtered_searches[rt] = [
            s
            for s in searches
            if not any(
                isinstance(p, str)
                and any(p.startswith(prefix) for prefix in excluded_prefixes)
                for p in s.get("paramNames", [])
            )
        ]
    return {
        **catalog,
        "searches": filtered_searches,
    }


def fetch_catalog(client, refresh=False, excluded_param_prefixes=None):
    """Record types + compact search listings. Disk-cached 7 days per site.
    Filters out searches with excluded_param_prefixes (default: ('eda_',)).
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        raw_catalog = json.loads(cache.read_text())
    else:
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
        raw_catalog = {
            "cached_at": time.time(),
            "record_types": record_types,
            "searches": searches,
        }
        cache.write_text(json.dumps(raw_catalog))

    return filter_catalog_searches(raw_catalog, excluded_prefixes=excluded_param_prefixes)


def fetch_record_type(client, record_type, refresh=False):
    """Fetch expanded record-type definition. Disk-cached 7 days per site/rt."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{client.site_id}_rt_{record_type}.json"
    if (
        not refresh
        and cache.is_file()
        and time.time() - cache.stat().st_mtime < CACHE_TTL_S
    ):
        return json.loads(cache.read_text())
    try:
        raw = client.get(f"/record-types/{record_type}", params={"format": "expanded"})
    except WDKError as err:
        try:
            all_rts = client.get("/record-types")
        except Exception:
            all_rts = []
        hint = difflib.get_close_matches(record_type, all_rts, n=3, cutoff=0.5)
        if hint:
            raise WDKError(
                f"unknown record type '{record_type}'; did you mean {hint}? Valid: {sorted(all_rts)}",
                status=404,
                endpoint=f"/record-types/{record_type}",
            ) from None
        raise err
    cache.write_text(json.dumps(raw))
    return raw
