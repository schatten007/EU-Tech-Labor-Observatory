"""Unit tests for the MPSV codelist -> NUTS 2024 crosswalk resolution rules."""

from pathlib import Path

import pytest

from scrapers.czech_mpsv import MpsvCrosswalk, RegionResolution

HEADER = "source_type,source_code,nuts_code,nuts_label,source_url,source_version\n"

KRAJE_ROWS = (
    "kraj,Kraj/19,CZ010,Hlavní město Praha,https://data.mpsv.cz/od/soubory/ciselniky/kraje.json,2026-08-21\n"
    "kraj,Kraj/27,CZ020,Středočeský kraj,https://data.mpsv.cz/od/soubory/ciselniky/kraje.json,2026-08-21\n"
    "kraj,Kraj/132,CZ080,Moravskoslezský kraj,https://data.mpsv.cz/od/soubory/ciselniky/kraje.json,2026-08-21\n"
)
OKRESY_ROWS = (
    "okres,Okres/9999,CZ010,Hlavní město Praha,https://data.mpsv.cz/od/soubory/ciselniky/okresy.json,2026-08-21\n"
    "okres,Okres/3100,CZ010,Hlavní město Praha,https://data.mpsv.cz/od/soubory/ciselniky/okresy.json,2026-08-21\n"
    "okres,Okres/2101,CZ020,Středočeský kraj,https://data.mpsv.cz/od/soubory/ciselniky/okresy.json,2026-08-21\n"
)
OBCE_ROWS = (
    "obec,Obec/554782,CZ010,Hlavní město Praha,https://data.mpsv.cz/od/soubory/ciselniky/obce.json,2026-08-21\n"
    "obec,Obec/529303,CZ020,Středočeský kraj,https://data.mpsv.cz/od/soubory/ciselniky/obce.json,2026-08-21\n"
)


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    root = tmp_path / "reference"
    root.mkdir()
    (root / "mpsv_kraje_nuts_2024.csv").write_text(HEADER + KRAJE_ROWS, encoding="utf-8")
    (root / "mpsv_okresy_kraj_2024.csv").write_text(HEADER + OKRESY_ROWS, encoding="utf-8")
    (root / "mpsv_obce_kraj_2024.csv").write_text(HEADER + OBCE_ROWS, encoding="utf-8")
    return root


def resolve(
    crosswalk: MpsvCrosswalk,
    *,
    work_kraje: list[str] | None = None,
    contact_kraj: str | None = None,
    okres_ids: list[str] | None = None,
    obec_id: str | None = None,
) -> RegionResolution:
    return crosswalk.resolve(
        work_kraje=work_kraje or [],
        contact_kraj=contact_kraj,
        okres_ids=okres_ids or [],
        obec_id=obec_id,
    )


def test_workplace_region_mapped(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), work_kraje=["Kraj/132"])
    assert result.nuts_code == "CZ080"
    assert result.nuts_label == "Moravskoslezský kraj"
    assert result.status == "mapped"
    assert result.method == "mpsv_kraje_codelist_nuts3"


def test_disagreeing_workplaces_are_ambiguous(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), work_kraje=["Kraj/19", "Kraj/27"])
    assert result.status == "ambiguous"
    assert result.nuts_code == "CZ010"  # first region wins


def test_contact_address_is_low_confidence(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), contact_kraj="Kraj/27")
    assert result.status == "low_confidence"
    assert result.nuts_code == "CZ020"
    assert result.method == "mpsv_kraje_codelist_contact_address"


def test_workplace_beats_contact_address(reference_dir: Path) -> None:
    result = resolve(
        MpsvCrosswalk(reference_dir),
        work_kraje=["Kraj/132"],
        contact_kraj="Kraj/27",
    )
    assert result.status == "mapped"
    assert result.nuts_code == "CZ080"


def test_okres_fallback_mapped(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), okres_ids=["Okres/3100"])
    assert result.status == "mapped"
    assert result.nuts_code == "CZ010"
    assert result.method == "mpsv_okres_codelist_nuts3"


def test_okreses_spanning_regions_are_ambiguous(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), okres_ids=["Okres/9999", "Okres/2101"])
    assert result.status == "ambiguous"
    assert result.nuts_code == "CZ010"


def test_obec_fallback_mapped(reference_dir: Path) -> None:
    result = resolve(MpsvCrosswalk(reference_dir), obec_id="Obec/554782")
    assert result.status == "mapped"
    assert result.nuts_code == "CZ010"
    assert result.method == "mpsv_obec_codelist_nuts3"


def test_unknown_codes_fall_through(reference_dir: Path) -> None:
    result = resolve(
        MpsvCrosswalk(reference_dir),
        work_kraje=["Kraj/999"],
        okres_ids=["Okres/999"],
        obec_id="Obec/999",
    )
    assert result.status == "unmapped"
    assert result.nuts_code is None
    assert result.method == "not_available"


def test_missing_reference_file_fails(reference_dir: Path) -> None:
    (reference_dir / "mpsv_okresy_kraj_2024.csv").unlink()
    with pytest.raises(FileNotFoundError):
        MpsvCrosswalk(reference_dir)
