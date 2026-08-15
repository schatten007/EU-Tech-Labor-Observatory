import json
import sys
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any, Never
from urllib.error import HTTPError

import duckdb
from pytest import MonkeyPatch

from scripts import collect, probe, publish, sanitize

KEY = b"test-only-key-with-at-least-32-bytes"


def hit(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "country_code": "SE",
        "publication_date": "2026-08-13T12:00:00Z",
        "number_of_vacancies": 1,
    }


def fake_clock() -> datetime:
    return datetime(2026, 8, 15, 0, 0, tzinfo=UTC)


def fail_network(*args: object, **kwargs: object) -> Never:
    raise AssertionError("default command attempted network access")


def test_probe_defaults_offline(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["probe.py"])
    monkeypatch.setattr(probe, "urlopen", fail_network)

    assert probe.main() == 2


def test_sanitize_record_keeps_analysis_without_identifiers() -> None:
    row = {
        "source": "example",
        "source_id": "native-42",
        "observed_at": "2026-08-13T12:00:00Z",
        "country": "SE",
        "skill_uris": ["urn:skill:python"],
        "title": "Private title",
        "text": "Private description",
        "employer": "Private employer",
        "contact": "Private contact",
        "url": "private-url",
    }
    key = KEY

    safe = sanitize.sanitize_record(row, key)

    assert safe == sanitize.sanitize_record(row, key)
    assert safe["source_id"] != row["source_id"]
    assert safe.keys() == {"source", "source_id", "observed_at", "country", "skill_uris"}


def test_collect_jobtech_writes_sanitized_observations(tmp_path: Path) -> None:
    source = tmp_path / "jobtech.json"
    target = tmp_path / "observations.ndjson"
    source.write_text(
        json.dumps(
            {
                "hits": [
                    {
                        "id": "native-42",
                        "headline": "Private title",
                        "description": {"text": "Private description"},
                        "employer": {"name": "Private employer"},
                        "country_code": "SE",
                        "publication_date": "2026-08-13T12:00:00Z",
                        "number_of_vacancies": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert collect.collect_jobtech(source, target, "2026-08-13T13:00:00Z", b"k" * 32) == 1
    row = json.loads(target.read_text(encoding="utf-8"))

    assert row["source"] == "jobtech"
    assert row["observed_at"] == "2026-08-13T13:00:00Z"
    assert row["number_of_vacancies"] == 2
    assert len(row["source_id"]) == 64
    assert row["nuts_code"] is None
    assert row["esco_occupation_uri"] is None
    assert "headline" not in row
    assert "employer" not in row
    assert "description" not in row


def test_jobtech_normalizer_requires_explicit_sweden_country() -> None:
    malformed = hit("missing-country")
    malformed.pop("country_code")

    try:
        collect.normalize_jobtech_hit(malformed, "2026-08-15T00:00:00Z")
    except ValueError as error:
        assert "country_code SE" in str(error)
    else:
        raise AssertionError("missing country must not be inferred as Sweden")


def test_collect_jobtech_sweep_paginates_and_publishes_manifest(tmp_path: Path) -> None:
    responses: dict[int, dict[str, Any]] = {
        0: {"total": {"value": 3}, "hits": [hit("one"), hit("two")]},
        2: {"total": {"value": 3}, "hits": [hit("three")]},
    }
    urls: list[str] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del timeout
        urls.append(url)
        offset = int(url.split("offset=")[1].split("&")[0])
        return responses[offset]

    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        observed_at="2026-08-15T00:00:00Z",
        page_size=2,
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-test",
    )

    assert manifest["status"] == "complete"
    assert manifest["expected_pages"] == 2
    assert manifest["row_count"] == 3
    assert manifest["schema_version"] == 2
    assert manifest["approval_status"] == "approved"
    assert manifest["expected_country"] == "SE"
    assert manifest["licence_reference"] == collect.JOBTECH_LICENCE_REFERENCE
    assert len(urls) == 2
    partition = tmp_path / "collections" / "jobtech" / manifest["scope_id"] / manifest["sweep_id"]
    assert (partition / "observations.ndjson").exists()
    assert (
        json.loads((partition / "manifest.json").read_text(encoding="utf-8"))["status"]
        == "complete"
    )


def test_collect_jobtech_sweep_supports_empty_complete_sweep(tmp_path: Path) -> None:
    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        observed_at="2026-08-15T00:00:00Z",
        transport=lambda url, timeout: {"total": {"value": 0}, "hits": []},
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-empty",
    )

    assert manifest["status"] == "complete"
    assert manifest["expected_pages"] == 1
    assert manifest["row_count"] == 0
    partition = tmp_path / "collections" / "jobtech" / manifest["scope_id"] / manifest["sweep_id"]
    assert (partition / "observations.ndjson").read_text(encoding="utf-8") == ""


def test_collect_jobtech_sweep_retries_transient_failure(tmp_path: Path) -> None:
    attempts = 0
    sleeps: list[float] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TimeoutError("temporary")
        return {"total": {"value": 1}, "hits": [hit("one")]}

    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        policy=collect.RetryPolicy(max_attempts=2, deadline_s=10, jitter_s=0),
        transport=transport,
        sleeper=sleeps.append,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-retry",
    )

    assert manifest["status"] == "complete"
    assert attempts == 2
    assert sleeps == [1.0]


def test_collect_jobtech_sweep_caps_request_timeout_to_retry_deadline(tmp_path: Path) -> None:
    timeouts: list[float] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del url
        timeouts.append(timeout)
        return {"total": {"value": 0}, "hits": []}

    collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        policy=collect.RetryPolicy(timeout_s=30, deadline_s=5),
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-deadline",
    )
    assert timeouts == [5.0]


def test_hmac_key_version_binds_the_secret_identity(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.setenv("OBSERVATORY_HMAC_KEY_VERSION", "v1")
    collect._verify_key_identity(tmp_path, b"a" * 32, "v1")
    try:
        collect._verify_key_identity(tmp_path, b"b" * 32, "v1")
    except collect.CollectionError as error:
        assert "does not match" in str(error)
    else:
        raise AssertionError("reusing a key version with another secret should fail")


def test_collect_jobtech_sweep_rejects_duplicate_ids_and_keeps_failed_state(tmp_path: Path) -> None:
    def transport(url: str, timeout: float) -> dict[str, Any]:
        del url, timeout
        return {"total": {"value": 2}, "hits": [hit("same"), hit("same")]}

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            page_size=2,
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-duplicate",
        )
    except collect.CollectionError as error:
        assert "duplicate" in str(error)
    else:
        raise AssertionError("duplicate page should fail")

    state = tmp_path / "collection-state" / "20260815T000000Z-duplicate" / "manifest.json"
    assert json.loads(state.read_text(encoding="utf-8"))["status"] == "failed"


def test_collect_jobtech_sweep_resumes_completed_pages(tmp_path: Path) -> None:
    calls: list[int] = []
    responses: dict[int, dict[str, Any]] = {
        0: {"total": {"value": 2}, "hits": [hit("one")]},
        1: {"total": {"value": 2}, "hits": [hit("two")]},
    }

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del timeout
        offset = int(url.split("offset=")[1].split("&")[0])
        calls.append(offset)
        if offset == 1 and calls.count(1) == 1:
            raise TimeoutError("interrupt page two")
        return responses[offset]

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            query="resume-query",
            observed_at="2026-08-15T00:00:00Z",
            page_size=1,
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-resume",
            policy=collect.RetryPolicy(max_attempts=1, deadline_s=10),
        )
    except collect.CollectionError:
        pass
    else:
        raise AssertionError("first run should fail")

    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        transport=transport,
        sleeper=lambda _: None,
        clock=lambda: datetime(2026, 8, 16, tzinfo=UTC),
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-resume",
        policy=collect.RetryPolicy(max_attempts=1, deadline_s=10),
        resume=True,
    )
    assert manifest["status"] == "complete"
    assert manifest["observed_at"] == "2026-08-15T00:00:00Z"
    assert calls == [0, 1, 1]


