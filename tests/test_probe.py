import json
import re
import sys
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from typing import Any, Never
from urllib.error import HTTPError

import duckdb
from pytest import MonkeyPatch

from scripts import collect, enrich, evaluate, probe, publish, release_check, sanitize

KEY = b"test-only-key-with-at-least-32-bytes"


def hit(identifier: str) -> dict[str, object]:
    return {
        "id": identifier,
        "country_code": "SE",
        "publication_date": "2026-08-13T12:00:00Z",
        "number_of_vacancies": 1,
    }


def data_it_hit(identifier: str, concept_id: str | None = None) -> dict[str, object]:
    """A hit as the occupation-field search returns it: the filtered field is echoed back."""
    return {
        **hit(identifier),
        "occupation_field": {"concept_id": concept_id or collect.JOBTECH_DATA_IT_FIELD},
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


def test_jobtech_normalizer_accepts_the_live_country_code_shape() -> None:
    """The live API omits country_code and nests SCB code 199, not ISO SE, in the address."""
    live_shape = hit("live-shape")
    live_shape.pop("country_code")
    live_shape["workplace_address"] = {
        "municipality_code": "1380",
        "region_code": "13",
        "country": "Sverige",
        "country_code": collect.JOBTECH_SWEDEN_COUNTRY_CODE,
    }

    row = collect.normalize_jobtech_hit(live_shape, "2026-08-15T00:00:00Z")

    assert row["country"] == collect.JOBTECH_EXPECTED_COUNTRY


def test_jobtech_normalizer_rejects_a_foreign_country_code() -> None:
    """Platsbanken answers Swedish keywords with a few foreign ads; none may be collected."""
    foreign = hit("foreign")
    foreign.pop("country_code")
    foreign["workplace_address"] = {"country": "Frankrike", "country_code": "60"}

    try:
        collect.normalize_jobtech_hit(foreign, "2026-08-15T00:00:00Z")
    except ValueError as error:
        assert "country_code SE" in str(error)
    else:
        raise AssertionError("a foreign posting must not be collected")


def test_jobtech_scope_filters_the_search_to_sweden() -> None:
    """The country filter must be part of the requested scope, not just a post-hoc check."""
    _, _, scope_json = collect.collection_scope()

    assert f'"country":"{collect.JOBTECH_SWEDEN_COUNTRY_CODE}"' in scope_json


def test_occupation_field_scope_replaces_the_keyword_filter() -> None:
    """Two scopes, one filter each: never both on one request, never merged into one scope."""
    keyword_id, _, keyword_json = collect.collection_scope()
    field_id, _, field_json = collect.collection_scope(
        occupation_field=collect.JOBTECH_DATA_IT_FIELD
    )

    assert f'"occupation-field":"{collect.JOBTECH_DATA_IT_FIELD}"' in field_json
    assert '"q"' not in field_json
    assert '"q":"utvecklare"' in keyword_json
    assert "occupation-field" not in keyword_json
    assert field_id != keyword_id
    assert f'"country":"{collect.JOBTECH_SWEDEN_COUNTRY_CODE}"' in field_json


def test_keyword_scope_id_is_frozen() -> None:
    """Scope definitions are append-only: editing this one orphans every posting already under it,
    and an orphaned posting can never be closed, so it would render as active forever."""
    assert collect.collection_scope()[0] == "jobtech-f5cf1d409aa51fad"


def test_scope_refuses_two_selectors_at_once() -> None:
    try:
        collect.collection_scope("utvecklare", occupation_field=collect.JOBTECH_DATA_IT_FIELD)
    except ValueError as error:
        assert "not both" in str(error)
    else:
        raise AssertionError("a scope must carry exactly one filter")


def test_scope_refuses_an_occupation_field_that_is_not_a_concept_id() -> None:
    """A scope is append-only, so a typo is permanent: a misspelled field the API answers with
    zero hits would publish a complete empty partition under a new scope that renders forever."""
    for typo in (
        collect.JOBTECH_DATA_IT_FIELD + "X",
        f" {collect.JOBTECH_DATA_IT_FIELD} ",
        "apaJ2jaLuF",
        "",
    ):
        try:
            collect.collection_scope(occupation_field=typo)
        except ValueError as error:
            assert "concept id" in str(error)
        else:
            raise AssertionError(f"{typo!r} must not be accepted as an occupation field")


FIXTURE_REFERENCE = Path(__file__).parent / "fixtures" / "reference"
FIXTURE_REVIEW = FIXTURE_REFERENCE / "review_sample.ndjson"


def test_enrichment_keeps_mapping_states_distinct() -> None:
    refs = enrich.load_references(FIXTURE_REFERENCE)
    mapped = enrich.enrich_hit(
        {
            "workplace_address": {"municipality_code": "0180"},
            "occupation": {"concept_id": "occ-exact"},
            "must_have": {"skills": [{"concept_id": "skill-python"}]},
        },
        refs,
    )
    manual = enrich.enrich_hit({"occupation": {"concept_id": "occ-manual"}}, refs)
    unresolved = enrich.enrich_hit(
        {
            "workplace_address": {"region_code": "99"},
            "occupation": {"concept_id": "occ-ambiguous"},
            "must_have": {"skills": [{"concept_id": "skill-cloud"}]},
            "nice_to_have": {"skills": [{"concept_id": "skill-unknown"}]},
        },
        refs,
    )
    absent = enrich.enrich_hit({}, refs)

    assert mapped["region"]["status"] == "mapped"
    assert mapped["region"]["nuts_code"] == "SE110"
    assert mapped["region"]["method"] == "municipality_prefix_crosswalk"
    assert mapped["occupation"]["status"] == "mapped"
    assert mapped["skills"][0]["status"] == "mapped"
    assert manual["occupation"]["status"] == "mapped"
    assert manual["occupation"]["method"] == "manual_review"
    assert unresolved["region"]["status"] == "unmapped"
    assert unresolved["occupation"]["status"] == "ambiguous"
    assert {skill["status"] for skill in unresolved["skills"]} == {"low_confidence", "unmapped"}
    assert absent["region"]["status"] == "not_present"
    assert absent["occupation"]["status"] == "not_present"
    assert absent["skills"][0]["status"] == "not_present"


def test_sole_exact_match_resolves_a_multi_candidate_concept() -> None:
    """A multi-candidate concept stays refused unless exactly one candidate is an exact match."""
    refs = enrich.load_references(FIXTURE_REFERENCE)
    exact_occupation = "http://data.europa.eu/esco/occupation/fixture-tiebreak-exact"
    exact_skill = "http://data.europa.eu/esco/skill/fixture-tiebreak-exact"
    tiebroken = enrich.enrich_hit(
        {
            "occupation": {"concept_id": "occ-tiebreak"},
            "must_have": {"skills": [{"concept_id": "skill-tiebreak"}]},
        },
        refs,
    )
    conflicted = enrich.enrich_hit(
        {
            "occupation": {"concept_id": "occ-two-exact"},
            "must_have": {"skills": [{"concept_id": "skill-two-exact"}]},
        },
        refs,
    )
    single = enrich.enrich_hit(
        {
            "occupation": {"concept_id": "occ-low"},
            "must_have": {"skills": [{"concept_id": "skill-cloud"}]},
        },
        refs,
    )
    no_exact = enrich.enrich_hit({"occupation": {"concept_id": "occ-ambiguous"}}, refs)

    assert tiebroken["occupation"]["status"] == "mapped"
    assert tiebroken["occupation"]["method"] == "exact_match_tiebreak"
    assert tiebroken["occupation"]["uri"] == exact_occupation
    assert tiebroken["skills"][0]["status"] == "mapped"
    assert tiebroken["skills"][0]["method"] == "exact_match_tiebreak"
    assert tiebroken["skills"][0]["uri"] == exact_skill
    # Two stated equivalences cannot both be the mapping, so the conflict is published, not picked.
    assert conflicted["occupation"]["status"] == "ambiguous"
    assert conflicted["occupation"]["uri"] is None
    assert conflicted["occupation"]["method"] == "no_match"
    assert conflicted["skills"][0]["status"] == "ambiguous"
    assert conflicted["skills"][0]["uri"] is None
    # The single-candidate and no-exact-match paths keep their previous outcomes.
    assert single["occupation"]["status"] == "low_confidence"
    assert single["occupation"]["method"] == "crosswalk"
    assert single["skills"][0]["status"] == "low_confidence"
    assert no_exact["occupation"]["status"] == "ambiguous"


def test_a_reviewed_refusal_overrides_a_bad_tiebreak() -> None:
    """A reviewer must be able to refuse a tiebreak, not only redirect it.

    The audit in Increment 13a found the crosswalk asserting one ESCO concept to be the exact
    equivalent of two different source concepts. The losing concept has no correct URI anywhere
    in the reference, so a redirect-only override could merely swap one wrong mapping for
    another. Refusing puts that single concept back where the narrower rule would have left it.
    """
    refs = enrich.load_references(FIXTURE_REFERENCE)
    vetoed = enrich.enrich_hit({"occupation": {"concept_id": "occ-vetoed"}}, refs)

    assert vetoed["occupation"]["status"] == "ambiguous"
    assert vetoed["occupation"]["uri"] is None
    assert vetoed["occupation"]["label"] is None
    assert vetoed["occupation"]["confidence"] is None
    # Still manual_review, so the eight-value published vocabulary does not grow and the
    # decision stays attributable to a reviewer rather than to the rule.
    assert vetoed["occupation"]["method"] == "manual_review"
    # The refusal must beat the tiebreak, not merely coexist with it.
    assert refs.manual[("occupation", "occ-vetoed")].candidate is None
    exact = [
        option for option in refs.occupations["occ-vetoed"] if option.relation == "exact-match"
    ]
    assert len(exact) == 1


def test_manual_reviews_refuse_unreadable_rows(tmp_path: Path) -> None:
    """A review this loader cannot express must fail, because a skipped row reads as no row."""
    header = (
        "dimension,source_concept_id,target_uri,target_label,relation,"
        "status,confidence,reviewer,reviewed_at\n"
    )
    cases = {
        # A status the loader has no representation for used to be silently dropped.
        "occupation,occ-x,,,,low_confidence,,fixture,2026-08-22\n": "unsupported manual review",
        "occupation,occ-x,,,,not_present,,fixture,2026-08-22\n": "unsupported manual review",
        "occupation,occ-x,,,,mappd,,fixture,2026-08-22\n": "unsupported manual review",
        # A refusal that also names a target has two contradictory intentions.
        (
            "occupation,occ-x,http://data.europa.eu/esco/occupation/x,x,"
            "manual-review,ambiguous,,fixture,2026-08-22\n"
        ): "must not name",
    }
    for row, expected in cases.items():
        root = tmp_path / str(abs(hash(row)))
        root.mkdir()
        for name in (
            "geography_nuts_2024.csv",
            "jobtech_occupation_esco_1.2.1.csv",
            "jobtech_skill_esco_1.2.1.csv",
            "jobtech_requirement_labels.csv",
        ):
            (root / name).write_text(
                (FIXTURE_REFERENCE / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        (root / "manual_reviews.csv").write_text(header + row, encoding="utf-8")
        try:
            enrich.load_references(root)
        except ValueError as error:
            assert expected in str(error), (row, str(error))
        else:
            raise AssertionError(f"{row!r} must not load")


def test_requirement_dimensions_account_for_every_posting() -> None:
    """Each dimension must yield exactly one triple per posting, including the unresolved cases.

    The published column sums to the sweep's posting count only if nothing is ever dropped, so a
    null source concept_id and a code the reference does not carry are two visible rows rather
    than two silences - and they stay distinct, because one is the source declining to state a
    value and the other is our vocabulary being out of date.
    """
    refs = enrich.load_references(FIXTURE_REFERENCE)
    stated = enrich.enrich_hit(
        {
            "employment_type": {"concept_id": "emp-permanent", "label": "Tillsvidareanställning"},
            "working_hours_type": {"concept_id": "hours-part", "label": "Deltid"},
            "duration": {"concept_id": "duration-open", "label": "Tills vidare"},
        },
        refs,
    )["requirements"]
    empty = enrich.enrich_hit(
        {
            "employment_type": {"concept_id": None, "label": None},
            "duration": {},
        },
        refs,
    )["requirements"]
    unknown = enrich.enrich_hit({"employment_type": {"concept_id": "emp-invented"}}, refs)[
        "requirements"
    ]

    assert set(stated) == set(enrich.REQUIREMENT_DIMENSIONS)
    assert stated["employment_type"] == {
        "code": "emp-permanent",
        "label": "Permanent employment",
        "status": "mapped",
    }
    assert stated["working_hours_type"]["label"] == "Part-time"
    assert stated["duration"]["label"] == "Open-ended"
    # A missing block, a present block with a null concept_id, and an absent field are one fact.
    for triple in (empty["employment_type"], empty["duration"], empty["working_hours_type"]):
        assert triple == {"code": None, "label": "Not stated", "status": "not_present"}
    # The unrecognised code is kept, so a vocabulary change is legible rather than merely counted.
    assert unknown["employment_type"] == {
        "code": "emp-invented",
        "label": "Unrecognised code",
        "status": "unmapped",
    }
    # No fourth status: the requirement triples reuse the published vocabulary.
    assert {triple["status"] for triple in (*stated.values(), *unknown.values())} <= enrich.STATUSES
    try:
        enrich.requirement_mapping("salary_type", {"concept_id": "x"}, refs)
    except ValueError as error:
        assert "unknown requirement dimension" in str(error)
    else:
        raise AssertionError("a dimension outside the published three must not map")


def test_requirement_reference_carries_the_live_vocabulary() -> None:
    """Every code observed live must map, and the file must be hashed into sweep provenance.

    A code absent from this file is published as `Unrecognised code`, which is visible but is not
    information. A file absent from reference_hashes is worse: the reference could change and no
    stored manifest would record it.
    """
    import csv as _csv

    with (Path("data/reference") / "jobtech_requirement_labels.csv").open(
        encoding="utf-8"
    ) as handle:
        rows = list(_csv.DictReader(handle))
    codes = {(row["dimension"], row["source_concept_id"]): row["label_en"] for row in rows}
    # Measured across all seven retained sweeps in Increment 13a/14; nothing outside these sets has
    # ever been observed. The taxonomy declares a fifth employment type that is still unobserved.
    observed = {
        ("employment_type", "PFZr_Syz_cUq"),
        ("employment_type", "kpPX_CNN_gDU"),
        ("employment_type", "sTu5_NBQ_udq"),
        ("employment_type", "1paU_aCR_nGn"),
        ("working_hours_type", "6YE1_gAC_R2G"),
        ("working_hours_type", "947z_JGS_Uk2"),
        ("duration", "a7uU_j21_mkL"),
        ("duration", "qQUd_4qe_NDT"),
        ("duration", "gJRb_akA_95y"),
        ("duration", "Xj7x_7yZ_jEn"),
        ("duration", "9RGe_UxD_FZw"),
        ("duration", "Sy9J_aRd_ALx"),
    }
    assert observed <= set(codes)
    assert len(codes) == len(rows)
    for (dimension, code), label in codes.items():
        assert dimension in enrich.REQUIREMENT_DIMENSIONS
        # The fixture placeholders are not concept ids, so this also keeps them out of the
        # committed file the way the ESCO placeholder guard does.
        assert collect.JOBTECH_CONCEPT_ID.fullmatch(code), code
        assert label and label not in (enrich.NOT_STATED_LABEL, enrich.UNRECOGNISED_LABEL)
        assert label.isascii(), label
    provenance = enrich.reference_provenance()
    assert "jobtech_requirement_labels.csv=" in provenance["reference_hashes"]


def test_municipality_prefix_resolves_full_swedish_coverage() -> None:
    refs = enrich.load_references(FIXTURE_REFERENCE)
    goteborg = enrich.enrich_hit({"workplace_address": {"municipality_code": "1480"}}, refs)
    assert goteborg["region"]["nuts_code"] == "SE232"
    assert goteborg["region"]["method"] == "municipality_prefix_crosswalk"


def test_mapping_evaluation_is_deterministic() -> None:
    refs = enrich.load_references(FIXTURE_REFERENCE)
    report = evaluate.evaluate(sample=FIXTURE_REVIEW, references=refs)

    assert report["sample_size"] == 3
    assert report["occupation"]["precision"] == 1.0
    assert report["occupation"]["recall"] == 1.0
    assert report["skill"]["precision"] == 1.0
    assert report["skill"]["recall"] == 0.75
    assert "JobTech->ESCO" in report["evaluation_basis"]


def test_committed_reference_has_no_placeholder_uris() -> None:
    import csv as _csv

    reference = Path("data/reference")
    placeholders = {
        "occ-exact",
        "occ-manual",
        "occ-ambiguous",
        "occ-low",
        "occ-tiebreak",
        "occ-two-exact",
        "occ-vetoed",
        "skill-python",
        "skill-manual",
        "skill-cloud",
        "skill-unknown",
        "skill-tiebreak",
        "skill-two-exact",
    }
    for name in ("jobtech_occupation_esco_1.2.1.csv", "jobtech_skill_esco_1.2.1.csv"):
        with (reference / name).open(encoding="utf-8") as handle:
            rows = list(_csv.DictReader(handle))
        assert rows
        for row in rows:
            assert row["target_uri"].startswith("http://data.europa.eu/esco/"), row["target_uri"]
            assert row["source_concept_id"] not in placeholders
            assert row["target_uri"].rsplit("/", 1)[-1] not in placeholders


def test_geography_reference_covers_all_swedish_lan() -> None:
    import csv as _csv

    with (Path("data/reference") / "geography_nuts_2024.csv").open(encoding="utf-8") as handle:
        rows = [row for row in _csv.DictReader(handle) if row["source_type"] == "region"]
    assert len(rows) == 21
    assert all(re.fullmatch(r"SE\d{3}", row["nuts_code"]) for row in rows)


def test_real_evaluation_is_honest_and_nontrivial() -> None:
    report = evaluate.evaluate()
    assert "JobTech->ESCO" in report["evaluation_basis"]
    assert report["sample_size"] == 3
    assert report["skill"]["recall"] is not None and report["skill"]["recall"] < 1.0


def test_sample_does_not_leak_source_concept_ids() -> None:
    sample = Path("data/sample/postings_sample.ndjson").read_text(encoding="utf-8")
    for concept_id in ("CZkP_hCz_KM8", "71Ji_irM_rSJ", "3vry_gaE_yfQ", "jBKc_5Yx_Y6T"):
        assert concept_id not in sample


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
    assert manifest["schema_version"] == 3
    assert manifest["approval_status"] == "approved"
    assert manifest["expected_country"] == "SE"
    assert manifest["licence_reference"] == collect.JOBTECH_LICENCE_REFERENCE
    assert len(urls) == 2
    # The manifest claims a Sweden-filtered sweep, so the request must actually carry the filter.
    assert all(f"country={collect.JOBTECH_SWEDEN_COUNTRY_CODE}" in url for url in urls)
    partition = tmp_path / "collections" / "jobtech" / manifest["scope_id"] / manifest["sweep_id"]
    assert (partition / "observations.ndjson").exists()
    assert (
        json.loads((partition / "manifest.json").read_text(encoding="utf-8"))["status"]
        == "complete"
    )


def test_collect_jobtech_sweep_requests_the_occupation_field_on_the_wire(tmp_path: Path) -> None:
    """The scope claims an occupation field, so the request must actually carry that parameter."""
    urls: list[str] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del timeout
        urls.append(url)
        return {"total": {"value": 1}, "hits": [data_it_hit("one")]}

    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        occupation_field=collect.JOBTECH_DATA_IT_FIELD,
        observed_at="2026-08-15T00:00:00Z",
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-datait",
    )

    assert manifest["status"] == "complete"
    assert manifest["row_count"] == 1
    assert urls and all(f"occupation-field={collect.JOBTECH_DATA_IT_FIELD}" in url for url in urls)
    assert all("q=" not in url for url in urls)
    assert all(f"country={collect.JOBTECH_SWEDEN_COUNTRY_CODE}" in url for url in urls)
    assert manifest["scope_id"] != collect.collection_scope()[0]
    assert manifest["coverage_limitations"] == collect.JOBTECH_OCCUPATION_FIELD_LIMITATIONS


def test_collect_jobtech_sweep_rejects_an_ignored_occupation_field_filter(tmp_path: Path) -> None:
    """The API answers an unknown parameter with everything and no error, so a page where the
    requested field is a minority means the sweep collected Sweden under a narrow scope name."""
    other_fields = ("E7hm_BLq_fqZ", "j7Cq_ZJe_grK", "ARvv_Cbu_ptx")

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del url, timeout
        return {
            "total": {"value": 10},
            "hits": [data_it_hit("in-scope")]
            + [
                data_it_hit(f"off-{index}", other_fields[index % len(other_fields)])
                for index in range(9)
            ],
        }

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            occupation_field=collect.JOBTECH_DATA_IT_FIELD,
            observed_at="2026-08-15T00:00:00Z",
            page_size=10,
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-ignored",
        )
    except collect.CollectionError as error:
        assert "did not apply the occupation-field filter: only 1 of 10" in str(error)
    else:
        raise AssertionError("a silently ignored filter must abort the sweep")

    state = tmp_path / "collection-state" / "20260815T000000Z-ignored" / "manifest.json"
    assert json.loads(state.read_text(encoding="utf-8"))["status"] == "failed"
    assert not (tmp_path / "collections").exists()


def test_collect_jobtech_sweep_rejects_hits_without_the_requested_field(tmp_path: Path) -> None:
    """An absent occupation_field is the shape a widened, unfiltered response actually has."""

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del url, timeout
        return {"total": {"value": 10}, "hits": [hit(f"plain-{index}") for index in range(10)]}

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            occupation_field=collect.JOBTECH_DATA_IT_FIELD,
            observed_at="2026-08-15T00:00:00Z",
            page_size=10,
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-nofield",
        )
    except collect.CollectionError as error:
        assert "only 0 of 10" in str(error)
    else:
        raise AssertionError("hits missing the filtered field must abort the sweep")


