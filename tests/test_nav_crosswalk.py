"""Unit tests for the NAV fylke/kommune -> NUTS 2024 crosswalk builder (Increment 6).

The build is driven with an injected ``get``/``sleep`` so the gate stays offline.
Covers the GISCO level-3 filter, the name join across SSB's hyphenated Sami dual
names and GISCO's slashed ones, the kommune -> fylke prefix rule, the ambiguous
repeated-name path (``Herøy`` exists in two counties), the loud failures (an
unmatched fylke, an orphan kommune prefix, an empty classification) and the
manifest contents.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from scrapers.nav_norway import (
    FYLKE_KEY,
    KOMMUNE_AMBIGUOUS_KEY,
    KOMMUNE_KEY,
    NAV_REFERENCE_FILE,
    NAVCrosswalk,
)
from scrapers.reference_nav import (
    GISCO_NUTS_2024_URL,
    KLASS_FYLKER_URL,
    KLASS_KOMMUNER_URL,
    MANIFEST_FILE,
    build_reference,
    klass_codes,
    match_fylker,
    nuts3_labels,
)

# Real shapes, trimmed: NAME_LATN carries the slashed Sami duals.
GISCO_CSV = (
    "NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN,NUTS_NAME\n"
    "NO,0,NO,Norge,Norge\n"
    "NO0,1,NO,Norge,Norge\n"
    "NO0A,2,NO,Vestlandet,Vestlandet\n"
    "NO0A2,3,NO,Vestland,Vestland\n"
    "NO0A3,3,NO,Møre og Romsdal,Møre og Romsdal\n"
    "NO071,3,NO,Nordland/Nordlánnda,Nordland/Nordlánnda\n"
    "NO072,3,NO,Troms/Romsa/Tromssa,Troms/Romsa/Tromssa\n"
    "NO081,3,NO,Oslo,Oslo\n"
    "NO0B2,3,NO,Svalbard,Svalbard\n"
    "SE110,3,SE,Stockholms län,Stockholms län\n"
)

FYLKER = [
    {"code": "03", "name": "Oslo - Oslove"},
    {"code": "15", "name": "Møre og Romsdal"},
    {"code": "18", "name": "Nordland - Nordlánnda"},
    {"code": "46", "name": "Vestland"},
    {"code": "55", "name": "Troms - Romsa - Tromssa"},
    {"code": "99", "name": "Uoppgitt"},
]

KOMMUNER = [
    {"code": "0301", "name": "Oslo - Oslove"},
    {"code": "1515", "name": "Herøy (Møre og Romsdal)"},
    {"code": "1818", "name": "Herøy (Nordland)"},
    {"code": "4601", "name": "Bergen"},
    {"code": "5501", "name": "Tromsø"},
    {"code": "9999", "name": "Uoppgitt"},
]


class FakeKlass:
    """Minimal stand-in for GISCO + SSB Klass."""

    def __init__(
        self,
        *,
        gisco: str = GISCO_CSV,
        fylker: list[dict[str, str]] | None = None,
        kommuner: list[dict[str, str]] | None = None,
    ) -> None:
        self.gisco = gisco
        self.fylker = FYLKER if fylker is None else fylker
        self.kommuner = KOMMUNER if kommuner is None else kommuner
        self.requested: list[str] = []
        self.sleeps: list[float] = []

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        self.requested.append(url)
        request = httpx.Request("GET", url)
        if url == GISCO_NUTS_2024_URL:
            return httpx.Response(200, text=self.gisco, request=request)
        if url == KLASS_FYLKER_URL:
            return httpx.Response(200, json={"codes": self.fylker}, request=request)
        if url == KLASS_KOMMUNER_URL:
            return httpx.Response(200, json={"codes": self.kommuner}, request=request)
        raise AssertionError(f"unexpected URL {url}")

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def read_rows(path: Path) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [line.split(",") for line in lines[1:]]


def test_gisco_filter_keeps_only_norwegian_level_three_codes() -> None:
    labels = nuts3_labels(GISCO_CSV)
    assert set(labels) == {"NO0A2", "NO0A3", "NO071", "NO072", "NO081", "NO0B2"}
    assert labels["NO072"] == "Troms/Romsa/Tromssa"
    assert nuts3_labels(GISCO_CSV, country="SE") == {"SE110": "Stockholms län"}


def test_klass_codes_tolerates_a_malformed_payload() -> None:
    assert klass_codes({"codes": [{"code": "46", "name": "Vestland"}]}) == [
        {"code": "46", "name": "Vestland"}
    ]
    assert klass_codes({"codes": [{"name": "no code"}]}) == []
    assert klass_codes({}) == []
    assert klass_codes("not a dict") == []


def test_fylke_join_bridges_hyphenated_and_slashed_sami_names() -> None:
    matched, unmatched = match_fylker(FYLKER, nuts3_labels(GISCO_CSV))
    assert matched["55"][0] == "NO072"
    assert matched["18"][0] == "NO071"
    assert matched["03"][0] == "NO081"
    # SSB's "Uoppgitt" has no NUTS 3 equivalent and is expected to be unmatched.
    assert unmatched == ["99:Uoppgitt"]


def test_build_writes_both_key_types_and_marks_repeated_names_ambiguous(tmp_path: Path) -> None:
    fake = FakeKlass()
    counts = build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date="2026-08-23")

    assert counts[FYLKE_KEY] == 5  # Uoppgitt excluded
    assert counts[KOMMUNE_KEY] == 3  # Oslo, Bergen, Tromsø
    assert counts[KOMMUNE_AMBIGUOUS_KEY] == 1  # Herøy sits in two counties
    assert counts[NAV_REFERENCE_FILE] == 9

    rows = read_rows(tmp_path / NAV_REFERENCE_FILE)
    by_type: dict[str, dict[str, str]] = {}
    for source_type, source_code, nuts_code, *_ in rows:
        by_type.setdefault(source_type, {})[source_code] = nuts_code
    assert by_type[FYLKE_KEY]["troms"] == "NO072"
    assert by_type[FYLKE_KEY]["more og romsdal"] == "NO0A3"
    assert by_type[KOMMUNE_KEY]["bergen"] == "NO0A2"
    assert by_type[KOMMUNE_KEY]["tromso"] == "NO072"
    assert by_type[KOMMUNE_AMBIGUOUS_KEY]["heroy"] == ""
    # Charter pacing floor between the three hosts/requests.
    assert fake.sleeps == [1.0, 1.0]


def test_the_built_crosswalk_is_readable_by_the_collector(tmp_path: Path) -> None:
    fake = FakeKlass()
    build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date="2026-08-23")
    crosswalk = NAVCrosswalk(tmp_path)
    assert crosswalk.lookup_fylke("TROMS") == ("NO072", "Troms/Romsa/Tromssa")
    assert crosswalk.lookup_kommune("BERGEN") == ("NO0A2", "Vestland")
    assert crosswalk.kommune_is_ambiguous("HERØY") is True


def test_manifest_records_counts_hashes_and_the_unmapped_nuts_codes(tmp_path: Path) -> None:
    fake = FakeKlass()
    build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date="2026-08-23")
    manifest = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))

    assert manifest["nuts_version"] == "NUTS-2024"
    assert manifest["classification_date"] == "2026-08-23"
    assert manifest["ssb_fylker_read"] == 6
    assert manifest["ssb_kommuner_read"] == 6
    assert manifest["unmatched_fylker"] == ["99:Uoppgitt"]
    assert manifest["unspecified_kommuner"] == ["9999:Uoppgitt"]
    assert manifest["ambiguous_kommune_names"] == ["heroy"]
    # Svalbard has no SSB fylke: reported, never forced onto a county.
    assert manifest["nuts3_without_ssb_fylke"] == ["NO0B2"]
    assert manifest["historic_names_included"] is False
    assert len(manifest["hashes"][NAV_REFERENCE_FILE]) == 64
    assert manifest["row_counts"][FYLKE_KEY] == 5


def test_an_unmatched_fylke_raises_instead_of_being_dropped(tmp_path: Path) -> None:
    fake = FakeKlass(fylker=[*FYLKER, {"code": "77", "name": "Nyfylke"}])
    with pytest.raises(RuntimeError, match="no Eurostat GISCO NUTS 2024 match"):
        build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date="2026-08-23")


def test_a_kommune_whose_prefix_is_not_a_known_fylke_raises(tmp_path: Path) -> None:
    fake = FakeKlass(kommuner=[*KOMMUNER, {"code": "2100", "name": "Svalbard"}])
    with pytest.raises(RuntimeError, match="fylke prefix"):
        build_reference(tmp_path, get=fake.get, sleep=fake.sleep, date="2026-08-23")


def test_an_empty_source_raises(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="no Norwegian NUTS 3 codes"):
        build_reference(
            tmp_path,
            get=FakeKlass(gisco="NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN\n").get,
            sleep=lambda _: None,
            date="2026-08-23",
        )
    with pytest.raises(RuntimeError, match="Klass 104"):
        build_reference(
            tmp_path, get=FakeKlass(fylker=[]).get, sleep=lambda _: None, date="2026-08-23"
        )
    with pytest.raises(RuntimeError, match="Klass 131"):
        build_reference(
            tmp_path, get=FakeKlass(kommuner=[]).get, sleep=lambda _: None, date="2026-08-23"
        )


def test_the_committed_crosswalk_matches_its_manifest() -> None:
    """The pinned file the offline gate depends on must stay consistent."""
    reference = Path("data/reference")
    crosswalk = NAVCrosswalk(reference)
    manifest = json.loads((reference / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert len(crosswalk.fylker()) == manifest["row_counts"][FYLKE_KEY]
    assert len(crosswalk.kommuner()) == manifest["row_counts"][KOMMUNE_KEY]
    # All 15 mainland counties resolve; Jan Mayen and Svalbard have no fylke.
    assert manifest["nuts3_without_ssb_fylke"] == ["NO0B1", "NO0B2"]
    assert crosswalk.lookup_fylke("VESTLAND") == ("NO0A2", "Vestland")
    assert crosswalk.lookup_kommune("ØSTRE TOTEN") == ("NO020", "Innlandet")
    assert crosswalk.kommune_is_ambiguous("HERØY") is True
