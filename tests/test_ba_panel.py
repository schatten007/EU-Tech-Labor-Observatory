"""Tests for the frozen NUTS-3 panel (BA Jobsuche, Germany step 2b).

Covers the invariants that make the panel usable for flow/survival series:

* the panel definition is a pure function of the pinned reference (frozen);
* the membership hash changes if and only if the query set changes;
* the declared page cap bounds each region and is encoded in the scope;
* ``expected_pages == completed_pages`` and ``expected_rows == row_count``
  hold for the declared capped scope, including when a region paginates out
  early because the advertised total was stale;
* a failed page breaks the identity loudly instead of silently truncating;
* the source's own ``woOutput`` echo is used as a locality assertion;
* rows carry the region of the query they came from, never a fabricated one;
* PII stays out of the payload and the written record.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.ba_jobsuche import (
    BA_ROBOTS_URL,
    BA_SEARCH_URL,
    BAJobsucheCollector,
    parse_search_envelope,
)
from scrapers.ba_panel import (
    BA_PANEL_PAGE_CAP,
    BA_PANEL_SCOPE_ID,
    BA_PANEL_UMKREIS,
    PanelEntry,
    ba_panel_coverage_limitations,
    ba_panel_scope_params,
    build_panel,
    load_pinned_panel,
    panel_candidates,
    panel_membership_hash,
    rule_panel,
    write_panel_regions,
    write_pinned_panel,
)
from scrapers.base import NormalizedRecord
from tests.test_ba_jobsuche import KEY, search_page, write_crosswalk

# A crosswalk with two regions, one addressable by a unique municipality name
# and one whose only name is ambiguous, so the postcode fallback is exercised.
PANEL_CROSSWALK = (
    "source_type,source_code,municipality_name,kreis_name,nuts_code,nuts_label,"
    "source_url,source_version\n"
    "kreis,11000,Berlin,Berlin,DE300,Berlin,https://example.invalid/k,2026-08-23\n"
    "kreis,08222,Aachtal,Aachtal,DE136,Aachtal,https://example.invalid/k,2026-08-23\n"
    "municipality,11000000,Berlin,Berlin,DE300,Berlin,https://example.invalid/m,2026-08-23\n"
    "municipality,08222000,Aach,Aachtal,DE136,Aachtal,https://example.invalid/m,2026-08-23\n"
    "municipality,08415000,Aach,Konstanz,DE138,Konstanz,https://example.invalid/m,2026-08-23\n"
    "plz,10178,Berlin,Berlin,DE300,Berlin,https://example.invalid/p,2026-08-23\n"
    "plz,10179,Berlin,Berlin,DE300,Berlin,https://example.invalid/p,2026-08-23\n"
    "plz,78267,Aach,Aachtal,DE136,Aachtal,https://example.invalid/p,2026-08-23\n"
)


def write_panel_crosswalk(tmp_path: Path, text: str = PANEL_CROSSWALK) -> Path:
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "germany_plz_nuts_2024.csv").write_text(text, encoding="utf-8")
    return ref_dir


def envelope_page(
    refs: list[tuple[str, str, str]],
    *,
    total: int,
    place: str,
    mode: str = "ORTSUCHE",
) -> str:
    """A synthetic search page carrying the SSR state envelope."""
    state = {
        "suchergebnis": {
            "ergebnisliste": [{"index": i} for i, _ in enumerate(refs)],
            "maxErgebnisse": total,
            "page": 1,
            "size": 25,
            "woOutput": {"bereinigterOrt": place, "suchmodus": mode},
        }
    }
    blob = json.dumps(state, ensure_ascii=False)
    return search_page(refs).replace(
        "</body>", f'<script id="ng-state" type="application/json">{blob}</script></body>'
    )


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


async def _collect(collector: BAJobsucheCollector) -> list[NormalizedRecord]:
    async with collector:
        return [record async for record in collector.collect()]


def panel_url(entry: PanelEntry, page: int) -> str:
    return f"{BA_SEARCH_URL}&{entry.query}&page={page}"


def refs(count: int, *, city: str, start: int = 0) -> list[tuple[str, str, str]]:
    return [(f"10000-{start + i:010d}-S", "19.08.2026", city) for i in range(count)]


# ---------------------------------------------------------------------------
# Panel definition: frozen, deterministic, hashed
# ---------------------------------------------------------------------------


def test_panel_is_one_query_per_region(tmp_path: Path) -> None:
    panel = build_panel(write_panel_crosswalk(tmp_path))
    assert [e.nuts_code for e in panel] == ["DE136", "DE300"]
    assert len({e.query for e in panel}) == 2
    # Berlin has a unique name; Aachtal's only municipality name (Aach) is
    # ambiguous, so it falls back to its unambiguous postcode.
    by_code = {e.nuts_code: e for e in panel}
    assert (by_code["DE300"].form, by_code["DE300"].value) == ("name", "Berlin")
    assert (by_code["DE136"].form, by_code["DE136"].value) == ("plz", "78267")


def test_panel_queries_are_umkreis_zero(tmp_path: Path) -> None:
    panel = build_panel(write_panel_crosswalk(tmp_path))
    for entry in panel:
        assert entry.query.endswith(f"&umkreis={BA_PANEL_UMKREIS}")
        assert entry.query.startswith("wo=")


def test_panel_build_is_deterministic(tmp_path: Path) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    first = build_panel(ref_dir)
    second = build_panel(ref_dir)
    assert [e.membership_line for e in first] == [e.membership_line for e in second]
    assert panel_membership_hash(first) == panel_membership_hash(second)


def test_membership_hash_detects_any_query_set_change(tmp_path: Path) -> None:
    panel = build_panel(write_panel_crosswalk(tmp_path))
    baseline = panel_membership_hash(panel)
    reordered = list(reversed(panel))
    dropped = panel[:-1]
    reworded = [
        panel[0].model_copy(update={"value": panel[0].value + "x"}),
        *panel[1:],
    ]
    assert panel_membership_hash(reordered) != baseline
    assert panel_membership_hash(dropped) != baseline
    assert panel_membership_hash(reworded) != baseline
    # ...and is stable under a change that does not touch the query set.
    relabelled = [panel[0].model_copy(update={"nuts_label": "Other label"}), *panel[1:]]
    assert panel_membership_hash(relabelled) == baseline


def test_panel_ignores_ambiguous_postcodes(tmp_path: Path) -> None:
    """A postcode in two regions carries no single-region provenance."""
    text = PANEL_CROSSWALK.replace(
        "plz,78267,Aach,Aachtal,DE136,Aachtal,https://example.invalid/p,2026-08-23\n",
        "plz,78267,Aach,Aachtal,DE136,Aachtal,https://example.invalid/p,2026-08-23\n"
        "plz,78267,Aach,Konstanz,DE138,Konstanz,https://example.invalid/p,2026-08-23\n",
    )
    panel = build_panel(write_panel_crosswalk(tmp_path, text))
    values = {e.nuts_code: e.value for e in panel}
    assert values.get("DE136") != "78267"


def test_scope_params_declare_the_cap_and_hash(tmp_path: Path) -> None:
    panel = build_panel(write_panel_crosswalk(tmp_path))
    params = ba_panel_scope_params(panel)
    assert params["page_cap_per_region"] == BA_PANEL_PAGE_CAP
    assert params["rows_cap_per_region"] == BA_PANEL_PAGE_CAP * 25
    assert params["membership_hash"] == panel_membership_hash(panel)
    assert params["frame_size"] == len(panel)
    assert params["frozen"] is True
    assert params["seed"] is None
    assert params["randomization"] == "none"
    # The cap must also be stated in prose, not only encoded in the scope.
    prose = ba_panel_coverage_limitations(panel)
    assert "not a census" in prose
    assert str(BA_PANEL_PAGE_CAP) in prose


def test_real_reference_yields_the_full_frame() -> None:
    ref_dir = Path("data/reference")
    if not (ref_dir / "germany_plz_nuts_2024.csv").exists():
        pytest.skip("pinned German crosswalk not present")
    panel = build_panel(ref_dir)
    assert len(panel) == 400
    assert len({e.nuts_code for e in panel}) == 400
    assert len({e.query for e in panel}) == 400


# ---------------------------------------------------------------------------
# Candidate ordering and the pinned artifact
# ---------------------------------------------------------------------------


def test_candidates_are_ordered_and_region_local(tmp_path: Path) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    candidates = panel_candidates(ref_dir)
    assert set(candidates) == {"DE136", "DE300"}
    # Berlin is its own seat town, so it leads its region's list.
    assert candidates["DE300"][0] == ("name", "Berlin")
    # Every candidate must be a place of that region: no cross-region leakage.
    assert ("name", "Berlin") not in candidates["DE136"]
    # Postcodes appear as later candidates, never ahead of a usable town.
    assert ("plz", "10178") in candidates["DE300"]
    assert candidates["DE300"].index(("name", "Berlin")) < candidates["DE300"].index(
        ("plz", "10178")
    )


def test_candidates_include_compound_seat_component(tmp_path: Path) -> None:
    """A merged Kreis ("Schleswig-Flensburg") is addressed by its seat town."""
    text = (
        "source_type,source_code,municipality_name,kreis_name,nuts_code,nuts_label,"
        "source_url,source_version\n"
        "kreis,01059,Schleswig-Flensburg,Schleswig-Flensburg,DEF0C,Schleswig-Flensburg,"
        "https://example.invalid/k,2026-08-23\n"
        "municipality,01059001,Ahneby,Schleswig-Flensburg,DEF0C,Schleswig-Flensburg,"
        "https://example.invalid/m,2026-08-23\n"
        "municipality,01059158,Schleswig,Schleswig-Flensburg,DEF0C,Schleswig-Flensburg,"
        "https://example.invalid/m,2026-08-23\n"
        "plz,24855,Ahneby,Schleswig-Flensburg,DEF0C,Schleswig-Flensburg,"
        "https://example.invalid/p,2026-08-23\n"
        "plz,24837,Schleswig,Schleswig-Flensburg,DEF0C,Schleswig-Flensburg,"
        "https://example.invalid/p,2026-08-23\n"
    )
    candidates = panel_candidates(write_panel_crosswalk(tmp_path, text))
    assert candidates["DEF0C"][0] == ("name", "Schleswig")


def test_pinned_artifact_overrides_the_rule(tmp_path: Path) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    ruled = rule_panel(ref_dir)
    by_code = {e.nuts_code: e for e in ruled}
    # The rule picks the name "Berlin" for DE300; pin a postcode instead.
    pinned_entries = [
        by_code["DE136"],
        by_code["DE300"].model_copy(update={"form": "plz", "value": "10179"}),
    ]
    write_pinned_panel(ref_dir, pinned_entries, {"pinned_at": "test"})
    loaded = build_panel(ref_dir)
    assert [(e.nuts_code, e.form, e.value) for e in loaded] == [
        (e.nuts_code, e.form, e.value) for e in pinned_entries
    ]
    assert panel_membership_hash(loaded) == panel_membership_hash(pinned_entries)
    assert panel_membership_hash(loaded) != panel_membership_hash(ruled)


def test_pinned_artifact_is_reloaded_identically(tmp_path: Path) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    write_pinned_panel(ref_dir, rule_panel(ref_dir), {"pinned_at": "test"})
    first = load_pinned_panel(ref_dir)
    second = load_pinned_panel(ref_dir)
    assert first is not None and second is not None
    assert panel_membership_hash(first) == panel_membership_hash(second)


def test_partial_pin_is_rejected(tmp_path: Path) -> None:
    """A half-pinned panel is not a frozen panel: it must fail, not fall back."""
    ref_dir = write_panel_crosswalk(tmp_path)
    write_pinned_panel(ref_dir, rule_panel(ref_dir)[:1], {"pinned_at": "test"})
    with pytest.raises(ValueError, match="not a frozen panel"):
        build_panel(ref_dir)


def test_pin_naming_an_unknown_region_is_rejected(tmp_path: Path) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    path = ref_dir / "ba_panel_nuts3.json"
    path.write_text(
        json.dumps({"entries": [{"nuts_code": "DE999", "form": "name", "value": "X"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="not exactly one region"):
        build_panel(ref_dir)


def test_real_pinned_panel_matches_the_reference_frame() -> None:
    ref_dir = Path("data/reference")
    if not (ref_dir / "ba_panel_nuts3.json").exists():
        pytest.skip("panel not pinned in this checkout")
    pinned = load_pinned_panel(ref_dir)
    assert pinned is not None
    assert len(pinned) == 400
    payload = json.loads((ref_dir / "ba_panel_nuts3.json").read_text(encoding="utf-8"))
    # The artifact carries the hash it was written with, and it must still hold.
    assert payload["membership_hash"] == panel_membership_hash(pinned)


# ---------------------------------------------------------------------------
# Envelope parsing
# ---------------------------------------------------------------------------


def test_parse_search_envelope_reads_total_place_and_mode() -> None:
    html = envelope_page(refs(1, city="Berlin"), total=30334, place="Berlin")
    total, place, mode = parse_search_envelope(html)
    assert (total, place, mode) == (30334, "Berlin", "ORTSUCHE")


def test_parse_search_envelope_absent_state_is_none() -> None:
    assert parse_search_envelope(search_page(refs(1, city="Berlin"))) == (
        None,
        None,
        None,
    )


def test_parse_search_envelope_malformed_state_is_none() -> None:
    html = search_page(refs(1, city="Berlin")).replace(
        "</body>", '<script id="ng-state">{not json}</script></body>'
    )
    assert parse_search_envelope(html) == (None, None, None)


# ---------------------------------------------------------------------------
# Panel sweep
# ---------------------------------------------------------------------------


def build_collector(ref_dir: Path, panel: list[PanelEntry]) -> BAJobsucheCollector:
    return BAJobsucheCollector(
        scope_id=BA_PANEL_SCOPE_ID,
        sweep_id="20260901T000000Z",
        observed_at=datetime(2026, 9, 1, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        panel=panel,
        pacing_interval=0.0,
    )


def mock_robots(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(BA_ROBOTS_URL).mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow:\nAllow: /\n")
    )


def test_panel_sweep_reconciles_and_respects_the_cap(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = build_panel(ref_dir)
    by_code = {e.nuts_code: e for e in panel}
    mock_robots(respx_mock)

    # Berlin advertises far more than the cap allows: 4 full pages, then stop.
    for page in range(1, BA_PANEL_PAGE_CAP + 1):
        respx_mock.get(panel_url(by_code["DE300"], page)).mock(
            return_value=httpx.Response(
                200,
                text=envelope_page(
                    refs(25, city="Berlin", start=1000 * page),
                    total=9999,
                    place="Berlin",
                ),
            )
        )
    # A 5th page must never be requested; if it is, respx raises.
    # Aachtal advertises 3, so exactly one page is planned.
    respx_mock.get(panel_url(by_code["DE136"], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(3, city="Aach", start=90), total=3, place="78267"),
        )
    )

    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))

    assert collector.panel_regions_queried == 2
    assert collector.completed_pages == BA_PANEL_PAGE_CAP + 1
    assert collector.total_pages == collector.completed_pages
    assert collector.total_elements == len(records) == BA_PANEL_PAGE_CAP * 25 + 3
    assert collector.panel_regions_capped == 1
    assert collector.failed_pages == 0
    assert collector.panel_locality_mismatches == 0
    assert collector.panel_regions["DE300"]["advertised"] == 9999
    assert collector.panel_regions["DE300"]["rows"] == BA_PANEL_PAGE_CAP * 25
    assert collector.panel_regions["DE136"]["advertised"] == 3


def test_panel_rows_carry_the_queried_region(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE136"]
    mock_robots(respx_mock)
    # The city name is ambiguous in the crosswalk (Aach is in DE136 and DE138),
    # so only the query's own provenance can resolve it — and it must resolve to
    # the queried region, never to the other candidate.
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(2, city="Aach", start=5), total=2, place="78267"),
        )
    )
    records = run(_collect(build_collector(ref_dir, panel)))
    assert [r.nuts_code for r in records] == ["DE136", "DE136"]
    assert {r.region_mapping_status for r in records} == {"mapped"}
    # Either tier is acceptable — Tier 2 disambiguates the ambiguous name with
    # the query's region, Tier 3 falls back to the query's own provenance — but
    # both must land on the queried region and neither may guess DE138.
    assert {r.region_mapping_method for r in records} <= {
        "ba_segment_disambiguated",
        "ba_segment_provenance_nuts3",
    }


def test_panel_short_pagination_keeps_the_identity_true(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    """A stale advertised total must not leave expected_pages > completed_pages."""
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    # Advertises 4 pages' worth but page 2 comes back short: the sweep stops and
    # the plan drops the un-walked remainder.
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(25, city="Berlin"), total=100, place="Berlin"),
        )
    )
    respx_mock.get(panel_url(panel[0], 2)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(4, city="Berlin", start=500), total=100, place="Berlin"),
        )
    )
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    assert collector.completed_pages == 2
    assert collector.total_pages == 2
    assert collector.panel_regions_short == 1
    assert collector.total_elements == len(records) == 29


def test_panel_failed_page_breaks_reconciliation_loudly(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    respx_mock.get(panel_url(panel[0], 1)).mock(return_value=httpx.Response(404))
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    assert records == []
    assert collector.failed_pages == 1
    # The page was planned and not fetched: the manifest must go partial.
    assert collector.total_pages == 1
    assert collector.completed_pages == 0


def test_panel_locality_mismatch_is_counted_not_silent(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    # The source resolved a different place than the one queried (probe E3's
    # "Osterholz" -> "Osterholz bei Bopfingen" fuzzy miss).
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(1, city="Berlin"), total=1, place="Berlin bei Anderswo"),
        )
    )
    collector = build_collector(ref_dir, panel)
    run(_collect(collector))
    assert collector.panel_locality_mismatches == 1


def test_panel_unresolvable_place_is_a_mismatch(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(1, city="Berlin"), total=0, place="", mode="UNGUELTIG"),
        )
    )
    collector = build_collector(ref_dir, panel)
    run(_collect(collector))
    assert collector.panel_locality_mismatches == 1


def test_panel_missing_envelope_is_counted(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(200, text=search_page(refs(2, city="Berlin")))
    )
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    assert collector.panel_missing_envelope == 1
    # Without an envelope only the mandatory first page is planned and walked.
    assert collector.total_pages == collector.completed_pages == 1
    assert len(records) == 2


def test_panel_dedupes_across_regions_on_hmac(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = build_panel(ref_dir)
    by_code = {e.nuts_code: e for e in panel}
    mock_robots(respx_mock)
    shared = refs(2, city="Berlin", start=7)
    respx_mock.get(panel_url(by_code["DE300"], 1)).mock(
        return_value=httpx.Response(200, text=envelope_page(shared, total=2, place="Berlin"))
    )
    respx_mock.get(panel_url(by_code["DE136"], 1)).mock(
        return_value=httpx.Response(200, text=envelope_page(shared, total=2, place="78267"))
    )
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    assert len(records) == 2
    assert collector.duplicates_dropped == 2
    assert collector.total_elements == 2
    # The panel is walked in NUTS-code order, so DE136 claims the shared rows
    # and the region queried second contributes none.
    assert collector.panel_regions["DE136"]["rows"] == 2
    assert collector.panel_regions["DE300"]["rows"] == 0
    assert collector.panel_regions_empty == 1


def test_panel_empty_region_is_complete_not_a_failure(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(200, text=envelope_page([], total=0, place="Berlin"))
    )
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    assert records == []
    assert collector.failed_pages == 0
    assert collector.panel_regions_empty == 1
    assert collector.total_pages == collector.completed_pages == 1


def test_panel_payload_and_records_carry_no_pii(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_panel_crosswalk(tmp_path)
    panel = [e for e in build_panel(ref_dir) if e.nuts_code == "DE300"]
    mock_robots(respx_mock)
    respx_mock.get(panel_url(panel[0], 1)).mock(
        return_value=httpx.Response(
            200,
            text=envelope_page(refs(1, city="Berlin"), total=1, place="Berlin"),
        )
    )
    collector = build_collector(ref_dir, panel)
    records = run(_collect(collector))
    dumped = json.dumps([r.model_dump(mode="json") for r in records])
    for forbidden in (
        "Private Job Title",
        "Private Employer GmbH",
        "jobdetail",
        "10000-0000000000-S",
    ):
        assert forbidden not in dumped


def test_write_panel_regions_side_file(tmp_path: Path) -> None:
    partition = tmp_path / "partition"
    partition.mkdir()
    path = write_panel_regions(partition, {"membership_hash": "abc", "regions": {}})
    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["membership_hash"] == "abc"


def test_crosswalk_fixture_shared_with_base_tests(tmp_path: Path) -> None:
    """The panel builder tolerates the base test crosswalk (no panel-only keys)."""
    panel = build_panel(write_crosswalk(tmp_path))
    assert [e.nuts_code for e in panel] == ["DE212", "DE300"]
