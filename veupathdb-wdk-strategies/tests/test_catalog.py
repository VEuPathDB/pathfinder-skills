import json


def test_strip_html():
    from _shaping import strip_html

    assert (
        strip_html("Find genes <br><br> with  <i>weight</i>\n in a range")
        == "Find genes with weight in a range"
    )


def test_catalog_lines_shape_and_boolean_filter():
    from _shaping import catalog_lines

    cat = {
        "record_types": ["transcript"],
        "searches": {
            "transcript": [
                {
                    "name": "GenesByTaxon",
                    "displayName": "Taxonomy",
                    "description": "<b>Find</b> genes " + "x" * 400,
                    "paramNames": ["organism"],
                    "outputRecordClassName": "transcript",
                },
                {
                    "name": "boolean_question_X",
                    "displayName": "bool",
                    "description": "",
                    "paramNames": [],
                    "outputRecordClassName": "transcript",
                },
            ]
        },
    }
    lines = catalog_lines(cat)
    assert len(lines) == 1
    rt, name, disp, desc = lines[0].split("\t")
    assert (rt, name, disp) == ("transcript", "GenesByTaxon", "Taxonomy")
    assert len(desc) <= 250 and desc.startswith("Find genes")


def test_live_catalog_plasmodb(live_client):
    from _client import fetch_catalog
    from _shaping import all_search_names, catalog_lines

    cat = fetch_catalog(live_client)
    assert "transcript" in cat["record_types"]
    names = all_search_names(cat)
    assert names.get("GenesByGoTerm") == "transcript"
    assert names.get("GenesByMolecularWeight") == "transcript"
    assert len(catalog_lines(cat)) > 400  # 515 searches incl. non-gene types, minus booleans

    # second call must come from disk cache (no HTTP): break the token
    from _client import Client

    broken = Client("plasmodb", token="invalid")
    cached = fetch_catalog(broken)
    assert cached["record_types"] == cat["record_types"]
