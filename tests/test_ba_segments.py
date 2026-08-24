"""Unit tests for the BA Jobsuche segmented regional census (Increment 9).

Covers the plan's §11 test list: the completeness oracle (empty page before the
400-page cap => complete; full 400th page => truncated => children enqueued at
the next level; only truncated nodes expand), breadth-first region ordering,
the three-tier region resolver (Tier 1 qualifier strip/alias, Tier 2 segment
context, Tier 3 single-NUTS-3 provenance under ``umkreis=0`` vs a radius),
non-geographic markers staying ``ambiguous``, the frontier round-trip and
resume semantics, budget stopping between segments, cross-segment dedupe, the
"inference never fabricates" guardrail, the 403-throttle path in segmented
mode, schema drift on level-0/1 page 1, and PII isolation of the city string
and segment label.

All HTTP is respx-mocked; no network in ``make check``. Synthetic markup only.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from scrapers.ba_jobsuche import (
    BA_BASE,
    BA_ROBOTS_URL,
    BA_SEARCH_URL,
    BAJobsucheCollector,
    GermanCrosswalk,
    normalize_location,
)
from scrapers.ba_segments import Segment, SegmentFrontier, build_initial_frontier
from scrapers.base import NormalizedRecord

KEY = b"test-only-key-with-at-least-32-bytes"

# A crosswalk covering: unique municipalities (Berlin, München, Starnberg,
# Heidelberg), a genuinely unknown name, an ambiguous name (Neunkirchen in
# DEC + DEA), a two-region ambiguous name (Aach), and PLZ rows (10178 Berlin,
# 82319 Starnberg) used for level-3 subdivision.
CROSSWALK = (
    "source_type,source_code,municipality_name,kreis_name,nuts_code,nuts_label,"
    "source_url,source_version\n"
    "plz,10178,Berlin,Berlin,DE300,Berlin,https://example.invalid/10178,2026-08-23\n"
    "plz,80331,München,München,DE212,München,https://example.invalid/80331,2026-08-23\n"
    "plz,82319,Starnberg,Starnberg,DE21I,Starnberg,https://example.invalid/82319,2026-08-23\n"
    "municipality,11000000,Berlin,Berlin,DE300,Berlin,https://example.invalid/vz250,2026-08-23\n"
    "municipality,09162000,München,München,DE212,München,https://example.invalid/vz250,2026-08-23\n"
    "municipality,09188000,Starnberg,Starnberg,DE21I,Starnberg,https://example.invalid/vz250,2026-08-23\n"
    "municipality,08221000,Heidelberg,Heidelberg,DE125,Heidelberg,https://example.invalid/vz250,2026-08-23\n"
    "municipality,10043000,Neunkirchen,Saarland,DEC02,Saarland,https://example.invalid/vz250,2026-08-23\n"
    "municipality,05162000,Neunkirchen,Nordrhein-Westfalen,DEA52,Nordrhein-Westfalen,"
    "https://example.invalid/vz250,2026-08-23\n"
    "municipality,08335000,Aach,Konstanz,DE138,Konstanz,https://example.invalid/vz250,2026-08-23\n"
    "municipality,08236000,Aach,Schwarzwald-Baar-Kreis,DE136,Schwarzwald-Baar-Kreis,"
    "https://example.invalid/vz250,2026-08-23\n"
    "municipality,01000000,Stadt Beispiel,Beispiel,DEG12,Beispiel,https://example.invalid/vz250,2026-08-23\n"
    "kreis,11000,Berlin,Berlin,DE300,Berlin,https://example.invalid/vz250,2026-08-23\n"
)


def write_crosswalk(tmp_path: Path) -> Path:
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "germany_plz_nuts_2024.csv").write_text(CROSSWALK, encoding="utf-8")
    return ref_dir


def item_html(
    ref: str,
    *,
    date: str = "19.08.2026",
    city: str = "Berlin",
) -> str:
    return f"""
    <li class="ba-tile ba-layoutless listeneintrag">
      <jb-job-listen-eintrag>
        <article class="ergebnisliste-item">
          <a role="button" href="{BA_BASE}/jobsuche/jobdetail/{ref}" id="i-{ref}">
            <h2 class="sr-only" id="i-{ref}-heading"><span>1: </span><span>Job</span></h2>
          </a>
          <div class="badge-lane"><span class="sr-only">Kennzeichnungen: </span></div>
          <div>
            <div class="h3 titel-lane" id="i-{ref}-titel"><span>{ref}</span></div>
            <div class="icon-lane">
              <span class="ba-icon" id="i-{ref}-arbeitsort">
                <span class="sr-only">Arbeitsort: </span><span>{city}</span>
              </span>
            </div>
          </div>
        </article>
        <div class="eintrag-meta-lane">
          <section class="eintrag-meta-lane-links ba-microcopy">
            <article>
              <span id="i-{ref}-datum" title="Veröffentlichungsdatum: {date}">
                <span class="sr-only">Veröffentlichungsdatum: </span>kürzlich
              </span>
            </article>
          </section>
        </div>
      </jb-job-listen-eintrag>
    </li>
    """


def search_page(refs: list[tuple[str, str]]) -> str:
    items = "".join(item_html(ref, city=city) for ref, city in refs)
    return f"""<!doctype html><html><head><title>Jobsuche</title></head><body>
