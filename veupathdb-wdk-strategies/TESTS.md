# Gold-standard test registry

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