def test_occupation_field_sweep_tolerates_adjacent_occupations(tmp_path: Path) -> None:
    """Measured live: the source's field filter returns 97-100 of 100 in-field, the rest adjacent
    (a Säkerhetsingenjör answering a Data/IT search). That is the filter working, not failing."""
    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        occupation_field=collect.JOBTECH_DATA_IT_FIELD,
        observed_at="2026-08-15T00:00:00Z",
        page_size=10,
        transport=lambda url, timeout: {
            "total": {"value": 10},
            "hits": [data_it_hit(f"in-{index}") for index in range(9)]
            + [data_it_hit("adjacent", "E7hm_BLq_fqZ")],
        },
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-adjacent",
    )

    assert manifest["status"] == "complete"
    assert manifest["row_count"] == 10
    # The postings are published, so the limitation has to say the scope is not pure.
    assert "adjacent occupations" in str(manifest["coverage_limitations"])


def test_occupation_field_sweep_does_not_judge_the_filter_on_a_short_page(tmp_path: Path) -> None:
    """A final page is total % page_size rows long, so one adjacent hit out of two is exactly the
    majority threshold. Refusing there would strand the scope: the checkpoint is resumable, so the
    same short page would be requested and refused again on every retry."""
    responses: dict[int, dict[str, Any]] = {
        0: {"total": {"value": 12}, "hits": [data_it_hit(f"in-{index}") for index in range(10)]},
        10: {
            "total": {"value": 12},
            "hits": [data_it_hit("last-in-field"), data_it_hit("last-adjacent", "E7hm_BLq_fqZ")],
        },
    }

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del timeout
        return responses[int(url.split("offset=")[1].split("&")[0])]

    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        occupation_field=collect.JOBTECH_DATA_IT_FIELD,
        observed_at="2026-08-15T00:00:00Z",
        page_size=10,
        transport=transport,
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-shortpage",
    )

    assert manifest["status"] == "complete"
    assert manifest["row_count"] == 12


