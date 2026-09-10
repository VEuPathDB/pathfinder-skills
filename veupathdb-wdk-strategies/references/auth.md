# Authentication and transport

## Getting a token

Register at the target site (e.g. plasmodb.org → Register). A logged-in
browser holds the token in the `Authorization` cookie; the profile page's
"Service Access" section describes API-key access. Put it in the environment
as `VEUPATHDB_BEARER_TOKEN` or in `.env` at the repo root (gitignored).

## How auth actually works (distilled from pathfinder's WDK rules)

- The token travels as a COOKIE: `Cookie: Authorization=<token>`. Never as an
  `Authorization:` header. Tomcat honors the FIRST cookie pair if duplicates
  are sent — the client here sends exactly one.
- An uncredentialed request is NOT rejected: WDK mints a fresh guest user per
  request. Guests get 401s on `/users/…` programmatic paths (VEuPathDB policy
  since 2026-08-19) and results that silently belong to nobody. Always verify
  with `whoami` first; the client refuses guest tokens for user-scoped calls.
- `GET /users/current` → `{"id": <int>, "isGuest": bool, "email": …}`. The
  client resolves the numeric id ONCE and uses it in every `/users/{uid}/…`
  path (the `current` alias is only ever used for that one resolution call —
  concrete ids make ownership errors loud 403s instead of silent misfires).
- Logout does NOT invalidate a bearer token; treat tokens as long-lived
  secrets. Never print or commit them.

## Transport quirks the client handles for you

- Retries ×3 (exponential backoff) on timeouts, connect errors, 5xx.
- A 2xx body of `{"status": "accepted", "message": "WDK-DELAYED-RESULT"}` means
  "result not ready" and is retried like a failure.
- Step/strategy/temporary-result CREATION is never retried (a proxy 502 after
  a committed create would otherwise duplicate objects).
- 422 = well-formed request, semantically invalid values; the WDK message is
  surfaced verbatim — read it, it names the offending parameter.
- Timeouts: 30 s per site; 120 s for the veupathdb.org portal.
