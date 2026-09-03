"""Unit tests for the VDAB postcode -> NUTS 2024 crosswalk builder (Increment 5).

The register walk is driven with an injected ``get``/``sleep`` so the gate stays
offline. Covers postcode enumeration across ``volgende`` pages, the GISCO
validation join, the 404/410 skip path (Brussels' ``1000`` answers
``410 Verwijderde postcode`` live), the loud failure on an unknown ``nuts3``,
and restartability from a partial CSV.
"""

import json
from pathlib import Path

import httpx
import pytest

from scrapers.reference_vdab import (
    GISCO_NUTS_2024_URL,
    MANIFEST_FILE,
    POSTINFO_DETAIL_URL,
    build_reference,
    enumerate_postcodes,
    load_existing,
    nuts3_labels,
)
from scrapers.vdab import VDAB_REFERENCE_FILE, VDABCrosswalk

GISCO_CSV = (
    "NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN,NUTS_NAME\n"
    "BE,0,BE,Belgique/België,Belgique/België\n"
    "BE2,1,BE,Vlaams Gewest,Vlaams Gewest\n"
    "BE23,2,BE,Prov. Oost-Vlaanderen,Prov. Oost-Vlaanderen\n"
    "BE234,3,BE,Arr. Gent,Arr. Gent\n"
    "BE211,3,BE,Arr. Antwerpen,Arr. Antwerpen\n"
    "BE100,3,BE,Arr. de Bruxelles-Capitale,Arr. Brussel-Hoofdstad\n"
    "FR101,3,FR,Paris,Paris\n"
)