def test_occupation_field_sweep_accepts_a_zero_row_sweep(tmp_path: Path) -> None:
    """An empty page proves nothing about the filter and must not be read as a widened sweep."""
    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        occupation_field=collect.JOBTECH_DATA_IT_FIELD,
        observed_at="2026-08-15T00:00:00Z",
        transport=lambda url, timeout: {"total": {"value": 0}, "hits": []},
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-datait-empty",
    )

    assert manifest["status"] == "complete"
    assert manifest["row_count"] == 0


def test_keyword_sweep_ignores_the_occupation_field_of_its_hits(tmp_path: Path) -> None:
    """A keyword sweep never asked about occupation fields, so a mixed answer is correct."""
    manifest = collect.collect_jobtech_sweep(
        tmp_path,
        KEY,
        observed_at="2026-08-15T00:00:00Z",
        transport=lambda url, timeout: {
            "total": {"value": 2},
            "hits": [data_it_hit("one", "unrelated"), hit("two")],
        },
        sleeper=lambda _: None,
        clock=fake_clock,
        monotonic_now=lambda: 0.0,
        sweep_id="20260815T000000Z-keyword",
    )

    assert manifest["row_count"] == 2
    assert manifest["scope_id"] == collect.collection_scope()[0]
    assert manifest["coverage_limitations"] == collect.JOBTECH_COVERAGE_LIMITATIONS


