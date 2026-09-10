import pytest


def test_all_14_sites_present():
    from _sites import SITES
    assert len(SITES) == 14
    for sid in ("plasmodb", "vectorbase", "toxodb", "veupathdb", "orthomcl"):
        assert sid in SITES


def test_service_and_web_urls():
    from _sites import service_url, strategy_url, web_base_url
    assert service_url("plasmodb") == "https://plasmodb.org/plasmo/service"
    assert web_base_url("plasmodb") == "https://plasmodb.org/plasmo"
    assert (strategy_url("plasmodb", 123)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123")
    assert (strategy_url("plasmodb", 123, 456)
            == "https://plasmodb.org/plasmo/app/workspace/strategies/123/456")


def test_unknown_site_lists_valid_ids():
    from _sites import UnknownSiteError, service_url
    with pytest.raises(UnknownSiteError) as e:
        service_url("nope")
    assert "plasmodb" in str(e.value)


def test_portal_timeout_is_120():
    from _sites import SITES
    assert SITES["veupathdb"]["timeout"] == 120
    assert SITES["plasmodb"]["timeout"] == 30
