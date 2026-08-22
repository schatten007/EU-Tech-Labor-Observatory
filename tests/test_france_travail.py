"""Unit tests for FranceTravailCollector (Increment 4) with a mocked OAuth2 API.

Covers the client-credentials token flow (mint, TTL reuse, refresh-on-401),
``range`` window pagination against the live 150-item / 3000-start caps,
département segmentation with HMAC dedupe, normalization onto the SAFE_FIELDS
allowlist, the département -> NUTS 2024 crosswalk, PII isolation, 429 backoff
honoring ``Retry-After``, and date/edge cases.
"""

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
from scrapers.france_travail import (
    FT_MAX_START,
    FT_MAX_WINDOW,
    FT_REFERENCE_FILE,
    FT_SEARCH_URL,
    FT_TOKEN_URL,
    FranceTravailCollector,
    FranceTravailCrosswalk,
    crosswalk_reference_hashes,
    departement_from_code_postal,
    departement_from_commune,
    departement_from_libelle,
    france_travail_credentials,
    parse_content_range,
    parse_ft_datetime,
)
from scrapers.retry import RetryPolicy

KEY = b"test-only-key-with-at-least-32-bytes"
CLIENT_ID = "PAR_testapp_0123456789abcdef"
CLIENT_SECRET = "0123456789abcdef"

