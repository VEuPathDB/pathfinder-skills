import pytest

MW = "GenesByMolecularWeight"
PF = ["Plasmodium falciparum 3D7"]


def _leaf(minw, maxw):
    return {
        "leaf": {
            "search": MW,
            "params": {
                "organism": PF,
                "min_molecular_weight": str(minw),
                "max_molecular_weight": str(maxw),
            },
        }
    }


def test_validate_spec_shapes():
    from _strategy import SpecError, validate_spec

    assert validate_spec(_leaf(1, 2)) == MW
    combined = {"combine": {"operator": "INTERSECT", "left": _leaf(1, 2), "right": _leaf(2, 3)}}
    assert validate_spec(combined) == MW
    with pytest.raises(SpecError):
        validate_spec({"combine": {"operator": "XOR", "left": _leaf(1, 2), "right": _leaf(2, 3)}})
    with pytest.raises(SpecError):
        validate_spec({"leaf": {"params": {}}})
    with pytest.raises(SpecError):
        validate_spec({"leaf": {}, "combine": {}})


@pytest.fixture
def strategy_tracker(live_client):
    created = []
    yield created
    uid = live_client.user_id()
    for sid in created:
        try:
            live_client.delete(f"/users/{uid}/strategies/{sid}")
        except Exception:
            pass  # 404 etc.: already gone


def test_live_two_leaf_intersect(live_client, strategy_tracker):
    from _client import fetch_catalog
    from _strategy import build_strategy

    spec = {
        "combine": {
            "operator": "INTERSECT",
            "left": _leaf(10000, 50000),
            "right": _leaf(40000, 100000),
        }
    }
    cat = fetch_catalog(live_client)
    out = build_strategy(live_client, cat, spec, "__skill_test__: intersect mw")
    strategy_tracker.append(out["strategy_id"])
    assert out["url"].endswith(f"/app/workspace/strategies/{out['strategy_id']}")
    assert len(out["steps"]) == 3
    root = out["estimated_size"]
    leaf_counts = [s["count"] for s in out["steps"] if s["search"] == MW]
    assert all(isinstance(c, int) for c in leaf_counts)
    assert isinstance(root, int)
    assert root <= min(leaf_counts)  # intersect can't exceed either input
    assert root > 0  # 40k-50k overlap is non-empty
