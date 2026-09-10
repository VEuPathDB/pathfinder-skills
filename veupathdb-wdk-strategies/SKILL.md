---
name: veupathdb-wdk-strategies
description: Build, run, and manage search strategies on VEuPathDB sites (PlasmoDB, VectorBase, ToxoDB, FungiDB, TriTrypDB, etc.) via the WDK REST API. Use when the user wants to find genes/records by biological criteria on a VEuPathDB site, combine searches (intersect/union/minus), count or preview results, or fetch/download result records.
---

# VEuPathDB WDK search strategies

All commands: `uv run scripts/wdk.py <subcommand> ...` (run from this skill's
directory). Machine-readable JSON on stdout; errors on stderr with exit 1.
`--help` on any subcommand. Supply-chain note: uv installs are expected to be
date-pinned via `exclude-newer` in `~/.config/uv/uv.toml`.

## Auth (required for nearly everything)

`VEUPATHDB_BEARER_TOKEN` env var, or `.env` at the repo root. Must be a
REGISTERED user's token — WDK silently mints guests otherwise. Verify first:

    uv run scripts/wdk.py whoami plasmodb

Details and how to obtain a token: references/auth.md

## The workflow

1. **Pick the site**: `sites` lists all 14 (plasmodb, vectorbase, toxodb, …).
2. **Discover searches** — dispatch a SUB-AGENT (keeps your context clean):
   its prompt = the research goal + "run `uv run scripts/wdk.py catalog SITE`,
   read every line, return 3–8 candidate searches (name, record type, why),
   tagged seed/filter/transform". The dump is ~25–75k tokens. No sub-agents
   available? Read the dump yourself. `find-searches SITE QUERY` is a quick
   lexical fallback when you already know roughly the name.
3. **Inspect each candidate**: `inspect SITE SEARCH [--query HINT]` returns the
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
   To inspect an individual gene or record: `fetch-record SITE ID [--tables TBLS]`.
   Manage: `strategy`, `list-strategies`, `delete-strategy ... --yes`.

## Subcommands

| cmd | purpose |
|---|---|
| sites | list site ids and service URLs |
| whoami SITE | verify token, print numeric user id |
| record-types SITE | list record type segments |
| searches SITE RT | searches for one record type (TSV) |
| catalog SITE [--record-type RT] [--refresh] | full compact catalog (TSV) — discovery input |
| find-searches SITE QUERY | lexical convenience lookup |
| inspect SITE SEARCH [--query HINT] | shaped parameter sheet |
| param-options SITE SEARCH PARAM [--query Q] [--context P=V] | browse a vocabulary |
| count SITE SEARCH --params JSON | count without creating anything |
| preview SITE SEARCH --params JSON [--limit N] | sample records, no writes |
| create-strategy SITE --spec JSON [--name S] | steps + strategy, returns URL |
| strategy SITE ID / list-strategies SITE | read back |
| delete-strategy SITE ID --yes | destructive |
| results SITE --step ID | records for a step |
| download-url SITE --step ID | temporary download URL |
| fetch-record SITE [ID] [--tables T] | single record details/tables (e.g. GeneTranscripts) |

## Top gotchas (full list: references/gotchas.md)

- **Vocabulary values are exact strings.** Never paraphrase; copy from the
  sheet or `param-options`. Wrong values are caught locally with suggestions.
- **Tree parents are auto-expanded to leaves** on submit (WDK would silently
  return 0 rows otherwise). Selecting "Plasmodium" means all its leaf genomes.
- **Multi-evidence needs enumeration**: a multi-pick param must list EVERY
  covered value, never one representative.
- **Defaults are disclosed**: params you leave null use the search default
  (shown in the sheet) — tell the user which defaults applied.

## Deeper reference (read on demand)

- references/auth.md — token acquisition, cookie transport, guest refusal
- references/parameters.md — the 11 param types, dependent vocabularies
- references/strategies.md — stepTree semantics, spec format, step kinds
- references/gotchas.md — every known silent-failure mode

Out of scope (v1): semantic search, site-search, control tests, enrichment,
step analyses, filters, phyletic profile patterns, dataset/basket uploads, EDA.
Tests + gold standards: TESTS.md.
