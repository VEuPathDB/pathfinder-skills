"""VEuPathDB site registry. base_url IS the WDK REST service root."""


class UnknownSiteError(KeyError):
    pass


def _s(base_url: str, project_id: str, timeout: int = 30) -> dict:
    return {"base_url": base_url, "project_id": project_id, "timeout": timeout}


SITES: dict[str, dict] = {
    "veupathdb": _s("https://veupathdb.org/veupathdb/service", "EuPathDB", 120),
    "amoebadb": _s("https://amoebadb.org/amoeba/service", "AmoebaDB"),
    "cryptodb": _s("https://cryptodb.org/cryptodb/service", "CryptoDB"),
    "fungidb": _s("https://fungidb.org/fungidb/service", "FungiDB"),
    "giardiadb": _s("https://giardiadb.org/giardiadb/service", "GiardiaDB"),
    "hostdb": _s("https://hostdb.org/hostdb/service", "HostDB"),
    "microsporidiadb": _s("https://microsporidiadb.org/micro/service", "MicrosporidiaDB"),
    "orthomcl": _s("https://orthomcl.org/orthomcl/service", "OrthoMCL"),
    "piroplasmadb": _s("https://piroplasmadb.org/piro/service", "PiroplasmaDB"),
    "plasmodb": _s("https://plasmodb.org/plasmo/service", "PlasmoDB"),
    "toxodb": _s("https://toxodb.org/toxo/service", "ToxoDB"),
    "trichdb": _s("https://trichdb.org/trichdb/service", "TrichDB"),
    "tritrypdb": _s("https://tritrypdb.org/tritrypdb/service", "TriTrypDB"),
    "vectorbase": _s("https://vectorbase.org/vectorbase/service", "VectorBase"),
}


def _site(site_id: str) -> dict:
    try:
        return SITES[site_id]
    except KeyError:
        raise UnknownSiteError(
            f"unknown site '{site_id}'; valid: {', '.join(sorted(SITES))}"
        ) from None


def service_url(site_id: str) -> str:
    return _site(site_id)["base_url"]


def web_base_url(site_id: str) -> str:
    return _site(site_id)["base_url"].removesuffix("/service")


def strategy_url(site_id: str, strategy_id, step_id=None) -> str:
    url = f"{web_base_url(site_id)}/app/workspace/strategies/{strategy_id}"
    return f"{url}/{step_id}" if step_id is not None else url
