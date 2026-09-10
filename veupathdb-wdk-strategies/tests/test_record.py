import pytest

from _client import Client, load_token
from _sites import project_id


@pytest.fixture(scope="module")
def token():
    tok = load_token()
    if not tok:
        pytest.skip("VEUPATHDB_BEARER_TOKEN not set")
    return tok


def test_live_fetch_gene_record_vectorbase(token):
    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "AGAP001212"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "name", "product", "exon_count"],
        "tables": ["GeneTranscripts"],
    }
    data = c.post("/record-types/gene/records", payload, idempotent=True)
    assert data["attributes"]["name"] == "PGRPLB"
    assert data["attributes"]["exon_count"] == "3"
    transcripts = data["tables"]["GeneTranscripts"]
    assert len(transcripts) >= 1
    assert transcripts[0]["exon_count"] == "3"
    assert transcripts[0]["transcript_id"] == "AGAP001212-RA"


def test_live_fetch_gene_record_plasmodb(token):
    c = Client("plasmodb", token=token)
    payload = {
        "primaryKey": [
            {"name": "source_id", "value": "PF3D7_0100200"},
            {"name": "project_id", "value": project_id("plasmodb")},
        ],
        "attributes": ["primary_key", "name", "product", "exon_count"],
        "tables": ["GeneTranscripts"],
    }
    data = c.post("/record-types/gene/records", payload, idempotent=True)
    assert data["attributes"]["primary_key"] == "PF3D7_0100200"
    assert data["attributes"]["exon_count"] == "2"


def test_live_fetch_transcript_record(token):
    c = Client("vectorbase", token=token)
    payload = {
        "primaryKey": [
            {"name": "gene_source_id", "value": "AGAP001212"},
            {"name": "source_id", "value": "AGAP001212-RA"},
            {"name": "project_id", "value": project_id("vectorbase")},
        ],
        "attributes": ["primary_key", "exon_count"],
        "tables": [],
    }
    data = c.post("/record-types/transcript/records", payload, idempotent=True)
    assert data["attributes"]["exon_count"] == "3"
