"""Unit tests for MPSVCollector (Increment 2) with a mocked daily dump."""

import asyncio
import json
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.base import NormalizedRecord
from scrapers.czech_mpsv import (
    MPSV_DUMP_URL,
    MPSVCollector,
    crosswalk_reference_hashes,
    parse_cz_date,
    parse_cz_datetime,
)
from scrapers.retry import RetryPolicy

KEY = b"test-only-key-with-at-least-32-bytes"
REFERENCE_DIR = Path(__file__).resolve().parents[1] / "data" / "reference"


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


def dump_item(
    portal_id: int,
    *,
    published: str = "2026-02-18T00:00:00.000Z",
    modified: str = "2026-08-19T23:11:31.000Z",
    pocet_mist: int = 3,
    expirace: str | None = None,
    kraj_id: str | None = "Kraj/132",
    contact_kraj_id: str | None = None,
    okres_ids: list[str] | None = None,
    obec_id: str | None = None,
) -> dict[str, Any]:
    """One dump record carrying PII that must never reach the allowlist."""
    pracoviste: list[dict[str, Any]] = []
    if kraj_id is not None:
        pracoviste.append(
            {
                "nazev": "Private workplace",
                "email": "priv@example.com",
                "telefon": "123 456 789",
                "adresa": {
                    "ulice": {"nazev": "Privátní ulice"},
                    "psc": "70030",
                    "kraj": {"id": kraj_id},
                },
            }
        )
    mvp: dict[str, Any] = {}
    if pracoviste:
        mvp["pracoviste"] = pracoviste
    if okres_ids:
        mvp["okresy"] = [{"id": oid} for oid in okres_ids]
    if obec_id:
        mvp["obec"] = {"id": obec_id}
    kde: dict[str, Any] = {}
    if contact_kraj_id is not None:
        kde["adresa"] = {"kraj": {"id": contact_kraj_id}}
    return {
        "portalId": portal_id,
        "id": f"VolneMisto/{portal_id}",
        "referencniCislo": f"R{portal_id}",
        "datumVlozeni": published,
        "datumZmeny": modified,
        "expirace": expirace,
        "pocetMist": pocet_mist,
        "mistoVykonuPrace": mvp or None,
        "prvniKontaktSeZamestnavatelem": {
            "komuSeHlasit": {
                "email": "jan.novak@example.com",
                "telefon": "777 111 222",
                "jmeno": "Jan",
                "prijmeni": "Novák",
            },
            "kdeSeHlasit": kde,
        },
        "zamestnavatel": {"ico": "12345678", "nazev": "Private Employer s.r.o."},
        "urlAdresa": "https://private.example.com/vacancy/1",
        "upresnujiciInformace": {"cs": "Very long private description " * 50},
        "pozadovanaProfese": {"cs": "Private occupation title"},
        "profeseCzIsco": {"id": "CzIsco/51203"},
    }


def collect_dump(items: list[dict[str, Any]]) -> list[NormalizedRecord]:
    async def collect() -> list[NormalizedRecord]:
        collector = MPSVCollector(
            scope_id="cz-all-active",
            sweep_id="20260822T000000Z",
            observed_at=datetime(2026, 8, 22, tzinfo=UTC),
            hmac_key=KEY,
            reference_dir=REFERENCE_DIR,
            pacing_interval=0.0,
        )
        async with collector:
            return [record async for record in collector.collect()]

    return run(collect())


def test_collect_single_request_and_normalizes() -> None:
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(
            return_value=httpx.Response(
                200, json={"polozky": [dump_item(67232098), dump_item(67285419, pocet_mist=1)]}
            )
        )
        call_count = 0

        async def collect() -> list[NormalizedRecord]:
            nonlocal call_count
            collector = MPSVCollector(
                scope_id="cz-all-active",
                sweep_id="20260822T000000Z",
                observed_at=datetime(2026, 8, 22, tzinfo=UTC),
                hmac_key=KEY,
                reference_dir=REFERENCE_DIR,
                pacing_interval=0.0,
            )
            async with collector:
                records = [record async for record in collector.collect()]
                call_count = len(respx.calls)
                return records

        records = run(collect())

    assert call_count == 1
    assert len(records) == 2
    first = records[0]
    assert first.source == "mpsv"
    assert first.country == "CZ"
    assert first.lang == "cs"
    assert first.source_language == "cs"
    assert len(first.source_id) == 64
    assert first.first_published == datetime(2026, 2, 18, tzinfo=UTC)
    assert first.last_modified == datetime(2026, 8, 19, 23, 11, 31, tzinfo=UTC)
    assert first.number_of_vacancies == 3
    assert records[1].number_of_vacancies == 1
    assert first.removed_at is None
    assert first.occupation_mapping_status == "not_present"
    assert first.region_mapping_status in {"mapped", "low_confidence", "unmapped"}
    assert first.nuts_version == "NUTS-2024"


