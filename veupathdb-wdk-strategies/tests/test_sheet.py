import json
import pathlib

FX = pathlib.Path(__file__).parent / "fixtures"


def _mw():
    return json.loads((FX / "mw.json").read_text())


def _go():
    return json.loads((FX / "go.json").read_text())


def test_tree_entries_skips_fake_root():
    from _shaping import tree_entries

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    entries = tree_entries(organism["vocabulary"])
    terms = [e["term"] for e in entries]
    assert "@@fake@@" not in terms
    assert "Plasmodium falciparum 3D7" in terms
    leaf = next(e for e in entries if e["term"] == "Plasmodium falciparum 3D7")
    assert leaf["leaf"] is True


def test_expand_to_leaves_parent_and_leaf_and_unknown():
    from _shaping import expand_to_leaves

    organism = next(p for p in _mw()["parameters"] if p["name"] == "organism")
    tree = organism["vocabulary"]
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D7"])
    assert leaves == ["Plasmodium falciparum 3D7"] and unknown == []
    leaves, unknown = expand_to_leaves(tree, ["Plasmodium"])
    assert len(leaves) > 5 and all("Plasmodium" in x for x in leaves[:3])
    _, unknown = expand_to_leaves(tree, ["Plasmodium falciparum 3D8"])
    assert unknown == ["Plasmodium falciparum 3D8"]


def test_sheet_mw():
    from _shaping import build_sheet

    sheet = build_sheet(_mw())
    assert sheet["search"] == "GenesByMolecularWeight"
    names = [e["name"] for e in sheet["required"] + sheet["optional"]]
    assert set(names) == {"organism", "min_molecular_weight", "max_molecular_weight"}
    org = next(e for e in sheet["required"] if e["name"] == "organism")
    assert "vocabulary_tree" in org
    assert len(org["vocabulary_tree"]) <= 80
    assert "children" in org["note"]
    assert sheet["params_template"]["min_molecular_weight"] == "10000"


def test_sheet_shortlists_huge_flat_vocab():
    from _shaping import build_sheet

    sheet = build_sheet(_go(), query="kinase")
    ta = next(
        e for e in sheet["required"] + sheet["optional"] if e["name"] == "go_typeahead"
    )
    assert len(ta["allowed_values"]) <= 200
    assert "values total" in ta["note"]
    assert "param-options" in ta["note"]


def test_sheet_dependencies_name_visible_dependents():
    from _shaping import build_sheet

    deps = build_sheet(_go())["dependencies"]
    assert any("go_term_slim" in d and "go_typeahead" in d for d in deps)


def test_resolve_search_did_you_mean(live_client):
    from _client import fetch_catalog
    from _shaping import resolve_search

    cat = fetch_catalog(live_client)
    rt, _ = resolve_search(cat, "GenesByMolecularWeight")
    assert rt == "transcript"
    rt, sugg = resolve_search(cat, "GenesByMolecularWieght")
    assert rt is None and "GenesByMolecularWeight" in sugg
