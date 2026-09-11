---
name: veupathdb-wdk-strategies
description: Build, run, and manage search strategies on VEuPathDB sites (PlasmoDB, VectorBase, ToxoDB, FungiDB, TriTrypDB, etc.) via the WDK REST API. Use when the user wants to find genes/records by biological criteria on a VEuPathDB site, combine searches (intersect/union/minus), count or preview results, or fetch/download result records.
---

# VEuPathDB WDK search strategies

All commands: `uv run scripts/wdk.py <subcommand> ...` (run from this skill's
directory). Machine-readable JSON on stdout; errors on stderr with exit 1.
`--help` on any subcommand. Supply-chain note: uv installs are expected to be
date-pinned via `exclude-newer` in `~/.config/uv/uv.toml`.

## Auth & User Onboarding (required for nearly everything)

All WDK programmatic endpoints require authentication with a registered VEuPathDB account.
Tokens are stored globally at `~/.config/veupathdb/token` (mode 0600) or via the
`VEUPATHDB_BEARER_TOKEN` env var. Unauthenticated requests silently mint guests,
which are rejected with 401 errors.

Verify authentication first:

    uv run scripts/wdk.py whoami plasmodb

### Guiding unauthenticated or unregistered users

When starting a session or whenever `whoami` fails, guide the user through onboarding:

1. **Detect the community site** from the user's research question:
   ```bash
   uv run scripts/wdk.py detect-site "User's research question or organism"
   ```
   This returns the site ID (e.g. `plasmodb`, `toxodb`, `vectorbase`), along with the
   community-specific `profile_url` and `registration_url`.

2. **Guide the user based on their account status**:
   - **For UNREGISTERED users (no account yet)**:
     - Direct them to the community registration page: `<registration_url>` (e.g. `https://plasmodb.org/plasmo/app/user/registration`).
     - Explain that registration is **free**, takes **under 1 minute**, requires no waiting period, and provides **Single Sign-On across all 14 VEuPathDB sites**.
     - Ask them to return once registered to complete login.
   - **For REGISTERED users (already have an account)**:
     - Offer the choice of two login methods:
       - **Method 1 (Direct login)**: The user provides their VEuPathDB account email and password, then run:
         ```bash
         uv run scripts/wdk.py login <site> --email <EMAIL> --password <PASSWORD>
         ```
       - **Method 2 (Browser API key — no password shared with assistant)**:
         If the user prefers not to share credentials, direct them to open `<profile_url>` in their browser (User icon in top header → **My Account** → **Service Access** tab), copy their API key, and provide it or run:
         ```bash
         uv run scripts/wdk.py login <site> --token <PASTED_KEY>
         ```
   - **Interactive CLI wizard**: The user can also run the interactive wizard in their terminal:
     ```bash
     uv run scripts/wdk.py login [site]
     ```

3. **Verify**:
   ```bash
   uv run scripts/wdk.py whoami <site>
   ```

To log out and remove the stored token: `uv run scripts/wdk.py logout`.
Full details and technical background: references/auth.md

## Resolving gene symbols & names (don't web-search or use external APIs first!)

When asked about a gene by symbol, name, or product (e.g. `SRPN2`, `K13`):
- **Do NOT reach for WebSearch or external APIs (NCBI, Ensembl, etc.)** to look
  up accession IDs (`AGAP...`, `PF3D7_...`) or to "cross-check" annotations.
  VEuPathDB is the primary authority for these genomes; external resources
  frequently use different gene models, ortholog mappings, or obsolete builds.
- **Resolve with `GenesByText` preview first**:
  ```bash
  uv run scripts/wdk.py preview SITE GenesByText \
    --params '{"text_expression": "SYMBOL", "text_search_organism": ["Organism"], "text_fields": ["name", "Alias"]}' \
    --attributes primary_key,gene_name,gene_product
  ```
  - **`text_search_organism` is MANDATORY**: WDK has no default organism for `GenesByText` and rejects empty selections. Always specify the organism or species complex (e.g. `["Anopheles gambiae"]`, `["Plasmodium falciparum 3D7"]`). Tree parents auto-expand to all member strains.
  - To look up the exact organism name: `uv run scripts/wdk.py param-options SITE GenesByText text_search_organism --filter "organism"`
  - Matching symbols specifically: use `"text_fields": ["name", "Alias"]` (as shown above).
- **When is WebSearch acceptable?** ONLY as a fallback if VEuPathDB text search
  returns 0 hits, specifically to discover published nomenclature/hyphenation
  variants (e.g. `SRPN-2` vs `SRPN2`) or synonym aliases. Once a synonym is
  found, return to `GenesByText` or `fetch-record` inside VEuPathDB.

## The workflow

1. **Check auth & pick the site**: Verify with `whoami`. If unauthenticated, follow the onboarding flow above (`detect-site`, guide registration or login). Otherwise resolve the site with `detect-site "QUERY"` or list all 14 with `sites`.
2. **Discover searches** — dispatch a SUB-AGENT (keeps your context clean):
   its prompt = the research goal + "run `uv run scripts/wdk.py catalog SITE`,
   read every line, return 3–8 candidate searches (name, record type, why),
   tagged seed/filter/transform". The dump is ~25–75k tokens. No sub-agents
   available? Read the dump yourself. `find-searches SITE QUERY` is a quick
   lexical fallback when you already know roughly the name.
