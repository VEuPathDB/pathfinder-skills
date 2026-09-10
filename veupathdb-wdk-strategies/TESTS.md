# Gold-standard test registry

Gold standards captured live on 2026-08-27. Counts drift with VEuPathDB data releases (~4/year): a `range` failure within ~20% of gold means re-capture, not code bug. Any other failure is a regression.

Live services drift with data releases; each case states its tolerance:
`exact` | `range` (± stated) | `fields-present`.
Run all: `uv run --with pytest --with httpx python -m pytest tests -q`

| ID | Command / pytest node | Expectation | Tolerance | Gold (captured) | Date |
|---|---|---|---|---|---|
| AUTH-1 | `wdk.py whoami plasmodb` / test_client.py::test_live_whoami | numeric user_id, not guest | fields-present | user_id=578013513 | 2026-08-27 |
| AUTH-2 | test_client.py::test_guest_token_is_refused | guest refusal names registration | exact (offline) | message contains "register" | 2026-08-27 |
| CAT-1 | `wdk.py record-types plasmodb` | contains transcript, organism, dataset | fields-present | 24 record types | 2026-08-27 |
| CAT-2 | `wdk.py catalog plasmodb` | header + one TSV line per non-boolean search | range ±20% | 495 lines | 2026-08-27 |
| CAT-3 | `wdk.py catalog vectorbase` | as CAT-2 | range ±20% | 995 lines | 2026-08-27 |
| CAT-4 | `wdk.py catalog toxodb` | as CAT-2 | range ±20% | 385 lines | 2026-08-27 |
| FIND-1 | `wdk.py find-searches plasmodb "GO term"` | GenesByGoTerm in top 5 | fields-present | rank=1 | 2026-08-27 |
| INS-1 | `wdk.py inspect plasmodb GenesByMolecularWeight` | 3 visible params; organism tree; min default 10000 | exact (offline fixture) | see tests/fixtures/mw.json | 2026-08-27 |
| INS-2 | `wdk.py inspect plasmodb GenesByGoTerm --query kinase` | go_typeahead shortlisted with note (5992 total) | range: total >5000 | 5992 | 2026-08-27 |
| INS-3 | `wdk.py inspect plasmodb GenesByMolecularWieght` | did-you-mean GenesByMolecularWeight, exit 1 | exact | — | 2026-08-27 |
| OPT-1 | `wdk.py param-options plasmodb GenesByGoTerm go_typeahead --query kinase` | filtered options + context_note naming go_term_slim | fields-present | shown=155 | 2026-08-27 |
| OPT-2 | `wdk.py param-options plasmodb GenesByGoTerm go_typahead` | did_you_mean includes go_typeahead | exact | — | 2026-08-27 |
| CNT-1 | `wdk.py count plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium falciparum 3D7"]}'` | 2365 genes | range 1800–3000 | 2365 | 2026-08-27 |
| CNT-2 | `wdk.py count plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium"]}'` | > CNT-1 count | range | 157941 | 2026-08-27 |
| PRV-1 | `wdk.py preview plasmodb GenesByMolecularWeight --params '{"organism": ["Plasmodium falciparum 3D7"]}' --limit 3` | 3 records with gene_source_id ids | fields-present | first id PF3D7_0100200 | 2026-08-27 |
| STR-1 | test_strategy.py::test_live_two_leaf_intersect / `wdk.py create-strategy plasmodb --spec '{"combine": {"operator": "INTERSECT", "left": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": "10000", "max_molecular_weight": "50000"}}}, "right": {"leaf": {"search": "GenesByMolecularWeight", "params": {"organism": ["Plasmodium falciparum 3D7"], "min_molecular_weight": "40000", "max_molecular_weight": "100000"}}}}}'` | 3 steps; root ≤ min(leaves); root > 0; url valid | range | root=521, leaves=[2365, 1842] | 2026-08-27 |
| STR-2 | `wdk.py strategy plasmodb <strategy_id>` | same shape as create output | fields-present | — | 2026-08-27 |
| STR-3 | `wdk.py delete-strategy plasmodb <strategy_id>` (without `--yes`) | refuses without `--yes`, exit 1 | exact | error: refusing to delete without --yes | 2026-08-27 |
| CNT-3 | `wdk.py count vectorbase GenesByMolecularWeight --params '{"organism": ["Anopheles gambiae PEST"]}'` / test_reports.py::test_live_count_vectorbase | >0, within range | range ±20% of gold | 6755 | 2026-08-27 |
| RES-1 | `wdk.py results plasmodb --step <step_id> --limit 2` / test_results.py::test_live_step_records | 2 records with gene ids | fields-present | — | 2026-08-27 |
| DL-1 | `wdk.py download-url plasmodb --step <step_id>` / test_results.py::test_live_download_url | URL containing /temporary-results/ | fields-present | report=attributesTabular | 2026-08-27 |
| E2E-1 | VectorBase MW intersect (10–50k ∩ 40–100k) Anopheles gambiae PEST | full lifecycle: catalog → inspect → count → create → results → delete | exact url | https://vectorbase.org/vectorbase/app/workspace/strategies/330622833 | 2026-08-27 |
