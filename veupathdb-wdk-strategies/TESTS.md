# Gold-standard test registry

Live services drift with data releases; each case states its tolerance:
`exact` | `range` (± stated) | `fields-present`.
Run all: `uv run --with pytest --with httpx python -m pytest tests -q`

| ID | Command / pytest node | Expectation | Tolerance | Gold (captured) | Date |
|---|---|---|---|---|---|
| AUTH-1 | `wdk.py whoami plasmodb` / test_client.py::test_live_whoami | numeric user_id, not guest | fields-present | user_id=578013513 | 2026-08-27 |
| AUTH-2 | test_client.py::test_guest_token_is_refused | guest refusal names registration | exact (offline) | message contains "register" | 2026-08-27 |