<div id="ergebnisliste-liste-1">{items}</div></body></html>"""


def empty_page() -> str:
    return "<html><body><div id='ergebnisliste-liste-1'></div></body></html>"


def full_page(ref_base: str, city: str, count: int = 25) -> str:
    return search_page([(f"{ref_base}-{i}", city) for i in range(count)])


def run(coro: Coroutine[Any, Any, Any]) -> Any:
    return asyncio.run(coro)


async def _collect(collector: BAJobsucheCollector) -> list[NormalizedRecord]:
    records: list[NormalizedRecord] = []
    async with collector:
        async for record in collector.collect():
            records.append(record)
    return records


def make_collector(
    ref_dir: Path,
    tmp_path: Path,
    frontier: SegmentFrontier,
    *,
    max_segments: int | None = None,
    min_level: int = 0,
    umkreis: int = 0,
    scope_id: str = "de-stock-segmented",
) -> BAJobsucheCollector:
    return BAJobsucheCollector(
        scope_id=scope_id,
        sweep_id="20260824T000000Z",
        observed_at=datetime(2026, 8, 24, tzinfo=UTC),
        hmac_key=KEY,
        reference_dir=ref_dir,
        frontier=frontier,
        frontier_path=tmp_path / "ba_segment_frontier.json",
        max_segments=max_segments,
        min_level=min_level,
        umkreis=umkreis,
        pacing_interval=0.0,
    )


# ---------------------------------------------------------------------------
# normalize_location: Tier 1 qualifier / Tier 2 / markers
# ---------------------------------------------------------------------------


def test_qualifier_strip_and_alias(tmp_path: Path) -> None:
    cw = GermanCrosswalk(write_crosswalk(tmp_path))
    # "Heidelberg, Neckar": base unique, qualifier alias DE1 — mapped.
    r = normalize_location(cw, "Heidelberg, Neckar")
    assert r.status == "mapped"
    assert r.nuts_code == "DE125"
    assert r.method == "ba_city_qualifier_nuts3"
    # Plain city still resolves.
    r2 = normalize_location(cw, "Berlin")
    assert r2.status == "mapped"
    assert r2.nuts_code == "DE300"


def test_tier2_segment_context_disambiguates(tmp_path: Path) -> None:
    cw = GermanCrosswalk(write_crosswalk(tmp_path))
    # "Neunkirchen" alone is ambiguous (DEC02 Saarland / DEA52 NRW).
    r = normalize_location(cw, "Neunkirchen")
    assert r.status == "ambiguous"
    # Under a Saarland segment (nuts1=DEC) it narrows to the one candidate.
    r2 = normalize_location(cw, "Neunkirchen", segment_nuts1="DEC")
    assert r2.status == "mapped"
    assert r2.nuts_code == "DEC02"
    assert r2.method == "ba_segment_disambiguated"


def test_qualifier_alias_overrides_ambiguity(tmp_path: Path) -> None:
    cw = GermanCrosswalk(write_crosswalk(tmp_path))
    # "Neunkirchen, Saar" — the qualifier names the Saarland (DEC).
    r = normalize_location(cw, "Neunkirchen, Saar")
    assert r.status == "mapped"
    assert r.nuts_code == "DEC02"


def test_non_geographic_markers_are_ambiguous(tmp_path: Path) -> None:
    cw = GermanCrosswalk(write_crosswalk(tmp_path))
    r = normalize_location(cw, "Verschiedene Arbeitsorte")
    assert r.status == "ambiguous"
    assert r.method == "ba_location_multiple"
    r2 = normalize_location(cw, "Deutschland")
    assert r2.status == "ambiguous"
    assert r2.method == "ba_location_nationwide"
    r3 = normalize_location(cw, "Bundesweit")
    assert r3.status == "ambiguous"
    assert r3.method == "ba_location_nationwide"
    # A marker under a segment is never force-mapped by Tier 3 — the collector
    # only applies Tier 3 when the Tier-1/2 status is unmapped.
    r4 = normalize_location(cw, "Verschiedene Arbeitsorte", segment_nuts3="DE300")
    assert r4.status == "ambiguous"


def test_genuine_miss_stays_unmapped(tmp_path: Path) -> None:
    cw = GermanCrosswalk(write_crosswalk(tmp_path))
    r = normalize_location(cw, "Nichtexistenz")
    assert r.status == "unmapped"
    assert r.method == "not_available"


def test_build_frontier_city_state_pre_subdivided(tmp_path: Path) -> None:
    """Berlin/Bremen/Hamburg are both states and cities: the identical level-2
    municipality segment covers the whole state, so the level-1 segment is
    pre-marked subdivided (never probed) instead of colliding in the frontier."""
    ref_dir = write_crosswalk(tmp_path)
    frontier = build_initial_frontier(GermanCrosswalk(ref_dir), umkreis=0)
    # Berlin exists at both levels with the same key, distinguished by level.
    l1 = frontier.get("wo=Berlin&umkreis=0", level=1)
    l2 = frontier.get("wo=Berlin&umkreis=0", level=2)
    assert l1 is not None and l1.status == "subdivided"
    assert l2 is not None and l2.status == "pending"
    assert l2.nuts_code == "DE300"
    # A non-city-state Bundesland stays pending (to be probed).
    bayern = frontier.get("wo=Bayern&umkreis=0", level=1)
    assert bayern is not None and bayern.status == "pending"
    assert bayern.nuts1 == "DE2"
    # The pending() order yields level 2 first, then level 0/1.
    pending = list(frontier.pending())
    assert all(s.level == 2 for s in pending[:3])


# ---------------------------------------------------------------------------
# Completeness oracle and subdivision
# ---------------------------------------------------------------------------


def _mock_segment(
    respx_mock: respx.MockRouter,
    key: str,
    *,
    pages: list[str] | None = None,
    all_full_until_400: bool = False,
) -> None:
    """Mock every page of one segment. ``pages`` maps page numbers to bodies
    (index 0 = page 1); if ``all_full_until_400`` every page returns 25 items."""
    import re as _re

    if all_full_until_400:
        respx_mock.get(
            url__regex=_re.compile(rf"{_re.escape(BA_SEARCH_URL)}&{_re.escape(key)}&page=\d+")
        ).mock(side_effect=lambda req: httpx.Response(200, text=full_page("10000", "Berlin")))
        return
    for idx, body in enumerate(pages or []):
        respx_mock.get(f"{BA_SEARCH_URL}&{key}&page={idx + 1}").mock(
            return_value=httpx.Response(200, text=body)
        )


def test_oracle_complete_before_cap(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Starnberg&umkreis=0"
    _mock_segment(
        respx_mock,
        key,
        pages=[search_page([("10001", "Starnberg")]), empty_page()],
    )
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE21I", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier)
    records = run(_collect(collector))
    assert len(records) == 1
    segment = frontier.get(key)
    assert segment is not None
    assert segment.status == "complete"
    assert segment.rows_yielded == 1
    assert collector.segments_complete == 1
    assert collector.segments_truncated == 0


def test_oracle_truncated_subdivides_into_plz_children(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Berlin&umkreis=0"
    # Every page (including page 400) is full -> truncated.
    _mock_segment(respx_mock, key, all_full_until_400=True)
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE300", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier, max_segments=1)
    records = run(_collect(collector))
    assert len(records) == 25  # only the last (400th) page's unique items
    segment = frontier.get(key)
    assert segment is not None
    assert segment.status == "subdivided"
    assert collector.segments_truncated == 1
    # Children enqueued at level 3: Berlin's PLZ rows (10178).
    children = [s for s in frontier.segments.values() if s.level == 3]
    assert any(s.key == "wo=10178&umkreis=0" and s.nuts_code == "DE300" for s in children)


def test_only_truncated_nodes_expand(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    small = "wo=Starnberg&umkreis=0"
    big = "wo=Berlin&umkreis=0"
    _mock_segment(respx_mock, small, pages=[search_page([("10001", "Starnberg")]), empty_page()])
    _mock_segment(respx_mock, big, all_full_until_400=True)
    frontier = SegmentFrontier(
        [
            Segment(key=small, level=2, nuts_code="DE21I", umkreis=0),
            Segment(key=big, level=2, nuts_code="DE300", umkreis=0),
        ]
    )
    collector = make_collector(ref_dir, tmp_path, frontier)
    run(_collect(collector))
    small_seg = frontier.get(small)
    assert small_seg is not None and small_seg.status == "complete"
    # Only the truncated segment gained level-3 children.
    assert not any(s.level == 3 for s in frontier.segments.values() if s.parent == small)
    assert any(s.level == 3 for s in frontier.segments.values() if s.parent == big)


def test_breadth_first_level2_before_level3(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    l2 = "wo=Starnberg&umkreis=0"
    l3 = "wo=10178&umkreis=0"
    # The level-3 child is present in the frontier from the start; with a
    # budget of 1 segment, the level-2 backbone segment must be processed first.
    _mock_segment(respx_mock, l2, pages=[search_page([("10001", "Starnberg")]), empty_page()])
    _mock_segment(respx_mock, l3, pages=[search_page([("10002", "Berlin")]), empty_page()])
    frontier = SegmentFrontier(
        [
            Segment(key=l2, level=2, nuts_code="DE21I", umkreis=0),
            Segment(key=l3, level=3, nuts_code="DE300", umkreis=0),
        ]
    )
    collector = make_collector(ref_dir, tmp_path, frontier, max_segments=1)
    records = run(_collect(collector))
    assert records and records[0].nuts_code == "DE21I"
    l2_seg = frontier.get(l2)
    l3_seg = frontier.get(l3)
    assert l2_seg is not None and l2_seg.status == "complete"
    assert l3_seg is not None and l3_seg.status == "pending"


# ---------------------------------------------------------------------------
# Tier 3 in the pipeline
# ---------------------------------------------------------------------------


def test_tier3_provenance_mapped_under_umkreis0(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Berlin&umkreis=0"
    # A label the crosswalk does not know, collected under the Berlin segment.
    _mock_segment(respx_mock, key, pages=[search_page([("10001", "Berlin-Wedding")]), empty_page()])
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE300", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier, umkreis=0)
    records = run(_collect(collector))
    assert len(records) == 1
    r = records[0]
    assert r.region_mapping_status == "mapped"
    assert r.region_mapping_method == "ba_segment_provenance_nuts3"
    assert r.nuts_code == "DE300"


def test_tier3_radius_is_low_confidence(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Berlin&umkreis=25"
    _mock_segment(respx_mock, key, pages=[search_page([("10001", "Berlin-Wedding")]), empty_page()])
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE300", umkreis=25)])
    collector = make_collector(ref_dir, tmp_path, frontier, umkreis=25)
    records = run(_collect(collector))
    assert records[0].region_mapping_status == "low_confidence"
    assert records[0].region_mapping_method == "ba_segment_radius_nuts3"


def test_tier3_never_overrides_ambiguous_marker(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Berlin&umkreis=0"
    _mock_segment(
        respx_mock, key, pages=[search_page([("10001", "Verschiedene Arbeitsorte")]), empty_page()]
    )
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE300", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier)
    records = run(_collect(collector))
    assert records[0].region_mapping_status == "ambiguous"
    assert records[0].region_mapping_method == "ba_location_multiple"
    assert records[0].nuts_code is None


# ---------------------------------------------------------------------------
# Thresholds on a synthetic multi-region fixture (plan §9 DoD proof)
# ---------------------------------------------------------------------------


def _threshold_crosswalk(tmp_path: Path) -> Path:
    """400 municipalities, one per synthetic NUTS 3 code (DE100..DE499)."""
    rows = [
        "source_type,source_code,municipality_name,kreis_name,nuts_code,nuts_label,"
        "source_url,source_version"
    ]
    for i in range(400):
        code = f"DE{100 + i:03d}"
        rows.append(
            f"municipality,{10000 + i:08d},Stadt {code},{code},{code},{code},"
            f"https://example.invalid/vz250,2026-08-23"
        )
    ref_dir = tmp_path / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    (ref_dir / "germany_plz_nuts_2024.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return ref_dir


def test_threshold_assertions_synthetic_multi_segment(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = _threshold_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    frontier = build_initial_frontier(GermanCrosswalk(ref_dir), umkreis=0)
    # The frontier has level 0 + 16 level-1 + 400 level-2 segments. Run only
    # the level-2 backbone: one posting per municipality -> 400 mapped rows.

    def handler(req: httpx.Request) -> httpx.Response:
        city = req.url.params.get("wo", "")
        if req.url.params.get("page") != "1":
            return httpx.Response(200, text=empty_page())
        ref = f"r-{city.replace(' ', '_')}"
        return httpx.Response(200, text=search_page([(ref, city)]))

    respx_mock.get(url__regex=r"wo=Stadt%20DE\d+&umkreis=0&page=\d+").mock(side_effect=handler)
    collector = make_collector(
        ref_dir,
        tmp_path,
        frontier,
        max_segments=400,
        min_level=2,
    )
    records = run(_collect(collector))
    # 400 municipalities -> 400 rows, all Tier-1 mapped, one per NUTS 3.
    assert len(records) == 400
    mapped = [r for r in records if r.region_mapping_status == "mapped"]
    assert len(mapped) / len(records) >= 0.85
    distinct_nuts = {r.nuts_code for r in records if r.region_mapping_status == "mapped"}
    assert len(distinct_nuts) >= 390
    assert len(distinct_nuts) == 400
    tier1 = sum(1 for r in records if r.region_mapping_method == "ba_city_municipality_nuts3")
    assert tier1 == 400
    # Every level-2 segment is complete; no fabricated rows.
    complete = [s for s in frontier.segments.values() if s.level == 2 and s.status == "complete"]
    assert len(complete) == 400
    total_rows = sum(s.rows_yielded for s in complete)
    assert total_rows == len(records)


# ---------------------------------------------------------------------------
# Frontier persistence, resume, budget
# ---------------------------------------------------------------------------


def test_frontier_round_trip_and_resume(tmp_path: Path) -> None:
    path = tmp_path / "ba_segment_frontier.json"
    frontier = SegmentFrontier(
        [
            Segment(key="a", level=2, nuts_code="DE300", status="complete", rows_yielded=5),
            Segment(key="b", level=2, nuts_code="DE21I", status="pending"),
            Segment(key="c", level=3, nuts_code="DE300", status="failed"),
        ]
    )
    frontier.save(path)
    loaded = SegmentFrontier.load(path)
    assert len(loaded) == 3
    seg_a = loaded.get("a")
    assert seg_a is not None and seg_a.status == "complete"
    # Resume continues from pending/failed only.
    pending = list(loaded.pending())
    assert [s.key for s in pending] == ["b", "c"]


def test_budget_stops_between_segments(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    keys = [f"wo=Stadt{i}&umkreis=0" for i in range(3)]
    frontier = SegmentFrontier(
        [Segment(key=k, level=2, nuts_code="DE300", umkreis=0) for k in keys]
    )
    for i, k in enumerate(keys):
        _mock_segment(respx_mock, k, pages=[search_page([(f"10000-{i}", "Berlin")]), empty_page()])
    collector = make_collector(ref_dir, tmp_path, frontier, max_segments=2)
    records = run(_collect(collector))
    assert len(records) == 2
    s0 = frontier.get(keys[0])
    s1 = frontier.get(keys[1])
    s2 = frontier.get(keys[2])
    assert s0 is not None and s0.status == "complete"
    assert s1 is not None and s1.status == "complete"
    assert s2 is not None and s2.status == "pending"


def test_cross_segment_overlap_dedupes(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key_a = "wo=Berlin&umkreis=0"
    key_b = "wo=10178&umkreis=0"
    # Same native id appears in both segments; the PLZ child shares it too.
    _mock_segment(respx_mock, key_a, pages=[search_page([("10000", "Berlin")]), empty_page()])
    _mock_segment(respx_mock, key_b, pages=[search_page([("10000", "Berlin")]), empty_page()])
    frontier = SegmentFrontier(
        [
            Segment(key=key_a, level=2, nuts_code="DE300", umkreis=0),
            Segment(key=key_b, level=3, nuts_code="DE300", umkreis=0),
        ]
    )
    collector = make_collector(ref_dir, tmp_path, frontier)
    records = run(_collect(collector))
    assert len(records) == 1
    assert collector.duplicates_dropped == 1


def test_throttle_403_then_success_segmented(
    tmp_path: Path, respx_mock: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scrapers.ba_jobsuche as mod

    monkeypatch.setattr(mod, "BA_THROTTLE_COOLDOWN_SECONDS", 0.0)
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Starnberg&umkreis=0"
    respx_mock.get(f"{BA_SEARCH_URL}&{key}&page=1").mock(
        side_effect=[
            httpx.Response(403, text="Access forbidden!"),
            httpx.Response(200, text=search_page([("10001", "Starnberg")])),
        ]
    )
    respx_mock.get(f"{BA_SEARCH_URL}&{key}&page=2").mock(
        return_value=httpx.Response(200, text=empty_page())
    )
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE21I", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier)
    records = run(_collect(collector))
    assert len(records) == 1
    assert collector.throttle_events == 1
    assert collector.failed_pages == 0


def test_schema_drift_on_level0_page1_fails_loudly(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(200, text="<html><body>drift</body></html>")
    )
    frontier = SegmentFrontier([Segment(key="", level=0, umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier)
    with pytest.raises(RuntimeError, match="page structure may have changed"):
        run(_collect(collector))


def test_pii_city_and_segment_label_never_reach_output(
    tmp_path: Path, respx_mock: respx.MockRouter
) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    key = "wo=Berlin&umkreis=0"
    _mock_segment(respx_mock, key, pages=[search_page([("10000", "Berlin-Wedding")]), empty_page()])
    frontier = SegmentFrontier([Segment(key=key, level=2, nuts_code="DE300", umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier)
    records = run(_collect(collector))
    blob = str(records[0].model_dump(mode="json"))
    assert "Berlin-Wedding" not in blob
    assert "wo=Berlin" not in blob
    assert "umkreis" not in blob
    assert "10000-1202838080" not in blob


def test_unscoped_segment_never_invokes_tier3(tmp_path: Path, respx_mock: respx.MockRouter) -> None:
    ref_dir = write_crosswalk(tmp_path)
    respx_mock.get(BA_ROBOTS_URL).mock(return_value=httpx.Response(200, text=""))
    # Level 0 (unscoped) collects an unmapped city -> stays unmapped: it has no
    # single-NUTS-3 provenance, so Tier 3 must not fire.
    respx_mock.get(f"{BA_SEARCH_URL}&page=1").mock(
        return_value=httpx.Response(200, text=search_page([("10000", "Nichtexistenz")]))
    )
    respx_mock.get(f"{BA_SEARCH_URL}&page=2").mock(
        return_value=httpx.Response(200, text=empty_page())
    )
    frontier = SegmentFrontier([Segment(key="", level=0, umkreis=0)])
    collector = make_collector(ref_dir, tmp_path, frontier, max_segments=1)
    records = run(_collect(collector))
    assert records[0].region_mapping_status == "unmapped"
    assert records[0].region_mapping_method == "not_available"
