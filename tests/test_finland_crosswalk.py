"""Unit tests for the Finnish kunta/maakunta -> NUTS 2024 crosswalk builder (Increment 7).

The build is driven with an injected ``get``/``sleep`` so the gate stays offline.
Covers the GISCO level-3 filter, the level-3 selection inside Statistics
Finland's NUTS 1-3 key, the zero-padded code folding shared with the collector,
the derived-and-verified maakunta layer (including the ``maakunta-ambiguous``
path when a region would span two NUTS 3 codes), the loud failures (a NUTS code
GISCO does not know, two keys that disagree about the municipality set, an empty
response) and the manifest contents.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scrapers.finland_tmt import (
    KUNTA_KEY,
    MAAKUNTA_AMBIGUOUS_KEY,
    MAAKUNTA_KEY,
    TMT_REFERENCE_FILE,
    FinlandCrosswalk,
)
from scrapers.reference_finland import (
    GISCO_NUTS_2024_URL,
    MANIFEST_FILE,
    build_reference,
    correspondence_maps,
    kunta_maakunta_url,
    kunta_nuts_url,
    kunta_to_maakunta,
    kunta_to_nuts3,
    nuts3_labels,
)

DATE = "20260101"

# Real shapes, trimmed.
GISCO_CSV = (
    "NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN,NUTS_NAME\n"
    "FI,0,FI,Suomi/Finland,Suomi/Finland\n"
    "FI1,1,FI,Manner-Suomi,Manner-Suomi\n"
    "FI1B,2,FI,Helsinki-Uusimaa,Helsinki-Uusimaa\n"
    "FI1B1,3,FI,Helsinki-Uusimaa,Helsinki-Uusimaa\n"
    "FI1C1,3,FI,Varsinais-Suomi,Varsinais-Suomi\n"
    "FI1D7,3,FI,Lappi,Lappi\n"
    "FI200,3,FI,Åland,Åland\n"
    "SE110,3,SE,Stockholms län,Stockholms län\n"
)


def _map(kunta: str, kunta_name: str, target: str, target_name: str, level: int) -> dict[str, Any]:
    """One Statistics Finland correspondence map, in the live payload shape."""
    return {
        "sourceLocalId": f"kunta_1_{DATE}/{kunta}",
        "sourceItem": {
            "level": 1.00,
            "code": kunta,
            "classificationItemNames": [{"lang": "fi", "name": kunta_name}],
        },
        "targetItem": {
            # Statistics Finland serializes ``level`` as a float (3.00).
            "level": float(level),
            "code": target,
            "classificationItemNames": [{"lang": "fi", "name": target_name}],
        },
    }


# Helsinki (091) -> Uusimaa (01) -> FI1B1; Turku (853) -> Varsinais-Suomi (02);
# Ranua (683) -> Lappi (19); Mariehamn (478) -> Ahvenanmaa (21) -> FI200.
KUNTA_NUTS_MAPS = [
    _map("091", "Helsinki", "FI1", "Manner-Suomi", 1),
    _map("091", "Helsinki", "FI1B", "Helsinki-Uusimaa", 2),
    _map("091", "Helsinki", "FI1B1", "Helsinki-Uusimaa", 3),
    _map("853", "Turku", "FI1C1", "Varsinais-Suomi", 3),
    _map("683", "Ranua", "FI1D7", "Lappi", 3),
    _map("478", "Maarianhamina", "FI200", "Åland", 3),
]

KUNTA_MAAKUNTA_MAPS = [
    _map("091", "Helsinki", "01", "Uusimaa", 1),
    _map("853", "Turku", "02", "Varsinais-Suomi", 1),
    _map("683", "Ranua", "19", "Lappi", 1),
    _map("478", "Maarianhamina", "21", "Ahvenanmaa", 1),
]


class FakeStatFi:
    """Minimal stand-in for GISCO + the Statistics Finland classification API."""

    def __init__(
        self,
        *,
        gisco: str = GISCO_CSV,
        kunta_nuts: list[dict[str, Any]] | None = None,
        kunta_maakunta: list[dict[str, Any]] | None = None,
    ) -> None:
        self.gisco = gisco
        self.kunta_nuts = KUNTA_NUTS_MAPS if kunta_nuts is None else kunta_nuts
        self.kunta_maakunta = KUNTA_MAAKUNTA_MAPS if kunta_maakunta is None else kunta_maakunta
        self.requested: list[str] = []
        self.sleeps: list[float] = []

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requested.append(url)
        request = httpx.Request("GET", url)
        if url == GISCO_NUTS_2024_URL:
            return httpx.Response(200, text=self.gisco, request=request)
        if url == kunta_nuts_url(DATE):
            return httpx.Response(200, json=self.kunta_nuts, request=request)
        if url == kunta_maakunta_url(DATE):
            return httpx.Response(200, json=self.kunta_maakunta, request=request)
        raise AssertionError(f"unexpected URL {url}")

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def read_rows(path: Path) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.split(",") for line in lines[1:]]


def test_gisco_filter_keeps_only_finnish_level_three_codes() -> None:
    labels = nuts3_labels(GISCO_CSV)
    assert set(labels) == {"FI1B1", "FI1C1", "FI1D7", "FI200"}
    assert labels["FI200"] == "Åland"
    assert nuts3_labels(GISCO_CSV, country="SE") == {"SE110": "Stockholms län"}


def test_the_key_url_percent_encodes_the_hash_separator() -> None:
    # A raw '#' would be read as a URL fragment and never reach the server.
    assert kunta_nuts_url(DATE).endswith(f"kunta_1_{DATE}%23nuts_2_{DATE}/maps")
    assert kunta_maakunta_url(DATE).endswith(f"kunta_1_{DATE}%23maakunta_1_{DATE}/maps")


def test_correspondence_maps_tolerates_a_malformed_payload() -> None:
    assert correspondence_maps([{"a": 1}, "junk", 3]) == [{"a": 1}]
    assert correspondence_maps({"maps": []}) == []
    assert correspondence_maps(None) == []


def test_only_level_three_targets_become_nuts_rows() -> None:
    codes, names = kunta_to_nuts3(KUNTA_NUTS_MAPS)
    # Helsinki appears at NUTS levels 1, 2 and 3; only level 3 is kept.
    assert codes == {"091": "FI1B1", "853": "FI1C1", "683": "FI1D7", "478": "FI200"}
    assert names["683"] == "Ranua"


def test_kunta_codes_are_folded_to_the_zero_padded_form() -> None:
    codes, _ = kunta_to_nuts3([_map("74", "Halsua", "FI1D5", "Keski-Pohjanmaa", 3)])
    assert codes == {"074": "FI1D5"}
    maakunta, names = kunta_to_maakunta([_map("74", "Halsua", "6", "Keski-Pohjanmaa", 1)])
    assert maakunta == {"074": "06"}
    assert names["06"] == "Keski-Pohjanmaa"


def test_build_writes_both_key_types_and_derives_the_maakunta_layer(tmp_path: Path) -> None:
    fake = FakeStatFi()
    counts = build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)

    assert counts[KUNTA_KEY] == 4
    assert counts[MAAKUNTA_KEY] == 4
    assert counts[MAAKUNTA_AMBIGUOUS_KEY] == 0
    assert counts[TMT_REFERENCE_FILE] == 8

    by_type: dict[str, dict[str, str]] = {}
    for source_type, source_code, nuts_code, *_ in read_rows(tmp_path / TMT_REFERENCE_FILE):
        by_type.setdefault(source_type, {})[source_code] = nuts_code
    assert by_type[KUNTA_KEY]["091"] == "FI1B1"
    assert by_type[KUNTA_KEY]["478"] == "FI200"
    # A Finnish maakunta *is* a NUTS 3 region: derived, then verified.
    assert by_type[MAAKUNTA_KEY]["01"] == "FI1B1"
    assert by_type[MAAKUNTA_KEY]["21"] == "FI200"
    # Charter pacing floor between the three requests.
    assert fake.sleeps == [1.0, 1.0]
    assert fake.requested == [
        GISCO_NUTS_2024_URL,
        kunta_nuts_url(DATE),
        kunta_maakunta_url(DATE),
    ]


def test_a_maakunta_spanning_two_nuts_regions_is_written_ambiguous_with_no_code(
    tmp_path: Path,
) -> None:
    """Never guess: the region key is written with no code so the collector says so."""
    fake = FakeStatFi(
        kunta_maakunta=[
            _map("091", "Helsinki", "01", "Uusimaa", 1),
            # Turku dragged into the same (hypothetical) region as Helsinki.
            _map("853", "Turku", "01", "Uusimaa", 1),
            _map("683", "Ranua", "19", "Lappi", 1),
            _map("478", "Maarianhamina", "21", "Ahvenanmaa", 1),
        ]
    )
    counts = build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)
    assert counts[MAAKUNTA_AMBIGUOUS_KEY] == 1
    assert counts[MAAKUNTA_KEY] == 2

    crosswalk = FinlandCrosswalk(tmp_path)
    assert crosswalk.maakunta_is_ambiguous("01") is True
    assert crosswalk.lookup_maakunta("01") is None
    assert crosswalk.resolve(regions=["01"]).status == "ambiguous"


def test_the_built_crosswalk_is_readable_by_the_collector(tmp_path: Path) -> None:
    fake = FakeStatFi()
    build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)
    crosswalk = FinlandCrosswalk(tmp_path)
    assert crosswalk.lookup_kunta("091") == ("FI1B1", "Helsinki-Uusimaa")
    # The collector and the builder share one normalizer, so "91" hits too.
    assert crosswalk.lookup_kunta("91") == ("FI1B1", "Helsinki-Uusimaa")
    assert crosswalk.lookup_maakunta("19") == ("FI1D7", "Lappi")
    assert crosswalk.lookup_maakunta("9") is None


def test_manifest_records_counts_hashes_and_the_disallowed_codeset_reason(tmp_path: Path) -> None:
    fake = FakeStatFi()
    build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)
    manifest = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))

    assert manifest["nuts_version"] == "NUTS-2024"
    assert manifest["classification_date"] == DATE
    assert manifest["kunta_nuts_maps_read"] == len(KUNTA_NUTS_MAPS)
    assert manifest["kunta_maakunta_maps_read"] == len(KUNTA_MAAKUNTA_MAPS)
    assert manifest["ambiguous_maakunta_codes"] == []
    assert manifest["nuts3_without_municipality"] == []
    assert manifest["maakunta_join"]["21"]["name"] == "Ahvenanmaa"
    assert manifest["maakunta_join"]["21"]["nuts_code"] == "FI200"
    # The source's own codeset service is robots-disallowed; the reason is pinned.
    assert "robots.txt disallows /api/" in manifest["codeset_source_not_used"]["reason"]
    assert len(manifest["hashes"][TMT_REFERENCE_FILE]) == 64


def test_a_nuts_code_gisco_does_not_know_raises(tmp_path: Path) -> None:
    fake = FakeStatFi(kunta_nuts=[*KUNTA_NUTS_MAPS, _map("999", "Uusi", "FI1XX", "Uusi", 3)])
    with pytest.raises(RuntimeError, match="absent from Eurostat GISCO"):
        build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)


def test_keys_that_disagree_about_the_municipality_set_raise(tmp_path: Path) -> None:
    fake = FakeStatFi(kunta_maakunta=KUNTA_MAAKUNTA_MAPS[:2])
    with pytest.raises(RuntimeError, match="disagree about the municipality set"):
        build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)


def test_a_key_with_no_level_three_maps_raises(tmp_path: Path) -> None:
    fake = FakeStatFi(kunta_nuts=[_map("091", "Helsinki", "FI1B", "Helsinki-Uusimaa", 2)])
    with pytest.raises(RuntimeError, match="no level-3 target maps"):
        build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date=DATE)


def test_an_empty_source_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no Finnish NUTS 3 codes"):
        build_reference(
            tmp_path,
            get=FakeStatFi(gisco="NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN\n").get,
            sleep=lambda _: None,
            date=DATE,
        )
    with pytest.raises(RuntimeError, match="no maps"):
        build_reference(
            tmp_path, get=FakeStatFi(kunta_nuts=[]).get, sleep=lambda _: None, date=DATE
        )
    with pytest.raises(RuntimeError, match="no maps"):
        build_reference(
            tmp_path, get=FakeStatFi(kunta_maakunta=[]).get, sleep=lambda _: None, date=DATE
        )


def test_the_committed_crosswalk_matches_its_manifest() -> None:
    """The pinned file the offline gate depends on must stay consistent."""
    reference = Path("data/reference")
    crosswalk = FinlandCrosswalk(reference)
    manifest = json.loads((reference / MANIFEST_FILE).read_text(encoding="utf-8"))

    assert len(crosswalk.kunnat()) == manifest["row_counts"][KUNTA_KEY] == 308
    assert len(crosswalk.maakunnat()) == manifest["row_counts"][MAAKUNTA_KEY] == 19
    # Every Finnish NUTS 3 region is reachable and none is left behind.
    assert len(manifest["gisco_nuts3_codes"]) == 19
    assert manifest["nuts3_without_municipality"] == []
    assert manifest["ambiguous_maakunta_codes"] == []
    assert crosswalk.lookup_kunta("091") == ("FI1B1", "Helsinki-Uusimaa")
    assert crosswalk.lookup_maakunta("21") == ("FI200", "Åland")
    assert crosswalk.lookup_maakunta("01") == ("FI1B1", "Helsinki-Uusimaa")
