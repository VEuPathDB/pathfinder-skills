import json

import httpx
import pytest


def _client(handler, **kw):
    from _client import Client

    kw.setdefault("token", "tok-x")
    kw.setdefault("backoff", 0)
    return Client("plasmodb", transport=httpx.MockTransport(handler), **kw)


def test_auth_is_a_single_cookie_pair():
    seen = {}

    def handler(request):
        seen["cookie"] = request.headers.get("cookie")
        seen["auth_header"] = request.headers.get("authorization")
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert seen["cookie"] == "Authorization=tok-x"
    assert seen["auth_header"] is None


def test_retries_5xx_then_succeeds():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        if n["v"] < 3:
            return httpx.Response(502, text="bad gateway")
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert n["v"] == 3


def test_delayed_result_body_is_retried():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        if n["v"] == 1:
            return httpx.Response(
                200, json={"status": "accepted", "message": "WDK-DELAYED-RESULT"}
            )
        return httpx.Response(200, json={"ok": True})

    assert _client(handler).get("/x") == {"ok": True}
    assert n["v"] == 2


def test_non_idempotent_post_gets_one_attempt():
    from _client import WDKError

    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        return httpx.Response(502, text="proxy hiccup")

    with pytest.raises(WDKError):
        _client(handler).post("/users/1/steps", {"a": 1}, idempotent=False)
    assert n["v"] == 1


def test_4xx_raises_with_body_and_no_retry():
    from _client import WDKError

    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        return httpx.Response(422, text="value 'x' is not in vocabulary")

    with pytest.raises(WDKError) as e:
        _client(handler).get("/x")
    assert n["v"] == 1
    assert e.value.status == 422
    assert "vocabulary" in str(e.value)


def test_user_id_resolves_and_caches():
    n = {"v": 0}

    def handler(request):
        n["v"] += 1
        assert request.url.path.endswith("/users/current")
        return httpx.Response(200, json={"id": 12345, "isGuest": False, "email": "x@y"})

    c = _client(handler)
    assert c.user_id() == 12345
    assert c.user_id() == 12345
    assert n["v"] == 1


def test_guest_token_is_refused():
    from _client import GuestTokenError

    def handler(request):
        return httpx.Response(200, json={"id": 99, "isGuest": True})

    with pytest.raises(GuestTokenError) as e:
        _client(handler).user_id()
    assert "register" in str(e.value).lower()


def test_load_token_env_then_dotenv(tmp_path, monkeypatch):
    from _client import load_token

    monkeypatch.setenv("VEUPATHDB_BEARER_TOKEN", "from-env")
    assert load_token(root=tmp_path) == "from-env"
    monkeypatch.delenv("VEUPATHDB_BEARER_TOKEN")
    (tmp_path / ".env").write_text('VEUPATHDB_BEARER_TOKEN="from-file"\n')
    assert load_token(root=tmp_path) == "from-file"
    assert load_token(root=tmp_path / "nowhere") is None


def test_live_whoami(live_client):
    me = live_client.get("/users/current")
    assert me["isGuest"] is False
    assert isinstance(me["id"], int)


@pytest.mark.parametrize("site", ["plasmodb", "vectorbase", "toxodb"])
def test_live_whoami_all_test_sites(site, token):
    from _client import Client

    me = Client(site, token=token).get("/users/current")
    assert me["isGuest"] is False