def test_collect_jobtech_sweep_resumes_an_occupation_field_scope(tmp_path: Path) -> None:
    """Resume must rehydrate the selector the saved scope carries. Defaulting to the keyword query
    would resume under a different scope_id and fail the checkpoint's scope comparison."""
    responses: dict[int, dict[str, Any]] = {
        0: {"total": {"value": 2}, "hits": [data_it_hit("one")]},
        1: {"total": {"value": 2}, "hits": [data_it_hit("two")]},
    }
    calls: list[int] = []

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del timeout
        offset = int(url.split("offset=")[1].split("&")[0])
        calls.append(offset)
        if offset == 1 and calls.count(1) == 1:
            raise TimeoutError("interrupt page two")
        return responses[offset]

    for resume in (False, True):
        try:
            manifest = collect.collect_jobtech_sweep(
                tmp_path,
                KEY,
                # The resumed call passes no selector at all: it has to read one back from the
                # checkpoint, which is the whole point of the test.
                occupation_field=None if resume else collect.JOBTECH_DATA_IT_FIELD,
                observed_at=None if resume else "2026-08-15T00:00:00Z",
                page_size=None if resume else 1,
                transport=transport,
                sleeper=lambda _: None,
                clock=fake_clock,
                monotonic_now=lambda: 0.0,
                sweep_id="20260815T000000Z-datait-resume",
                policy=collect.RetryPolicy(max_attempts=1, deadline_s=10),
                resume=resume,
            )
        except collect.CollectionError:
            assert not resume, "the resumed run must not fail"
            manifest = {}

    assert manifest["status"] == "complete"
    assert manifest["row_count"] == 2
    assert '"occupation-field"' in str(manifest["scope_json"])
    assert '"q"' not in str(manifest["scope_json"])


def test_collect_jobtech_sweep_refuses_a_scope_it_cannot_traverse(tmp_path: Path) -> None:
    """Measured live: Data/IT is 2589 ads and the API refuses offset > 2000, so 489 of them are
    unreachable. Publishing the reachable prefix as a complete sweep would close all 489 as
    inferred absences on the next sweep, so the sweep must refuse before writing anything."""

    def transport(url: str, timeout: float) -> dict[str, Any]:
        del url, timeout
        return {"total": {"value": 2589}, "hits": [data_it_hit("one")]}

    try:
        collect.collect_jobtech_sweep(
            tmp_path,
            KEY,
            occupation_field=collect.JOBTECH_DATA_IT_FIELD,
            observed_at="2026-08-15T00:00:00Z",
            transport=transport,
            sleeper=lambda _: None,
            clock=fake_clock,
            monotonic_now=lambda: 0.0,
            sweep_id="20260815T000000Z-unreachable",
        )
    except collect.CollectionError as error:
        assert "only 2100 are reachable" in str(error)
    else:
        raise AssertionError("an untraversable scope must not be collected")

    assert not (tmp_path / "collections").exists()
    state = tmp_path / "collection-state" / "20260815T000000Z-unreachable"
    assert not (state / "pages").exists()