def test_collect_jobtech_recorded_output_is_not_truncated_on_late_error(tmp_path: Path) -> None:
    source = tmp_path / "jobtech.json"
    target = tmp_path / "observations.ndjson"
    target.write_text("sentinel\n", encoding="utf-8")
    source.write_text(json.dumps({"hits": [hit("one"), {"id": ""}]}), encoding="utf-8")

    try:
        collect.collect_jobtech(source, target, "2026-08-15T00:00:00Z", KEY)
    except ValueError as error:
        assert "non-empty id" in str(error)
    else:
        raise AssertionError("malformed late row should fail")
    assert target.read_text(encoding="utf-8") == "sentinel\n"


def test_recorded_output_is_explicitly_non_publishable(tmp_path: Path) -> None:
    source = tmp_path / "jobtech.json"
    target = tmp_path / "observations.ndjson"
    observed_at = "2026-08-15T00:00:00Z"
    source.write_text(json.dumps({"hits": [hit("one")]}), encoding="utf-8")

    count = collect.collect_jobtech(
        source,
        target,
        observed_at,
        KEY,
    )
    row = json.loads(target.read_text(encoding="utf-8"))
    assert count == 1
    assert "scope_id" not in row
    assert "sweep_id" not in row
    assert not target.with_suffix(".manifest.json").exists()


def test_collect_jobtech_sweep_is_idempotent_for_completed_partition(tmp_path: Path) -> None:
    calls = 0

    def transport(url: str, timeout: float) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"total": {"value": 1}, "hits": [hit("one")]}

    first = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-idempotent",
    )
    second = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-idempotent",
    )
    assert first["partition_id"] == second["partition_id"]
    assert calls == 1


def test_collect_jobtech_sweep_honors_retry_after(tmp_path: Path) -> None:
    attempts = 0
    sleeps: list[float] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        nonlocal attempts
        del timeout
        attempts += 1
        if attempts == 1:
            headers = Message()
            headers["Retry-After"] = "3"
            raise HTTPError(url, 429, "rate limited", headers, None)
        return {"total": {"value": 0}, "hits": []}

    collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        transport=transport,
        sleeper=sleeps.append,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        random_value=lambda: 0.0,
        sweep_id="20260815T000000Z-rate-limit",
    )
    assert attempts == 2
    assert sleeps == [3.0]