HEADER = "source_type,source_code,nuts_code,nuts_label,source_url,source_version\n"
ROWS = (
    "departement,64,FRI15,Pyrénées-Atlantiques,https://example.invalid,2026-08-22\n"
    "departement,75,FR101,Paris,https://example.invalid,2026-08-22\n"
    "departement,2A,FRM01,Corse-du-Sud,https://example.invalid,2026-08-22\n"
    "departement,2B,FRM02,Haute-Corse,https://example.invalid,2026-08-22\n"
    "departement,971,FRY10,Guadeloupe,https://example.invalid,2026-08-22\n"
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(coro)


@pytest.fixture
def reference_dir(tmp_path: Path) -> Path:
    (tmp_path / FT_REFERENCE_FILE).write_text(HEADER + ROWS, encoding="utf-8")
    return tmp_path


def offre(
    offer_id: str,
    *,
    created: str = "2026-08-22T18:04:03.871Z",
    updated: str = "2026-08-22T18:04:04.437Z",
    postes: int = 1,
    rome: str | None = "I1309",
    lieu: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One search result carrying the PII the allowlist must never let through."""
    if lieu is None:
        lieu = {"libelle": "64 - Bayonne", "codePostal": "64100", "commune": "64102"}
    return {
        "id": offer_id,
        "intitule": "Private Job Title",
        "description": "Very long private description, contact Jean Dupont on "
        "+33 6 12 34 56 78 or private.person@example.com",
        "dateCreation": created,
        "dateActualisation": updated,
        "romeCode": rome,
        "romeLibelle": "Electricien / Electricienne de maintenance",
        "appellationlibelle": "Electrotechnicien / Electrotechnicienne de maintenance",
        "entreprise": {
            "nom": "Private Employer SARL",
            "description": "Private employer description",
            "url": "https://private-employer.example.com",
            "entrepriseAdaptee": False,
        },
        "contact": {
            "nom": "Jean Dupont",
            "coordonnees1": "private.person@example.com",
            "telephone": "0612345678",
            "urlPostulation": "https://private-employer.example.com/apply/1",
        },
        "origineOffre": {
            "origine": "1",
            "urlOrigine": "https://candidat.francetravail.fr/offres/recherche/detail/212TTKM",
        },
        "lieuTravail": {**lieu, "latitude": 43.49, "longitude": -1.47},
        "salaire": {"libelle": "Annuel de 30000.0 Euros à 35000.0 Euros sur 12.0 mois"},
        "typeContrat": "CDI",
        "natureContrat": "Contrat travail",
        "dureeTravailLibelle": "39H/semaine\nTravail en journée",
        "nombrePostes": postes,
        "agence": {"courriel": "agence.private@francetravail.fr"},
        "qualificationLibelle": "Technicien",
    }


def token_response(expires_in: int = 1499, token: str = "token-1") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "scope": "api_offresdemploiv2 o2dsoffre",
            "expires_in": expires_in,
            "token_type": "Bearer",
            "access_token": token,
        },
    )


def search_response(
    results: list[dict[str, Any]], *, start: int = 0, total: int = 1
) -> httpx.Response:
    end = start + max(0, len(results) - 1)
    return httpx.Response(
        206,
        json={"filtresPossibles": [], "resultats": results},
        headers={"Content-Range": f"offres {start}-{end}/{total}", "accept-range": "150"},
    )


def make_collector(
    reference_dir: Path,
    *,
    max_pages: int | None = None,
    segments: list[dict[str, str]] | None = None,
    policy: RetryPolicy | None = None,
    window: int = FT_MAX_WINDOW,
    monotonic: Any = None,
) -> FranceTravailCollector:
    return FranceTravailCollector(
        scope_id="fr-all-active",
        sweep_id="20260822T000000Z",
        observed_at=datetime(2026, 8, 22, tzinfo=UTC),
        hmac_key=KEY,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        reference_dir=reference_dir,
        window=window,
        max_pages=max_pages,
        segments=segments,
        pacing_interval=0.0,
        policy=policy,
        **({"monotonic": monotonic} if monotonic is not None else {}),
    )


def collect(collector: FranceTravailCollector) -> list[NormalizedRecord]:
    async def go() -> list[NormalizedRecord]:
        async with collector:
            return [record async for record in collector.collect()]

    return run(go())


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


def test_credentials_loaded_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_ID", "env-id")
    monkeypatch.setenv("FRANCE_TRAVAIL_CLIENT_SECRET", "env-secret")
    assert france_travail_credentials() == ("env-id", "env-secret")


def test_credentials_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_ID", raising=False)
    monkeypatch.delenv("FRANCE_TRAVAIL_CLIENT_SECRET", raising=False)
    # .env may carry real credentials; force the dotenv reader to report none.
    monkeypatch.setattr("scrapers.france_travail.read_dotenv_value", lambda _name: None)
    with pytest.raises(RuntimeError, match="FRANCE_TRAVAIL_CLIENT_ID"):
        france_travail_credentials()


# ---------------------------------------------------------------------------
# Token flow
# ---------------------------------------------------------------------------


def test_token_minted_once_and_reused(reference_dir: Path) -> None:
    with respx.mock:
        token_route = respx.post(FT_TOKEN_URL).mock(return_value=token_response())

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["Authorization"] == "Bearer token-1"
            start = int(request.url.params["range"].split("-")[0])
            return search_response(
                [offre(f"native-{start + i}") for i in range(3)], start=start, total=3
            )

        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(reference_dir, segments=[{}, {"departement": "75"}])
        records = collect(collector)

    assert len(records) == 3  # second segment repeats the same ids -> deduped
    assert token_route.call_count == 1
    assert collector.token_requests == 1


def test_token_request_body_matches_documented_contract(reference_dir: Path) -> None:
    with respx.mock:
        token_route = respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response([offre("native-1")], total=1)
        )
        collect(make_collector(reference_dir, segments=[{}]))

    request = token_route.calls[0].request
    body = dict(pair.split("=", 1) for pair in request.content.decode().split("&"))
    assert request.url.params["realm"] == "/partenaire"
    assert body["grant_type"] == "client_credentials"
    assert body["client_id"] == CLIENT_ID
    assert body["client_secret"] == CLIENT_SECRET
    assert body["scope"] == "api_offresdemploiv2+o2dsoffre"
    assert request.headers["Content-Type"] == "application/x-www-form-urlencoded"


def test_expired_ttl_mints_a_new_token(reference_dir: Path) -> None:
    """A token whose TTL elapsed is replaced without waiting for a 401."""
    # First reading stamps the first token's expiry; every later reading is past it.
    clock = iter([0.0, *([10_000.0] * 20)])

    with respx.mock:
        token_route = respx.post(FT_TOKEN_URL).mock(
            side_effect=[token_response(token="token-1"), token_response(token="token-2")]
        )
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers["Authorization"])
            return search_response([offre("native-1")], total=1)

        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(
            reference_dir,
            segments=[{}, {"departement": "75"}],
            monotonic=lambda: next(clock),
        )
        collect(collector)

    assert token_route.call_count == 2
    assert seen == ["Bearer token-1", "Bearer token-2"]


def test_401_refreshes_token_and_replays_request(reference_dir: Path) -> None:
    calls: list[str] = []

    with respx.mock:
        token_route = respx.post(FT_TOKEN_URL).mock(
            side_effect=[token_response(token="stale"), token_response(token="fresh")]
        )

        def handler(request: httpx.Request) -> httpx.Response:
            auth = request.headers["Authorization"]
            calls.append(auth)
            if auth == "Bearer stale":
                return httpx.Response(401, headers={"WWW-Authenticate": "Bearer"}, content=b"")
            return search_response([offre("native-1")], total=1)

        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(reference_dir, segments=[{}])
        records = collect(collector)

    assert calls == ["Bearer stale", "Bearer fresh"]
    assert token_route.call_count == 2
    assert collector.token_requests == 2
    assert len(records) == 1


def test_persistent_401_raises(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(return_value=httpx.Response(401, content=b""))
        with pytest.raises(httpx.HTTPStatusError):
            collect(make_collector(reference_dir, segments=[{}]))


def test_token_endpoint_without_access_token_raises(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=httpx.Response(200, json={"expires_in": 1499}))
        with pytest.raises(RuntimeError, match="no access_token"):
            collect(make_collector(reference_dir, segments=[{}]))


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


def test_paginates_range_windows_and_normalizes(reference_dir: Path) -> None:
    total = 275

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = (int(part) for part in request.url.params["range"].split("-"))
        assert end - start + 1 == FT_MAX_WINDOW
        count = min(FT_MAX_WINDOW, max(0, total - start))
        return search_response(
            [offre(f"native-{start + i}") for i in range(count)], start=start, total=total
        )

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(reference_dir, segments=[{}])
        records = collect(collector)

    assert len(records) == total
    assert collector.completed_pages == 2
    assert collector.total_pages == 2
    assert collector.total_elements == total
    assert collector.planned_pages == 2  # ceil(275 / 150)
    assert collector.advertised_count == total
    assert all(len(record.source_id) == 64 for record in records)
    assert all(record.source == "francetravail" for record in records)
    assert all(record.country == "FR" for record in records)
    assert all(record.lang == "fr" and record.source_language == "fr" for record in records)
    assert all(record.nuts_version == "NUTS-2024" for record in records)
    assert all(record.esco_version == "1.2.1" for record in records)
    assert all(record.jobtech_taxonomy_version == "" for record in records)
    assert all(record.number_of_vacancies == 1 for record in records)
    assert all(record.removed_at is None for record in records)
    assert all(
        record.first_published == datetime(2026, 8, 22, 18, 4, 3, 871000, tzinfo=UTC)
        for record in records
    )
    assert all(
        record.last_modified == datetime(2026, 8, 22, 18, 4, 4, 437000, tzinfo=UTC)
        for record in records
    )


def test_stops_at_the_3000_start_cap(reference_dir: Path) -> None:
    """The API rejects a start position above 3000, so one query caps at 3,150."""
    starts: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["range"].split("-")[0])
        starts.append(start)
        assert start <= FT_MAX_START
        return search_response(
            [offre(f"native-{start + i}") for i in range(FT_MAX_WINDOW)],
            start=start,
            total=500_000,
        )

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(reference_dir, segments=[{}])
        records = collect(collector)

    assert starts[0] == 0
    assert starts[-1] == FT_MAX_START
    assert len(starts) == 21
    assert len(records) == 21 * FT_MAX_WINDOW  # 3,150 offers per query
    assert collector.planned_pages == 21
    assert collector.advertised_count == 500_000


def test_short_window_ends_the_segment(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        route = respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response([offre("native-1"), offre("native-2")], total=2)
        )
        collector = make_collector(reference_dir, segments=[{}])
        records = collect(collector)

    assert route.call_count == 1
    assert len(records) == 2
    assert collector.completed_pages == 1


def test_empty_window_ends_the_segment(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=httpx.Response(
                206, json={"resultats": []}, headers={"Content-Range": "offres 0-0/0"}
            )
        )
        collector = make_collector(reference_dir, segments=[{}])
        records = collect(collector)

    assert records == []
    assert collector.completed_pages == 1


def test_204_no_content_is_tolerated(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(return_value=httpx.Response(204))
        collector = make_collector(reference_dir, segments=[{}])
        assert collect(collector) == []


def test_max_pages_budget_stops_early(reference_dir: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        start = int(request.url.params["range"].split("-")[0])
        return search_response(
            [offre(f"native-{start + i}") for i in range(FT_MAX_WINDOW)],
            start=start,
            total=500_000,
        )

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(reference_dir, segments=[{}], max_pages=3)
        records = collect(collector)

    assert collector.completed_pages == 3
    assert collector.total_pages == 3
    assert len(records) == 3 * FT_MAX_WINDOW
    assert collector.total_elements == len(records)


def test_departement_segments_dedupe_on_source_id(reference_dir: Path) -> None:
    """Overlapping segments never write the same offer twice."""
    seen_params: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        dep = request.url.params.get("departement", "")
        seen_params.append(dep)
        shared = offre("shared-1")
        return search_response([shared, offre(f"only-{dep or 'all'}")], total=2)

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(
            reference_dir, segments=[{}, {"departement": "75"}, {"departement": "64"}]
        )
        records = collect(collector)

    assert seen_params == ["", "75", "64"]
    source_ids = [record.source_id for record in records]
    assert len(source_ids) == 4  # 1 shared + 3 segment-only
    assert len(set(source_ids)) == 4


def test_default_segments_cover_every_departement(reference_dir: Path) -> None:
    """Without explicit segments the sweep queries every crosswalk département."""
    queried: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        queried.append(request.url.params.get("departement", ""))
        return search_response([offre(f"native-{len(queried)}")], total=1)

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collect(make_collector(reference_dir))

    assert queried == ["", "2A", "2B", "64", "75", "971"]


def test_retries_429_honoring_retry_after(reference_dir: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"message": "throttled"})
        return search_response([offre("native-1")], total=1)

    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(side_effect=handler)
        collector = make_collector(
            reference_dir,
            segments=[{}],
            policy=RetryPolicy(max_attempts=3, base_delay=0.01, jitter=0.0),
        )
        records = collect(collector)

    assert calls == 2
    assert len(records) == 1


def test_server_error_propagates(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=httpx.Response(500, json={"message": "boom"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            collect(
                make_collector(
                    reference_dir,
                    segments=[{}],
                    policy=RetryPolicy(max_attempts=1, base_delay=0.0, jitter=0.0),
                )
            )


# ---------------------------------------------------------------------------
# PII isolation
# ---------------------------------------------------------------------------


def test_pii_never_reaches_output(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response([offre("native-1")], total=1)
        )
        records = collect(make_collector(reference_dir, segments=[{}]))

    dumped = json.dumps(records[0].model_dump_ndjson(), ensure_ascii=False)
    for forbidden in (
        "Private Job Title",
        "private.person@example.com",
        "Jean Dupont",
        "0612345678",
        "+33 6 12 34 56 78",
        "Private Employer SARL",
        "private-employer.example.com",
        "candidat.francetravail.fr",
        "Bayonne",
        "64100",  # postcode (licence article 7)
        "64102",  # commune INSEE code (licence article 7)
        "agence.private",
        "Annuel de 30000.0",
        "native-1",  # native identifier never leaves the worktree
    ):
        assert forbidden not in dumped, forbidden
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


def test_source_ids_unique_per_offer(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response(
                [offre("native-1"), offre("native-2"), offre("native-3")], total=3
            )
        )
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert len({record.source_id for record in records}) == 3
    assert all(len(record.source_id) == 64 for record in records)


def test_missing_id_fails_loudly(reference_dir: Path) -> None:
    broken = offre("native-1")
    del broken["id"]
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response([broken], total=1)
        )
        with pytest.raises(ValueError):
            collect(make_collector(reference_dir, segments=[{}]))


# ---------------------------------------------------------------------------
# Normalization details
# ---------------------------------------------------------------------------


def test_nombre_postes_becomes_number_of_vacancies(reference_dir: Path) -> None:
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response(
                [offre("native-1", postes=4), offre("native-2", postes=0)], total=2
            )
        )
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert [record.number_of_vacancies for record in records] == [4, 0]


def test_missing_nombre_postes_defaults_to_one(reference_dir: Path) -> None:
    item = offre("native-1")
    del item["nombrePostes"]
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(return_value=search_response([item], total=1))
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert records[0].number_of_vacancies == 1


def test_rome_code_present_is_unmapped_absent_is_not_present(reference_dir: Path) -> None:
    """ROME is exposed on every offer; only the ESCO crosswalk is deferred."""
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(
            return_value=search_response([offre("native-1"), offre("native-2", rome=None)], total=2)
        )
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert records[0].occupation_mapping_status == "unmapped"
    assert records[1].occupation_mapping_status == "not_present"
    assert all(record.occupation_mapping_method == "deferred_rome_to_esco" for record in records)
    assert all(record.esco_occupation_uri is None for record in records)
    assert all(record.skill_mappings == [] for record in records)


def test_missing_dates_are_null(reference_dir: Path) -> None:
    item = offre("native-1", created="", updated="")
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(return_value=search_response([item], total=1))
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert records[0].first_published is None
    assert records[0].last_modified is None


def test_parse_ft_datetime() -> None:
    assert parse_ft_datetime("2026-08-22T18:04:03.871Z") == datetime(
        2026, 8, 22, 18, 4, 3, 871000, tzinfo=UTC
    )
    assert parse_ft_datetime("2026-08-22T18:04:03Z") == datetime(2026, 8, 22, 18, 4, 3, tzinfo=UTC)
    assert parse_ft_datetime(None) is None
    assert parse_ft_datetime("") is None
    assert parse_ft_datetime("garbage") is None


def test_parse_content_range() -> None:
    assert parse_content_range("offres 0-149/503356") == 503356
    assert parse_content_range("offres 3000-3149/503356") == 503356
    assert parse_content_range(None) is None
    assert parse_content_range("bytes 0-149/1000") is None
    assert parse_content_range("garbage") is None


# ---------------------------------------------------------------------------
# Region crosswalk
# ---------------------------------------------------------------------------


def test_commune_insee_is_mapped(reference_dir: Path) -> None:
    resolution = FranceTravailCrosswalk(reference_dir).resolve(
        commune="64102", code_postal="64100", libelle="64 - Bayonne"
    )
    assert resolution.nuts_code == "FRI15"
    assert resolution.nuts_label == "Pyrénées-Atlantiques"
    assert resolution.status == "mapped"
    assert resolution.method == "ft_commune_insee_departement_nuts3"


def test_code_postal_only_is_low_confidence(reference_dir: Path) -> None:
    resolution = FranceTravailCrosswalk(reference_dir).resolve(code_postal="75012")
    assert resolution.nuts_code == "FR101"
    assert resolution.status == "low_confidence"
    assert resolution.method == "ft_code_postal_departement_nuts3"


def test_libelle_prefix_only_is_low_confidence(reference_dir: Path) -> None:
    resolution = FranceTravailCrosswalk(reference_dir).resolve(libelle="971 - Guadeloupe")
    assert resolution.nuts_code == "FRY10"
    assert resolution.status == "low_confidence"
    assert resolution.method == "ft_lieu_libelle_departement_nuts3"


def test_corsican_postcode_is_ambiguous(reference_dir: Path) -> None:
    """20xxx postcodes span both 2A and 2B, so no NUTS code is emitted."""
    resolution = FranceTravailCrosswalk(reference_dir).resolve(code_postal="20000")
    assert resolution.nuts_code is None
    assert resolution.status == "ambiguous"
    assert resolution.method == "ft_code_postal_corse_2a_2b"


def test_corsican_commune_is_mapped(reference_dir: Path) -> None:
    resolution = FranceTravailCrosswalk(reference_dir).resolve(
        commune="2A004", code_postal="20000", libelle="2A - AJACCIO"
    )
    assert resolution.nuts_code == "FRM01"
    assert resolution.status == "mapped"


def test_region_only_and_foreign_locations_are_unmapped(reference_dir: Path) -> None:
    crosswalk = FranceTravailCrosswalk(reference_dir)
    region_only = crosswalk.resolve(libelle="Île-de-France")
    foreign = crosswalk.resolve(libelle="Monaco", code_postal="99999")
    for resolution in (region_only, foreign):
        assert resolution.nuts_code is None
        assert resolution.status == "unmapped"
        assert resolution.method == "not_available"


def test_unknown_departement_falls_through(reference_dir: Path) -> None:
    resolution = FranceTravailCrosswalk(reference_dir).resolve(commune="33063")
    assert resolution.status == "unmapped"


def test_departement_from_commune() -> None:
    assert departement_from_commune("64102") == "64"
    assert departement_from_commune("2A004") == "2A"
    assert departement_from_commune("2b355") == "2B"
    assert departement_from_commune("97113") == "971"
    assert departement_from_commune("97423") == "974"
    assert departement_from_commune(None) is None
    assert departement_from_commune("") is None
    assert departement_from_commune("X") is None
    assert departement_from_commune("XY123") is None


def test_departement_from_code_postal() -> None:
    assert departement_from_code_postal("64100") == ("64", False)
    assert departement_from_code_postal("97190") == ("971", False)
    assert departement_from_code_postal("20000") == (None, True)
    assert departement_from_code_postal("20290") == (None, True)
    assert departement_from_code_postal(None) == (None, False)
    assert departement_from_code_postal("ABCDE") == (None, False)


def test_departement_from_libelle() -> None:
    assert departement_from_libelle("64 - Bayonne") == "64"
    assert departement_from_libelle("30 - Gard") == "30"
    assert departement_from_libelle("2A - AJACCIO") == "2A"
    assert departement_from_libelle("971 - LE GOSIER") == "971"
    assert departement_from_libelle("Île-de-France") is None
    assert departement_from_libelle("Monaco") is None
    assert departement_from_libelle(None) is None


def test_offer_without_lieu_travail_is_unmapped(reference_dir: Path) -> None:
    item = offre("native-1")
    del item["lieuTravail"]
    with respx.mock:
        respx.post(FT_TOKEN_URL).mock(return_value=token_response())
        respx.get(url__startswith=FT_SEARCH_URL).mock(return_value=search_response([item], total=1))
        records = collect(make_collector(reference_dir, segments=[{}]))

    assert records[0].nuts_code is None
    assert records[0].region_mapping_status == "unmapped"


def test_missing_reference_file_fails(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="francetravail_departements"):
        FranceTravailCrosswalk(tmp_path)


def test_empty_reference_file_fails(tmp_path: Path) -> None:
    (tmp_path / FT_REFERENCE_FILE).write_text(HEADER, encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        FranceTravailCrosswalk(tmp_path)


def test_crosswalk_reference_hashes(reference_dir: Path) -> None:
    digest = crosswalk_reference_hashes(reference_dir)
    assert digest.startswith(f"{FT_REFERENCE_FILE}:")
    assert len(digest.split(":")[1]) == 64


def test_short_hmac_key_rejected(reference_dir: Path) -> None:
    with pytest.raises(ValueError, match="hmac_key"):
        FranceTravailCollector(
            scope_id="fr-all-active",
            sweep_id="20260822T000000Z",
            observed_at=datetime(2026, 8, 22, tzinfo=UTC),
            hmac_key=b"too-short",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            reference_dir=reference_dir,
        )


def test_missing_client_credentials_rejected(reference_dir: Path) -> None:
    with pytest.raises(ValueError, match="client_id and client_secret"):
        FranceTravailCollector(
            scope_id="fr-all-active",
            sweep_id="20260822T000000Z",
            observed_at=datetime(2026, 8, 22, tzinfo=UTC),
            hmac_key=KEY,
            client_id="",
            client_secret="",
            reference_dir=reference_dir,
        )