def test_pii_never_reaches_output() -> None:
    item = dump_item(1, kraj_id="Kraj/132")
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))
        records = collect_dump([item])

    dumped = json.dumps(records[0].model_dump_ndjson(), ensure_ascii=False)
    assert "jan.novak@example.com" not in dumped
    assert "Novák" not in dumped
    assert "777 111 222" not in dumped
    assert "Private Employer" not in dumped
    assert "70030" not in dumped
    assert "Privátní" not in dumped
    assert "private.example.com" not in dumped
    assert "Very long private description" not in dumped
    assert "Private occupation title" not in dumped
    # The allowlist itself is the only key set.
    assert set(records[0].model_dump()) == {
        "source",
        "source_id",
        "scope_id",
        "sweep_id",
        "observed_at",
        "first_published",
        "last_modified",
        "removed_at",
        "nuts_code",
        "nuts_label",
        "region_mapping_status",
        "region_mapping_method",
        "nuts_version",
        "country",
        "esco_occupation_uri",
        "esco_occupation_label",
        "occupation_mapping_status",
        "occupation_mapping_confidence",
        "occupation_mapping_method",
        "source_language",
        "jobtech_taxonomy_version",
        "esco_version",
        "skill_mappings",
        "lang",
        "number_of_vacancies",
    }


def test_region_mapped_from_workplace() -> None:
    item = dump_item(1, kraj_id="Kraj/132")
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))
        records = collect_dump([item])

    record = records[0]
    assert record.nuts_code == "CZ080"
    assert record.nuts_label == "Moravskoslezský kraj"
    assert record.region_mapping_status == "mapped"
    assert record.region_mapping_method == "mpsv_kraje_codelist_nuts3"


def test_region_low_confidence_from_contact_address() -> None:
    item = dump_item(1, kraj_id=None, contact_kraj_id="Kraj/116")
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))
        records = collect_dump([item])

    record = records[0]
    assert record.nuts_code == "CZ064"
    assert record.region_mapping_status == "low_confidence"
    assert record.region_mapping_method == "mpsv_kraje_codelist_contact_address"


def test_region_fallback_via_okres_and_obec() -> None:
    okres_item = dump_item(1, kraj_id=None, okres_ids=["Okres/3100"])
    obec_item = dump_item(2, kraj_id=None, obec_id="Obec/554782")
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(
            return_value=httpx.Response(200, json={"polozky": [okres_item, obec_item]})
        )
        records = collect_dump([okres_item, obec_item])

    assert records[0].nuts_code == "CZ010"
    assert records[0].region_mapping_method == "mpsv_okres_codelist_nuts3"
    assert records[1].nuts_code == "CZ010"
    assert records[1].region_mapping_method == "mpsv_obec_codelist_nuts3"


def test_region_unmapped_when_nothing_present() -> None:
    item = dump_item(1, kraj_id=None)
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))
        records = collect_dump([item])

    record = records[0]
    assert record.nuts_code is None
    assert record.nuts_label is None
    assert record.region_mapping_status == "unmapped"
    assert record.region_mapping_method == "not_available"


def test_missing_portal_id_fails_loudly() -> None:
    item = dump_item(1)
    del item["portalId"]
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))
        with pytest.raises(ValueError):
            collect_dump([item])


def test_collector_retries_transient_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"polozky": [dump_item(1)]})

    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(side_effect=handler)
        policy = RetryPolicy(max_attempts=3, base_delay=0.01, jitter=0.0)

        async def collect() -> list[NormalizedRecord]:
            collector = MPSVCollector(
                scope_id="s",
                sweep_id="w",
                observed_at=datetime(2026, 8, 22, tzinfo=UTC),
                hmac_key=KEY,
                reference_dir=REFERENCE_DIR,
                pacing_interval=0.0,
                policy=policy,
            )
            async with collector:
                return [record async for record in collector.collect()]

        records = run(collect())

    assert calls == 2
    assert len(records) == 1


def test_expirace_meta_accumulated_per_source_id() -> None:
    item = dump_item(42, expirace="2026-09-01")
    with respx.mock:
        respx.get(MPSV_DUMP_URL).mock(return_value=httpx.Response(200, json={"polozky": [item]}))

        async def collect() -> tuple[list[NormalizedRecord], dict[str, str]]:
            collector = MPSVCollector(
                scope_id="cz-all-active",
                sweep_id="w",
                observed_at=datetime(2026, 8, 22, tzinfo=UTC),
                hmac_key=KEY,
                reference_dir=REFERENCE_DIR,
                pacing_interval=0.0,
            )
            async with collector:
                records = [record async for record in collector.collect()]
                return records, dict(collector.expirace_by_source_id)

        records, expirace_map = run(collect())

    assert len(expirace_map) == 1
    assert expirace_map[records[0].source_id] == "2026-09-01"


def test_parse_cz_datetime_and_date() -> None:
    assert parse_cz_datetime("2026-02-18T00:00:00.000Z") == datetime(2026, 2, 18, tzinfo=UTC)
    assert parse_cz_datetime("2026-08-19T23:11:31.000Z") == datetime(
        2026, 8, 19, 23, 11, 31, tzinfo=UTC
    )
    assert parse_cz_datetime(None) is None
    assert parse_cz_datetime("garbage") is None
    assert parse_cz_date("2026-09-01") == datetime(2026, 9, 1, tzinfo=UTC)
    assert parse_cz_date(None) is None
    assert parse_cz_date("not-a-date") is None


def test_crosswalk_reference_hashes_are_deterministic() -> None:
    first = crosswalk_reference_hashes(REFERENCE_DIR)
    second = crosswalk_reference_hashes(REFERENCE_DIR)
    assert first == second
    assert "mpsv_kraje_nuts_2024.csv:" in first