3. **Inspect each candidate**: `inspect-search SITE SEARCH [--query HINT]` returns the
   parameter sheet: required/optional params, defaults, vocabularies
   (truncated over 200 — fetch more with `param-options`), dependency notes,
   and `params_template` (copy it, fill values, null = use default).
   Copy vocabulary values EXACTLY. A tree parent term selects all its children.
4. **Dry-run cheaply** (no writes, parallelizable): `count SITE SEARCH --params
   JSON`, then `preview` to sanity-check actual records. A count of 0 usually
   means a wrong vocabulary value or an over-narrow AND — see
   references/gotchas.md before blaming the site.
5. **Create the strategy**: `create-strategy SITE --spec JSON --name "..."`.
   Spec nodes: {"leaf": {search, params}}, {"combine": {operator, left,
   right}} (UNION|INTERSECT|MINUS|RMINUS|LONLY|RONLY), {"transform": {search,
   params, input}}. Returns strategy id, per-step counts, and the website URL —
   give that URL to the user. Combine semantics: alternative evidence for the
   SAME property → UNION; distinct required properties → INTERSECT; nest
   multi-evidence branches (A ∩ (B ∪ C) ≠ (A ∩ B) ∪ C).
6. **Fetch results & records**: `results SITE --step ID`, `download-url SITE --step ID`.
   Discover schema: `inspect-record-type SITE RT [--filter Q]` (PK, attributes, tables).
   Inspect record/tables: `fetch-record SITE ID [--tables TBLS] [--filter TEXT]`.
   Manage: `strategy`, `list-strategies`, `delete-strategy ... --yes`.

## Subcommands

| cmd | purpose |
|---|---|
| sites | list site ids and service URLs |
| whoami SITE | verify token, print numeric user id |
| login [SITE] [--token K] [--email E --password P] | authenticate and store token in ~/.config/veupathdb/token |
| logout | remove stored token from ~/.config/veupathdb/token |
| detect-site QUERY | detect VEuPathDB site and URLs from query text |
| record-types SITE | list record type segments |
| inspect-record-type SITE RT [--filter Q] [--name-only] [--exclude P] | record schema: PK, attributes, tables |
| searches SITE RT | searches for one record type (TSV) |
| catalog SITE [--record-type RT] [--refresh] | full compact catalog (TSV) — discovery input |
| find-searches SITE QUERY | lexical convenience lookup |
| inspect-search SITE SEARCH [--filter HINT] | parameter sheet (alias: inspect) |
| param-options SITE SEARCH PARAM [--filter Q] [--context P=V] | browse a vocabulary |
| count SITE SEARCH --params JSON | count without creating anything |
| preview SITE SEARCH --params JSON [--limit N] [--attributes A] | sample records with search's default attributes (or custom) |
| create-strategy SITE --spec JSON [--name S] | steps + strategy, returns URL |
| strategy SITE ID / list-strategies SITE | read back |
| delete-strategy SITE ID --yes | destructive |
| results SITE --step ID [--limit N] [--attributes A] | records for a step (defaults to search's standard attributes) |
| download-url SITE --step ID | temporary download URL |
| fetch-record SITE [ID] [--tables T] [--filter F] | record details/tables with row filtering |

## Top gotchas (full list: references/gotchas.md)

- **Vocabulary values are exact strings.** Never paraphrase; copy from the
  sheet or `param-options`. Wrong values are caught locally with suggestions.
- **Tree parents are auto-expanded to leaves** on submit (WDK would silently
  return 0 rows otherwise). Selecting "Plasmodium" means all its leaf genomes.
- **Multi-evidence needs enumeration**: a multi-pick param must list EVERY
  covered value, never one representative.
- **Defaults are disclosed**: params you leave null use the search default
  (shown in the sheet) — tell the user which defaults applied.
- **Resolve symbols via `GenesByText`, not WebSearch or external APIs (NCBI, Ensembl).**
  VEuPathDB is the primary authority for these genome annotations; external
  databases often use different coordinate systems or outdated gene builds.
- **Differential expression (EDA) searches are excluded**: Searches with `eda_` params
  require interactive web-app analysis and are hidden from `catalog`/`find-searches`.
- **`inspect-record-type` and Protocol Application Nodes (`pan_`)**: Transcript records
  contain thousands of legacy GUS Protocol Application Node columns (`pan_<id>_ns_<id>`)
  and web graph widgets (`_expr_graph`). When querying schema, use `--name-only` to filter
  specifically on attribute names (avoiding false positives from long descriptions) or
  `--exclude pan_` / `--exclude "pan_,graph"` to suppress them.
- **Automatic default attributes for `preview` and `results`**: When `--attributes` is
  omitted, both `preview` and `results` dynamically look up and return the search's
  standard default columns (`defaultAttributes`, e.g. `gene_product`, `organism`,
  `primary_key`), exactly matching the website results table. Specify `--attributes` only
  when requesting custom non-default attributes.

## Deeper reference (read on demand)

- references/auth.md — token acquisition, cookie transport, guest refusal
- references/parameters.md — the 11 param types, dependent vocabularies
- references/strategies.md — stepTree semantics, spec format, step kinds
- references/gotchas.md — every known silent-failure mode

Out of scope (v1): semantic search, site-search, control tests, enrichment,
step analyses, filters, phyletic profile patterns, dataset/basket uploads, EDA.
Tests + gold standards: TESTS.md.
