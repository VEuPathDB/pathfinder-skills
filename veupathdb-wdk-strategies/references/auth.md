# Authentication and transport

## Getting and managing credentials

Authentication requires a registered VEuPathDB account. Tokens are stored
globally in `~/.config/veupathdb/token` with strict `0600` permissions (or
provided via the `VEUPATHDB_BEARER_TOKEN` environment variable). Because
VEuPathDB uses single sign-on across all 14 sites, a token obtained on any site
works on all of them.

### Option 1: Direct login with email and password
Run the login wizard:

    uv run scripts/wdk.py login [site]

Or non-interactively:

    uv run scripts/wdk.py login [site] --email user@example.org --password mypass

This authenticates directly against VEuPathDB's `/login` service, retrieves the
long-lived (3-year) bearer token, and stores it in `~/.config/veupathdb/token`.

### Option 2: Browser API key (no password shared with agent)
For users who prefer not to enter their account password into a terminal/agent:
1. Log in to any VEuPathDB website (e.g. `https://plasmodb.org` or `https://toxodb.org`).
2. Go to the user menu (top right) → **My Account** → **Service Access** tab
   (e.g. `https://plasmodb.org/plasmo/app/user/profile#serviceAccess`).
3. Copy the personal API key and pass it to:

       uv run scripts/wdk.py login [site] --token <PASTED_KEY>

### Unregistered users
If the user does not have an account, direct them to register for free:
`https://veupathdb.org/veupathdb/app/user/registration` (or the component site's
registration page). After registration, they can log in via Option 1 or Option 2.

### Community / Site Detection
To identify which community website a user's prompt pertains to:

    uv run scripts/wdk.py detect-site "Toxoplasma gondii rhoptry kinases"

This detects the target site (e.g. `toxodb`, `vectorbase`, `plasmodb`) and
outputs the community-specific profile and registration URLs, falling back to
the unified portal `veupathdb` (`veupathdb.org`).

### Logging out
To delete the stored token:

    uv run scripts/wdk.py logout

## How auth actually works (distilled from pathfinder's WDK rules)

- The token travels as both a COOKIE: `Cookie: Authorization=<token>` (honored
  by Tomcat for `/users/…` strategy paths) and an `Authorization: Bearer <token>`
  header (required by `POST /record-types/…/records`). Tomcat honors the FIRST
  cookie pair if duplicates are sent — the client sends exactly one cookie pair.
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