def test_reachable_window_follows_the_page_size_grid() -> None:
    """Offsets land on multiples of page_size, so rounding the cap up would let a non-divisor page
    size pass the check and then die at the first offset above 2000 with the pages already saved."""
    collect._verify_reachable(2100, 100)
    collect._verify_reachable(2010, 30)
    collect._verify_reachable(2001, 1)
    for total, page_size, reachable in ((2101, 100, 2100), (2011, 30, 2010), (2002, 1, 2001)):
        try:
            collect._verify_reachable(total, page_size)
        except collect.CollectionError as error:
            assert f"only {reachable} are reachable" in str(error)
        else:
            raise AssertionError(f"{total} rows at page size {page_size} is not traversable")


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


def test_publish_builds_aggregate_page(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OBSERVATIONS_PATH", raising=False)
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
    connection.execute(
        """
        create table dimension_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'region'::varchar as dimension, 'SE110'::varchar as value_uri,
               'Stockholms län'::varchar as value_label, 'NUTS-2024'::varchar as taxonomy_version,
               2::bigint as posting_count
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'occupation', 'http://data.europa.eu/esco/occupation/bd272aee',
               'IKT-programutvecklare', '1.2.1', 1::bigint
        """
    )
    connection.execute(
        """
        create table skill_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'skill'::varchar as dimension,
               'http://data.europa.eu/esco/skill/4c016b68'::varchar as value_uri,
               'C#'::varchar as value_label, '1.2.1'::varchar as taxonomy_version,
               1::bigint as posting_count
        """
    )
    connection.execute(
        """
        create table mapping_quality_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, 'region'::varchar as dimension,
               'mapped'::varchar as mapping_status, 'region_crosswalk'::varchar as mapping_method,
               cast(null as varchar) as mapping_confidence,
               'NUTS-2024'::varchar as taxonomy_version,
               2::bigint as outcome_count, 3::hugeint as total_outcomes
        """
    )
    connection.execute(
        """
        create table mapping_coverage_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, 'region'::varchar as dimension,
               3::bigint as postings_total, 3::bigint as postings_with_source_value,
               2::bigint as postings_mapped, 'NUTS-2024'::varchar as taxonomy_version
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'occupation', 3::bigint, 2::bigint,
               1::bigint, '1.2.1'
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', 'skill', 3::bigint, 2::bigint, 1::bigint,
               '1.2.1'
        """
    )
    connection.execute(
        """
        create table requirement_demand_latest as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id, timestamp '2026-08-06 09:00:00' as observed_at,
               'employment_type'::varchar as dimension, 'kpPX_CNN_gDU'::varchar as value_code,
               'Permanent employment (probationary period possible)'::varchar as value_label,
               'mapped'::varchar as mapping_status, 2::bigint as posting_count
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'employment_type', 'zzzz_zzz_zzz', 'Unrecognised code', 'unmapped', 1::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'working_hours_type', '6YE1_gAC_R2G', 'Full-time', 'mapped', 2::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'working_hours_type', cast(null as varchar), 'Not stated', 'not_present', 1::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-one', timestamp '2026-08-06 09:00:00',
               'duration', 'a7uU_j21_mkL', 'Open-ended', 'mapped', 3::bigint
        """
    )
    connection.execute(
        """
        create table posting_flows as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'day'::varchar as grain,
               timestamp '2026-08-06 00:00:00' as bucket_start, true as is_suppressed,
               5::bigint as openings, cast(null as bigint) as closures,
               6::bigint as active_postings, 13::bigint as active_vacancies
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-07 00:00:00', true,
               cast(null as bigint), cast(null as bigint), cast(null as bigint),
               cast(null as bigint)
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-08 00:00:00', false,
               4::bigint, 1::bigint, 9::bigint, 15::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-09 00:00:00', false,
               3::bigint, 1::bigint, 11::bigint, 17::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'day', timestamp '2026-08-11 00:00:00', false,
               2::bigint, 1::bigint, 13::bigint, 19::bigint
        union all
        select 'jobtech', 'jobtech-scope', 'week', timestamp '2026-08-03 00:00:00', false,
               12::bigint, 2::bigint, 11::bigint, 17::bigint
        """
    )
    connection.execute(
        """
        create table posting_survival as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'active'::varchar as lifecycle_status,
               false as is_suppressed, true as any_right_censored,
               7::bigint as posting_count, 13::bigint as advertised_vacancies,
               0.0::double as median_duration_days, 0.0::double as p25_duration_days,
               1.0::double as p75_duration_days, 1::bigint as max_duration_days
        union all
        select 'jobtech', 'jobtech-scope', 'inferred_absence', true, false,
               cast(null as bigint), cast(null as bigint), cast(null as double),
               cast(null as double), cast(null as double), cast(null as bigint)
        """
    )
    connection.execute(
        """
        create table collection_frequency as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               3::bigint as complete_sweeps,
               timestamp '2026-08-05 09:00:00' as first_observed_at,
               timestamp '2026-08-08 09:00:00' as last_observed_at,
               36.0::double as median_interval_hours, 48::integer as freshness_threshold_hours,
               'Keyword-scoped'::varchar as coverage_limitations
        """
    )
    connection.execute(
        """
        create table source_coverage as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               'sweep-one'::varchar as sweep_id,
               'SE'::varchar as country, timestamp '2026-08-06 09:00:00' as observed_at,
               11::bigint as expected_rows, 11::bigint as observed_rows,
               'fresh'::varchar as freshness_status, 'covered'::varchar as coverage_status,
               3.0::double as freshness_age_hours,
               'Keyword-scoped'::varchar as coverage_limitations,
               48::integer as freshness_threshold_hours
        union all
        select 'jobtech', 'jobtech-scope', 'sweep-zero', 'SE', timestamp '2026-08-05 09:00:00',
               9::bigint, 9::bigint, 'stale', 'covered', 27.0::double, 'Keyword-scoped', 24
        union all
        select 'jobtech', 'jobtech-archive', 'sweep-old', 'SE', timestamp '2026-07-01 09:00:00',
               12::bigint, 9::bigint, 'stale', 'invalid', 900.0::double, 'Keyword-scoped', 72
        """
    )
    connection.execute(
        """
        create table latest_complete_sweeps as
        select 'jobtech'::varchar as source, 'jobtech-scope'::varchar as scope_id,
               timestamp '2026-08-06 09:00:00' as observed_at,
               'https://data.jobtechdev.se/dataservice/jobsearch/'::varchar as licence_reference,
               'official-public-api'::varchar as access_method,
               'JobSearch current ads'::varchar as source_version,
               'NUTS-2024'::varchar as nuts_version,
               'v30'::varchar as jobtech_taxonomy_version, '1.2.1'::varchar as esco_version,
               3::bigint as row_count
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
    assert "Stockholms län" in page
    assert "C#" in page
    assert "Sweden only" in page
    assert "No mapped dimension results" not in page
    # Iteration 9: historical analytics, correct labelling, and suppression.
    assert "Posting survival by closure basis" in page
    assert "Advertised vacancies" in page
    assert "Inferred removal" in page
    assert "posting duration or inferred removal" in page
    assert "never as time to hire" in page
    assert "Time to hire" not in page
    assert "suppressed" in page
    # Iteration 10: six sections, persistent filters, server-rendered charts, accessibility.
    for slug, heading in publish.SECTIONS:
        assert f'<h2 id="{slug}-heading">{heading}</h2>' in page
        assert f'data-tab="{slug}"' in page
    assert "data-filters" in page
    assert 'name="occupation"' in page
    assert 'name="skill"' in page
    assert "Reset filters" in page
    assert 'data-country="SE"' in page
    assert 'data-source="jobtech"' in page
    assert 'data-dimension="skill"' in page
    assert 'data-bucket="2026-08-07"' in page
    assert 'role="img"' in page
    assert "<title>Daily active postings within one source scope: jobtech-scope</title>" in page
    assert "<polyline points=" in page
    # One bucket is suppressed and one (2026-08-10) was never observed; both stay gaps.
    assert "4 plotted bucket(s), peak 13, 2 bucket(s) left as gaps" in page
    assert len(page.split('<polyline points="')[1].split('"')[0].split(" ")) == 2
    assert 'scope="col"' in page
    assert 'class="skip"' in page
    assert 'role="region"' in page
    assert "Stale data" in page
    assert "Partial coverage" in page
    assert "Download CSV" in page
    assert 'data-csv="table-quality-coverage"' in page
    assert "right-censored" in page
    # Coverage is reduced to the latest sweep per scope, so the older sweep-zero row is not shown.
    assert page.count('id="table-quality-coverage"') == 1
    coverage_table = page.split('id="table-quality-coverage"')[1].split("</table>")[0]
    assert coverage_table.count("data-row") == 2
    assert "2026-08-05" not in coverage_table
    assert "1 of 2" in page
    assert "source scope(s) covered" in page
    # Scope-keyed rows carry the filter keys, so country and source selectors reach them.
    assert 'data-row data-source="jobtech" data-country="SE"' in page
    assert "of this source\u2019s largest scope" in page
    assert "Groups under 5 postings are suppressed." not in page
    # Iteration 11: operational status, governance, and the release checks over the built page.
    assert "Operational status of the latest complete sweep" in page
    assert "The last complete sweep is 0.1 days old" in page
    # The archive scope stored 9 of 12 rows, and its own sweep threshold is quoted, not the
    # history-wide maximum published by collection_frequency.
    assert "so rows are missing" in page
    assert "past the 72 hour freshness threshold" in page
    assert "this scope is incomplete" not in page
    assert "20 row(s) stored by the latest sweep of each scope" in page
    assert "Source licences, access methods" in page
    assert "Privacy assessment" in page
    assert "Architecture overview" in page
    assert "built from the synthetic sample in data/sample/" in page
    assert f"Methodology version {publish.METHODOLOGY_VERSION}" in page
    assert f'data-methodology-version="{publish.METHODOLOGY_VERSION}"' in page
    # A masked group hides its vacancy and duration figures too, so the page must not promise
    # more than that.
    assert "a true zero posting count stays visible" in page
    # Iteration 13: every ranking states the postings it was drawn from, so a top-N list cannot
    # be read as the whole sweep. Counts, never percentages.
    assert page.count('class="denominator"') == 2
    # The selection rule is stated on the page, because the methodology version claims to cover
    # the mapping rules described here. Figures published under 1.0 used the stricter rule.
    assert "exactly one of them is an exact match, that one is used" in page
    assert publish.METHODOLOGY_VERSION != "1.0"
    assert (
        "Ranked from 1 mapped posting(s) of 3 in the latest sweep; 2 carry a structured occupation."
        in page
    )
    assert (
        "Ranked from 1 mapped posting(s) of 3 in the latest sweep; 2 carry a structured skill."
        in page
    )
    assert "%" not in page.split('class="denominator"')[1].split("</p>")[0]
    # Iteration 14: the three requirement dimensions, each accounting for every posting in the
    # sweep. Unresolved values are rows, not omissions, and the two unresolved kinds stay apart.
    assert '<h2 id="requirements-heading">Requirements</h2>' in page
    for caption in (
        "Latest postings by employment type",
        "Latest postings by working-hours type",
        "Latest postings by contract duration",
    ):
        assert caption in page
    assert "Permanent employment (probationary period possible)" in page
    assert "Unrecognised code" in page
    assert "Not stated" in page
    assert 'data-dimension="employment_type"' in page
    assert "our English translations of the Swedish taxonomy labels" in page
    assert "kpPX_CNN_gDU" in page
    # Every column reconciles by inspection, so no requirement table carries - or needs - a
    # denominator sentence, and the two that do are still the two rankings.
    requirements = page.split('id="requirements"')[1].split("</section>")[0]
    assert 'class="denominator"' not in requirements
    for identifier, total in (
        ("table-requirements-employment-type", 3),
        ("table-requirements-working-hours-type", 3),
        ("table-requirements-duration", 3),
    ):
        body = page.split(f'id="{identifier}"')[1].split("</tbody>")[0]
        assert sum(int(cell) for cell in re.findall(r'class="count">(\d+)<', body)) == total
    problems = release_check.check_page(page)
    # This fixture writes posting_flows directly, so its small counts never pass through the dbt
    # mask and the disclosure rule has to see them. Every other release rule must pass.
    assert [problem for problem in problems if "suppression threshold" not in problem] == []
    assert any("table-survival-flows publishes 1" in problem for problem in problems)


def test_truncated_occupation_ranking_states_what_it_leaves_out() -> None:
    """A one-row-per-posting ranking must not silently stop summing to its own denominator.

    Increment 13 widened occupation mapping enough that the ranking hit DIMENSION_LIMIT for the
    first time, so the visible column stopped accounting for every mapped posting. A reader who
    adds it up gets a smaller number than the sentence above it states, and nothing said why.
    """
    coverage = [("jobtech", "scope", "occupation", 627, 627, 519)]
    listed = [
        ("occupation", f"occ-{index}", "1.2.1", 1) for index in range(publish.DIMENSION_LIMIT)
    ]
    truncated = publish._denominator(coverage, "occupation", "occupation", listed=listed)
    assert "Ranked from 519 mapped posting(s) of 627" in truncated
    assert f"Only the {publish.DIMENSION_LIMIT} most frequent occupations are listed" in truncated
    assert "accounting for 25 of those mapped postings" in truncated
    assert "%" not in truncated

    # A complete ranking must stay silent: an unnecessary caveat is its own kind of dishonesty.
    whole = publish._denominator(
        coverage,
        "occupation",
        "occupation",
        listed=[("occupation", "occ", "1.2.1", 519)],
    )
    assert "unlisted tail" not in whole
    # The skill ranking counts postings per skill, so its column legitimately exceeds the
    # denominator and must never gain a shortfall clause.
    skills = publish._denominator(coverage, "skill", "skill")
    assert "unlisted tail" not in skills


def test_publish_handles_zero_only_aggregate(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    # A live build must not be labelled as the synthetic sample, so the basis label is pinned
    # for the non-default observations path too.
    monkeypatch.setenv("OBSERVATIONS_PATH", "data/raw/collections/jobtech/*/*/observations.ndjson")
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
    connection.execute(
        """
        create table dimension_demand_latest(
            source varchar, scope_id varchar, sweep_id varchar, observed_at timestamp,
            dimension varchar, value_uri varchar, value_label varchar, taxonomy_version varchar,
            posting_count bigint)
        """
    )
    connection.execute(
        """
        create table skill_demand_latest(
            source varchar, scope_id varchar, sweep_id varchar, observed_at timestamp,
            dimension varchar, value_uri varchar, value_label varchar, taxonomy_version varchar,
            posting_count bigint)
        """
    )
    connection.execute(
        """
        create table mapping_quality_latest(
            source varchar, scope_id varchar, sweep_id varchar, dimension varchar,
            mapping_status varchar, mapping_method varchar, mapping_confidence varchar,
            taxonomy_version varchar, outcome_count bigint, total_outcomes hugeint)
        """
    )
    connection.execute(
        """
        create table mapping_coverage_latest(
            source varchar, scope_id varchar, sweep_id varchar, dimension varchar,
            postings_total bigint, postings_with_source_value bigint, postings_mapped bigint,
            taxonomy_version varchar)
        """
    )
    connection.execute(
        """
        create table requirement_demand_latest(
            source varchar, scope_id varchar, sweep_id varchar, observed_at timestamp,
            dimension varchar, value_code varchar, value_label varchar, mapping_status varchar,
            posting_count bigint)
        """
    )
    connection.execute(
        """
        create table posting_flows(
            source varchar, scope_id varchar, grain varchar, bucket_start timestamp,
            is_suppressed boolean, openings bigint, closures bigint, active_postings bigint,
            active_vacancies bigint)
        """
    )
    connection.execute(
        """
        create table posting_survival(
            source varchar, scope_id varchar, lifecycle_status varchar, is_suppressed boolean,
            any_right_censored boolean, posting_count bigint, advertised_vacancies bigint,
            median_duration_days double, p25_duration_days double, p75_duration_days double,
            max_duration_days bigint)
        """
    )
    connection.execute(
        """
        create table collection_frequency(
            source varchar, scope_id varchar, complete_sweeps bigint, first_observed_at timestamp,
            last_observed_at timestamp, median_interval_hours double,
            freshness_threshold_hours integer, coverage_limitations varchar)
        """
    )
    connection.execute(
        """
        create table source_coverage(
            source varchar, scope_id varchar, sweep_id varchar, country varchar,
            observed_at timestamp, expected_rows bigint, observed_rows bigint,
            freshness_status varchar, coverage_status varchar, freshness_age_hours double,
            coverage_limitations varchar, freshness_threshold_hours integer)
        """
    )
    connection.execute(
        """
        create table latest_complete_sweeps(
            source varchar, scope_id varchar, observed_at timestamp, licence_reference varchar,
            access_method varchar, source_version varchar, nuts_version varchar,
            jobtech_taxonomy_version varchar, esco_version varchar, row_count bigint)
        """
    )
    connection.close()

    assert publish.build_site(database, target) == 1
    page = target.read_text(encoding="utf-8")
    assert "SE" in page
    assert ">0<" in page
    assert "No mapped dimension results" in page
    assert "No trend results" in page
    assert "No survival results" in page
    # Iteration 10: the remaining empty states and the filter bar still render.
    assert "No coverage results" in page
    assert "No provenance results" in page
    assert "No missing mapping results" in page
    assert "data-filters" in page
    assert "no trend published for this scope" in page
    assert "built from stored collection partitions (data/raw/collections/jobtech" in page
    assert "built from the synthetic sample" not in page
    # No coverage row means no denominator to state, and saying so beats printing a bare zero.
    assert page.count('class="denominator"') == 2
    assert "so this occupation ranking has no stated denominator" in page
    assert "so this skill ranking has no stated denominator" in page
    # A sweep collected before the requirement fields existed publishes no row for them, and the
    # section says so rather than inventing a `Not stated` bucket the source never reported.
    assert "No employment type results" in page
    assert "No working-hours type results" in page
    assert "No contract duration results" in page
    assert release_check.check_page(page) == []


def test_methodology_version_covers_the_requirement_dimensions() -> None:
    """The version is the only handle a saved CSV has on the rules that produced it.

    1.1 published no requirement dimension at all. Publishing three of them under 1.1 would make
    two files named `...-methodology-1-1.csv` carry figures from two different definition sets,
    which is exactly the traceability hole Increment 13a found and closed.
    """
    assert publish.METHODOLOGY_VERSION == "1.2"
    assert [slug for slug, _heading in publish.SECTIONS if slug == "requirements"] == [
        "requirements"
    ]
    assert [slug for slug, _heading, _noun in publish.REQUIREMENT_SECTIONS] == list(
        enrich.REQUIREMENT_DIMENSIONS
    )


def test_publish_refuses_to_pool_two_collecting_scopes() -> None:
    """The rankings and the mapping-quality table pool scopes, so a second one stops the build."""
    one: list[publish.MappingCoverageRow] = [("jobtech", "jobtech-scope", "occupation", 3, 2, 1)]
    zero_row_scope = [*one, ("jobtech", "jobtech-empty-scope", "occupation", 0, 0, 0)]
    two = [*one, ("jobtech", "jobtech-datait", "occupation", 4, 3, 2)]

    publish._verify_single_scope(one)
    publish._verify_single_scope(zero_row_scope)
    try:
        publish._verify_single_scope(two)
    except ValueError as error:
        assert "jobtech/jobtech-datait" in str(error)
        assert "jobtech/jobtech-scope" in str(error)
        assert "_query_dimension" in str(error)
    else:
        raise AssertionError("two scopes with postings must not be published as one ranking")


def masked_views(flows_cells: str, basis_cells: str = "<td>Active</td><td>7</td><td>0</td>") -> str:
    """Both suppression-masked tables, because the checker fails when one is missing."""
    flows = ("Scope", "Openings", "Active postings", "Active vacancies")
    basis = ("Basis", "Postings", "Advertised vacancies")
    heads = tuple(
        "".join(f'<th scope="col">{name}</th>' for name in names) for names in (flows, basis)
    )
    return (
        f'<table id="table-survival-flows"><caption>Flows</caption><thead><tr>{heads[0]}</tr>'
        f"</thead><tbody><tr data-row>{flows_cells}</tr></tbody></table>"
        f'<table id="table-survival-basis"><caption>Basis</caption><thead><tr>{heads[1]}</tr>'
        f"</thead><tbody><tr data-row>{basis_cells}</tr></tbody></table>"
    )


DENOMINATOR = (
    '<p class="denominator">Ranked from 7 mapped posting(s) of 9 in the latest sweep; '
    "8 carry a structured value.</p>"
)


def ranked_views(*, denominators: bool = True) -> str:
    """Both ranked top-N tables, because a ranking absent from the page also skips its rule."""
    head = '<thead><tr><th scope="col">Value</th><th scope="col">Postings</th></tr></thead>'
    return "".join(
        f"{DENOMINATOR if denominators else ''}"
        f'<table id="{identifier}"><caption>Ranked</caption>{head}'
        "<tbody><tr data-row><td>value</td><td>7</td></tr></tbody></table>"
        for identifier in ("table-occupations-ranked", "table-occupations-skills")
    )


def stub_page(
    body: str = "",
    *,
    version: str | None = None,
    masked: str | None = None,
    ranked: str | None = None,
) -> str:
    """The smallest page that satisfies every release rule, so one fault can be added at a time."""
    sections = "".join(
        f'<section id="{slug}"><h2>{heading}</h2></section>' for slug, heading in publish.SECTIONS
    )
    stamp = publish.METHODOLOGY_VERSION if version is None else version
    views = (
        masked_views("<td>scope</td><td>7</td><td>9</td><td>0</td>") if masked is None else masked
    )
    rankings = ranked_views() if ranked is None else ranked
    return (
        f'<!doctype html><html lang="en" data-methodology-version="{stamp}">'
        "<head><title>Observatory</title></head><body><h1>Observatory</h1>"
        f"<p>Groups of 1 to {publish.SUPPRESSION_THRESHOLD - 1} postings are suppressed.</p>"
        "<noscript><p>Filters need JavaScript.</p></noscript>"
        f"{sections}{views}{rankings}{body}</body></html>"
    )


def test_release_check_accepts_a_compliant_page() -> None:
    assert release_check.check_page(stub_page()) == []


def test_release_check_flags_accessibility_asset_and_link_faults() -> None:
    body = (
        "<div hidden><p>Invisible without JavaScript.</p></div>"
        '<a href="#nowhere">Broken</a><a href="https://example.com/tracker">Offsite</a>'
        '<link rel="stylesheet" href="theme.css"><iframe src="https://example.com/frame"></iframe>'
        # A label without `for` must not vouch for an unrelated control; a wrapping label does.
        '<label>Loose label</label><select name="loose"><option value="">All</option></select>'
        '<label>Wrapped <input name="wrapped"></label>'
        '<table id="table-loose"><thead><tr><th>Postings</th></tr></thead>'
        "<tbody><tr data-row><td>7</td></tr></tbody></table>"
    )
    problems = release_check.check_page(stub_page(body))
    assert any("table table-loose has no caption" in problem for problem in problems)
    assert any("header cell(s) without scope" in problem for problem in problems)
    assert any("#nowhere has no matching id" in problem for problem in problems)
    assert any("outside the documented allowlist" in problem for problem in problems)
    assert any("external asset requested: theme.css" in problem for problem in problems)
    assert any("example.com/frame" in problem for problem in problems)
    assert any("select control (no id) has no label" in problem for problem in problems)
    assert any("div element is hidden without JavaScript" in problem for problem in problems)
    assert not any("input control" in problem for problem in problems)


def test_release_check_flags_unmasked_small_counts_only_in_the_masked_views() -> None:
    columns = '<thead><tr><th scope="col">Scope</th><th scope="col">Openings</th></tr></thead>'
    rows = (
        "<tbody><tr data-row><td>scope</td><td>3</td></tr>"
        "<tr data-row><td>scope</td><td>0</td></tr>"
        "<tr data-row><td>scope</td><td>suppressed</td></tr></tbody>"
    )
    latest = (
        f'<table id="table-quality-coverage"><caption>Coverage</caption>{columns}{rows}</table>'
    )
    # A true zero and a suppressed cell are both fine; only 1..k-1 in a masked view is a fault,
    # and the latest-sweep marts publish their raw counts.
    assert release_check.check_page(
        stub_page(latest, masked=masked_views("<td>scope</td><td>3</td><td>9</td><td>0</td>"))
    ) == [
        "table table-survival-flows publishes 3 in the openings column, "
        f"below the suppression threshold of {publish.SUPPRESSION_THRESHOLD}"
    ]


def test_release_check_flags_figures_published_beside_a_suppressed_count() -> None:
    # posting_flows masks active_vacancies on active_postings, so a number here would republish
    # the group the mask just hid.
    leaked = masked_views("<td>scope</td><td>7</td><td>suppressed</td><td>12</td>")
    assert release_check.check_page(stub_page(masked=leaked)) == [
        "table table-survival-flows publishes 12 in the active vacancies column while its "
        "active postings count is suppressed"
    ]


def test_release_check_flags_missing_masked_views() -> None:
    problems = release_check.check_page(stub_page(masked=""))
    assert any("table-survival-basis is missing from the page" in problem for problem in problems)
    assert any("table-survival-flows is missing from the page" in problem for problem in problems)


def test_release_check_flags_a_ranking_published_without_its_denominator() -> None:
    absent = "has no denominator sentence before it"
    problems = release_check.check_page(stub_page(ranked=ranked_views(denominators=False)))
    assert [problem for problem in problems if absent in problem] == [
        f"table table-occupations-ranked {absent}, so a ranked subset can be read as the "
        "whole sweep",
        f"table table-occupations-skills {absent}, so a ranked subset can be read as the "
        "whole sweep",
    ]
    # One sentence cannot cover two rankings: the first table consumes it, so the second is bare.
    shared = release_check.check_page(
        stub_page(ranked=DENOMINATOR + ranked_views(denominators=False))
    )
    assert [problem for problem in shared if absent in problem] == [
        f"table table-occupations-skills {absent}, so a ranked subset can be read as the "
        "whole sweep"
    ]
    missing = release_check.check_page(stub_page(ranked=""))
    assert any("table-occupations-ranked is missing" in problem for problem in missing)
    assert any("table-occupations-skills is missing" in problem for problem in missing)


def test_release_check_flags_disclosure_and_version_drift() -> None:
    problems = release_check.check_page(
        stub_page(f'<p aria-label="TEAM@EXAMPLE.ORG">Token {"A1" * 20}.</p>', version="9.9")
    )
    assert any("key-like token is rendered" in problem for problem in problems)
    assert any("email address is rendered" in problem for problem in problems)
    assert any("does not match" in problem for problem in problems)
    bare = f'<html lang="en" data-methodology-version="{publish.METHODOLOGY_VERSION}"><h1>x</h1>'
    missing = release_check.check_page(bare)
    assert any("suppression rule as 1 to" in problem for problem in missing)
    assert any("section overview is missing" in problem for problem in missing)
    assert any("noscript" in problem for problem in missing)