def test_collect_jobtech_sweep_does_not_retry_bad_request(tmp_path: Path) -> None:
    attempts = 0

    def transport(url: str, timeout: float) -> dict[str, Any]:
        nonlocal attempts
        del timeout
        attempts += 1
        raise HTTPError(url, 400, "bad query", Message(), None)

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-bad-request",
        )
    except collect.CollectionError:
        pass
    else:
        raise AssertionError("HTTP 400 should fail")
    assert attempts == 1


def test_collect_jobtech_sweep_rejects_lock_contention(tmp_path: Path) -> None:
    lock = tmp_path / "collection-state" / "20260815T000000Z-locked.lock"
    lock.parent.mkdir(parents=True)
    lock.write_text("held", encoding="utf-8")

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            transport=lambda url, timeout: {"total": {"value": 0}, "hits": []},
            clock=fake_clock,
            sweep_id="20260815T000000Z-locked",
        )
    except collect.CollectionError as error:
        assert "already locked" in str(error)
    else:
        raise AssertionError("existing lock should fail")


def test_collect_jobtech_sweep_detects_completed_partition_tampering(tmp_path: Path) -> None:
    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        transport=lambda url, timeout: {"total": {"value": 1}, "hits": [hit("one")]},
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-tamper",
    )
    partition = tmp_path / "collections" / "jobtech" / manifest["scope_id"] / manifest["sweep_id"]
    (partition / "observations.ndjson").write_text("tampered\n", encoding="utf-8")

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            transport=lambda url, timeout: {"total": {"value": 1}, "hits": [hit("one")]},
            clock=fake_clock,
            sweep_id="20260815T000000Z-tamper",
        )
    except collect.CollectionError as error:
        assert "hash mismatch" in str(error)
    else:
        raise AssertionError("tampered completed partition should fail")


def test_publish_builds_aggregate_page(tmp_path: Path) -> None:
    database = tmp_path / "site.duckdb"
    target = tmp_path / "index.html"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        create table labour_demand_latest as
        select 'jobtech'::varchar as source,
               'jobtech-scope'::varchar as scope_id,
               'sample/one'::varchar as partition_id,
               'sweep-one'::varchar as sweep_id,
               'run-one'::varchar as run_id,
               'SE'::varchar as country,
               timestamp '2026-08-06 09:00:00' as observed_at,
               timestamp '2026-08-06 08:59:00' as started_at,
               timestamp '2026-08-06 09:01:00' as completed_at,
               'complete'::varchar as status,
               'v1'::varchar as hmac_key_version,
               'JobSearch current ads'::varchar as source_version,
               'https://data.jobtechdev.se/dataservice/jobsearch/'::varchar as licence_reference,
               'official-public-api'::varchar as access_method,
               'approved'::varchar as approval_status,
               'Keyword-scoped'::varchar as coverage_limitations,
               3.0::double as freshness_age_hours,
               'fresh'::varchar as freshness_status,
               'covered'::varchar as coverage_status,
               1::bigint as active_postings
        """
    )
    connection.close()

    assert publish.build_site(database, target) == 1
    page = target.read_text(encoding="utf-8")
    assert "EU Tech Labour Observatory" in page
    assert "jobtech" in page
    assert "Counts are not summed or deduplicated across sources" in page
    assert "official-public-api" in page
    assert "native-42" not in page


def test_publish_handles_zero_only_aggregate(tmp_path: Path) -> None:
    database = tmp_path / "zero.duckdb"
    target = tmp_path / "zero.html"
    connection = duckdb.connect(str(database))
    connection.execute(
        """
        create table labour_demand_latest as
        select 'jobtech'::varchar as source,
               'scope'::varchar as scope_id,
               'partition'::varchar as partition_id,
               'sweep'::varchar as sweep_id,
               'run'::varchar as run_id,
               'SE'::varchar as country,
               timestamp '2026-08-06 09:00:00' as observed_at,
               timestamp '2026-08-06 08:59:00' as started_at,
               timestamp '2026-08-06 09:01:00' as completed_at,
               'complete'::varchar as status,
               'v1'::varchar as hmac_key_version,
               'JobSearch current ads'::varchar as source_version,
               'https://data.jobtechdev.se/dataservice/jobsearch/'::varchar as licence_reference,
               'official-public-api'::varchar as access_method,
               'approved'::varchar as approval_status,
               'Keyword-scoped'::varchar as coverage_limitations,
               3.0::double as freshness_age_hours,
               'fresh'::varchar as freshness_status,
               'covered'::varchar as coverage_status,
               0::bigint as active_postings
        """
    )
    connection.close()

    assert publish.build_site(database, target) == 1
    page = target.read_text(encoding="utf-8")
    assert "SE" in page
    assert ">0<" in page