def postinfo_page(codes: list[str], *, next_url: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {
        "postInfoObjecten": [
            {"identificator": {"objectId": code}, "postInfoStatus": "gerealiseerd"}
            for code in codes
        ]
    }
    if next_url:
        payload["volgende"] = next_url
    return payload


class FakeRegister:
    """Minimal stand-in for Basisregisters Vlaanderen + GISCO."""

    def __init__(
        self,
        *,
        pages: list[dict[str, object]],
        details: dict[str, httpx.Response],
        gisco: str = GISCO_CSV,
    ) -> None:
        self.pages = pages
        self.details = details
        self.gisco = gisco
        self.requested: list[str] = []
        self.sleeps: list[float] = []
        self._page_index = 0

    def get(self, url: str, **_: object) -> httpx.Response:
        self.requested.append(url)
        request = httpx.Request("GET", url)
        if url == GISCO_NUTS_2024_URL:
            return httpx.Response(200, text=self.gisco, request=request)
        if "/postinfo/" in url:
            postcode = url.rsplit("/", 1)[-1]
            response = self.details.get(postcode)
            if response is None:
                return httpx.Response(404, json={"status": "404"}, request=request)
            response.request = request
            return response
        page = self.pages[min(self._page_index, len(self.pages) - 1)]
        self._page_index += 1
        return httpx.Response(200, json=page, request=request)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def detail(nuts3: str | None) -> httpx.Response:
    body: dict[str, object] = {"identificator": {"objectId": "x"}}
    if nuts3 is not None:
        body["nuts3"] = nuts3
    return httpx.Response(200, json=body)


def test_nuts3_labels_keeps_belgian_level_three_only() -> None:
    labels = nuts3_labels(GISCO_CSV)
    assert labels == {
        "BE234": "Arr. Gent",
        "BE211": "Arr. Antwerpen",
        "BE100": "Arr. de Bruxelles-Capitale",
    }


def test_enumerate_postcodes_follows_volgende_and_skips_non_postcodes() -> None:
    register = FakeRegister(
        pages=[
            postinfo_page(["9000", "2000", "not-a-code"], next_url="https://x.invalid/next"),
            postinfo_page(["3000", "9000"]),
        ],
        details={},
    )
    codes = enumerate_postcodes(register.get, sleep=register.sleep)
    assert codes == ["2000", "3000", "9000"]
    # One paced wait between the two list pages.
    assert register.sleeps == [1.0]


def test_build_reference_writes_csv_and_manifest(tmp_path: Path) -> None:
    register = FakeRegister(
        pages=[postinfo_page(["9000", "2000", "1000", "0612", "5000"])],
        details={
            "9000": detail("BE234"),
            "2000": detail("BE211"),
            # Brussels is removed from the Flemish register (live: 410).
            "1000": httpx.Response(410, json={"detail": "Verwijderde postcode."}),
            "0612": detail("BE100"),
            "5000": detail(None),
        },
    )
    counts = build_reference(tmp_path, get=register.get, sleep=register.sleep, resume=False)
    assert counts == {VDAB_REFERENCE_FILE: 3}

    crosswalk = VDABCrosswalk(tmp_path)
    assert crosswalk.resolve("9000").nuts_code == "BE234"
    assert crosswalk.resolve("2000").nuts_label == "Arr. Antwerpen"
    assert crosswalk.resolve("1000").status == "unmapped"
    assert crosswalk.resolve("5000").status == "unmapped"

    manifest = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["row_counts"] == {VDAB_REFERENCE_FILE: 3}
    assert manifest["postcodes_enumerated"] == 5
    assert manifest["postcodes_skipped"] == {"410": 1, "no_nuts3": 1}
    assert manifest["flemish_nuts3"] == ["BE211", "BE234"]
    assert manifest["non_flemish_nuts3"] == ["0612:BE100"]
    assert manifest["unmatched_nuts3"] == []
    assert manifest["nuts_version"] == "NUTS-2024"
    assert len(manifest["hashes"][VDAB_REFERENCE_FILE]) == 64
    assert manifest["source_urls"]["nuts_2024"] == GISCO_NUTS_2024_URL


def test_unknown_nuts3_is_reported_not_dropped(tmp_path: Path) -> None:
    register = FakeRegister(
        pages=[postinfo_page(["9000", "4321"])],
        details={"9000": detail("BE234"), "4321": detail("BE999")},
    )
    with pytest.raises(RuntimeError, match="BE999"):
        build_reference(tmp_path, get=register.get, sleep=register.sleep, resume=False)


def test_empty_gisco_table_fails(tmp_path: Path) -> None:
    register = FakeRegister(
        pages=[postinfo_page(["9000"])],
        details={"9000": detail("BE234")},
        gisco="NUTS_ID,LEVL_CODE,CNTR_CODE,NAME_LATN\nFR101,3,FR,Paris\n",
    )
    with pytest.raises(RuntimeError, match="NUTS 3"):
        build_reference(tmp_path, get=register.get, sleep=register.sleep, resume=False)


def test_resume_skips_postcodes_already_written(tmp_path: Path) -> None:
    first = FakeRegister(
        pages=[postinfo_page(["9000"])],
        details={"9000": detail("BE234")},
    )
    build_reference(tmp_path, get=first.get, sleep=first.sleep, resume=False)

    second = FakeRegister(
        pages=[postinfo_page(["9000", "2000"])],
        details={"9000": detail("BE234"), "2000": detail("BE211")},
    )
    counts = build_reference(tmp_path, get=second.get, sleep=second.sleep, resume=True)
    assert counts == {VDAB_REFERENCE_FILE: 2}
    detail_calls = [url for url in second.requested if "/postinfo/" in url]
    assert detail_calls == [POSTINFO_DETAIL_URL.format(postcode="2000")]

    manifest = json.loads((tmp_path / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert manifest["postcodes_resolved_this_run"] == 1
    assert load_existing(tmp_path / VDAB_REFERENCE_FILE).keys() == {"9000", "2000"}


def test_fresh_build_ignores_the_existing_csv(tmp_path: Path) -> None:
    first = FakeRegister(pages=[postinfo_page(["9000"])], details={"9000": detail("BE234")})
    build_reference(tmp_path, get=first.get, sleep=first.sleep, resume=False)

    second = FakeRegister(pages=[postinfo_page(["2000"])], details={"2000": detail("BE211")})
    counts = build_reference(tmp_path, get=second.get, sleep=second.sleep, resume=False)
    assert counts == {VDAB_REFERENCE_FILE: 1}
    assert load_existing(tmp_path / VDAB_REFERENCE_FILE).keys() == {"2000"}


def test_limit_truncates_the_walk(tmp_path: Path) -> None:
    register = FakeRegister(
        pages=[postinfo_page(["9000", "2000", "3000"])],
        details={"9000": detail("BE234"), "2000": detail("BE211"), "3000": detail("BE234")},
    )
    counts = build_reference(
        tmp_path, get=register.get, sleep=register.sleep, resume=False, limit=2
    )
    # Sorted enumeration: 2000, 3000 (9000 is out of the limit).
    assert counts == {VDAB_REFERENCE_FILE: 2}
    assert load_existing(tmp_path / VDAB_REFERENCE_FILE).keys() == {"2000", "3000"}


def test_load_existing_returns_empty_without_a_file(tmp_path: Path) -> None:
    assert load_existing(tmp_path / VDAB_REFERENCE_FILE) == {}
