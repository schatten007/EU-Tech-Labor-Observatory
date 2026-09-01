"""Pin the frozen NUTS-3 panel: choose, verify and freeze one query per region.

Germany step 2b. The reference-only selection rule is degenerate in rural
regions (every municipality has one postcode, so the tie-break picks the
alphabetically first village), which cost the rejected sweep-1 attempt 30
regions of breadth. This script walks the deterministic candidate list of every
region, keeps the first candidate the source both **resolves to itself** and
reports **non-empty**, and writes the result to
``data/reference/ba_panel_nuts3.json`` — the committed, hashed panel definition
that every later sweep must reproduce byte-for-byte.

Evidence already collected (a previous sweep's ``panel_regions.json``) is reused
instead of re-requested, so only the regions that actually need a better anchor
cost requests. Serial, 1 s pacing, 403 cooldown, compact summary only.

Usage::

    python scripts/pin_ba_panel.py [--evidence <panel_regions.json> ...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.ba_jobsuche import (  # noqa: E402
    BA_PACING_SECONDS,
    BA_ROBOTS_URL,
    BA_SEARCH_URL,
    BA_THROTTLE_COOLDOWN_SECONDS,
    BA_USER_AGENT,
    parse_search_envelope,
)
from scrapers.ba_panel import (  # noqa: E402
    BA_PANEL_UMKREIS,
    PanelEntry,
    QueryForm,
    panel_candidates,
    panel_membership_hash,
    write_pinned_panel,
)

REFERENCE_DIR = Path("data/reference")
PANEL_ROOT = Path("data/raw/collections/ba/de-nuts3-panel")

_HEADERS = {
    "User-Agent": BA_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9",
}


def query_of(form: QueryForm, value: str) -> str:
    return f"wo={value}&umkreis={BA_PANEL_UMKREIS}"


def locality_ok(value: str, place: str | None, mode: str | None) -> bool:
    if mode == "UNGUELTIG" or not place:
        return False
    return place.split(",")[0].strip().casefold() == value.strip().casefold()


def load_evidence(paths: list[Path]) -> dict[str, dict[str, Any]]:
    """query string -> {advertised, resolved_place, search_mode} from past sweeps."""
    evidence: dict[str, dict[str, Any]] = {}
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for meta in payload.get("regions", {}).values():
            query = meta.get("query")
            if not query:
                continue
            evidence[query] = {
                "advertised": meta.get("advertised"),
                "resolved_place": meta.get("resolved_place"),
                "search_mode": meta.get("search_mode"),
                "source": f"sweep:{payload.get('sweep_id')}",
            }
    return evidence


async def probe(client: httpx.AsyncClient, query: str) -> tuple[int | None, str | None, str | None]:
    url = f"{BA_SEARCH_URL}&{query}&page=1"
    for attempt in (0, 1):
        response = await client.get(url)
        if response.status_code == 200:
            return parse_search_envelope(response.text)
        if response.status_code == 403 and attempt == 0:
            await asyncio.sleep(BA_THROTTLE_COOLDOWN_SECONDS)
            continue
        return (None, None, None)
    return (None, None, None)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, nargs="*", default=None)
    parser.add_argument("--max-requests", type=int, default=1200)
    args = parser.parse_args()

    evidence_paths = args.evidence
    if evidence_paths is None:
        evidence_paths = sorted(PANEL_ROOT.glob("*/panel_regions.json"))
    evidence = load_evidence([p for p in evidence_paths if p.exists()])

    candidates = panel_candidates(REFERENCE_DIR, max_candidates=6)
    kreis = {
        row["nuts_code"]: row
        for row in __import__("csv").DictReader(
            (REFERENCE_DIR / "germany_plz_nuts_2024.csv").open(encoding="utf-8")
        )
        if row["source_type"] == "kreis"
    }

    entries: list[PanelEntry] = []
    provenance: dict[str, dict[str, Any]] = {}
    requests_made = 0
    reused = 0
    unresolved: list[str] = []

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=_HEADERS) as client:
        await client.get(BA_ROBOTS_URL)
        for nuts_code in sorted(candidates):
            picked: tuple[QueryForm, str] | None = None
            picked_meta: dict[str, Any] = {}
            fallback: tuple[QueryForm, str] | None = None
            for form, value in candidates[nuts_code]:
                fallback = fallback or (form, value)
                query = query_of(form, value)
                known = evidence.get(query)
                if known is not None:
                    reused += 1
                    total = known["advertised"]
                    place = known["resolved_place"]
                    mode = known["search_mode"]
                    origin = known["source"]
                else:
                    if requests_made >= args.max_requests:
                        break
                    total, place, mode = await probe(client, query)
                    requests_made += 1
                    origin = "probe:2026-09-01"
                    evidence[query] = {
                        "advertised": total,
                        "resolved_place": place,
                        "search_mode": mode,
                        "source": origin,
                    }
                    await asyncio.sleep(BA_PACING_SECONDS)
                if total and locality_ok(value, place, mode):
                    picked = (form, value)
                    picked_meta = {
                        "advertised": total,
                        "resolved_place": place,
                        "search_mode": mode,
                        "evidence": origin,
                        "candidate_rank": candidates[nuts_code].index((form, value)),
                    }
                    break
            if picked is None:
                # Keep the region in the frame with its first candidate so the
                # panel stays complete; it simply contributes no rows.
                assert fallback is not None
                picked = fallback
                picked_meta = {
                    "advertised": evidence.get(query_of(*fallback), {}).get("advertised"),
                    "evidence": "no-candidate-resolved",
                    "candidate_rank": 0,
                }
                unresolved.append(nuts_code)
            entries.append(
                PanelEntry(
                    nuts_code=nuts_code,
                    nuts_label=kreis[nuts_code]["nuts_label"],
                    kreis_name=kreis[nuts_code]["kreis_name"],
                    form=picked[0],
                    value=picked[1],
                )
            )
            provenance[nuts_code] = picked_meta

    path = write_pinned_panel(
        REFERENCE_DIR,
        entries,
        {
            "pinned_at": "2026-09-01",
            "rule": "first candidate the source resolves to itself with >=1 hit",
            "candidate_order": "seat town, towns by postcode count, unambiguous "
            "postcodes, ambiguous seat name as last resort",
            "requests_made": requests_made,
            "evidence_reused": reused,
            "unresolved_regions": unresolved,
            "per_region": provenance,
        },
    )
    advertised = [provenance[c].get("advertised") or 0 for c in provenance]
    non_empty = sum(1 for value in advertised if value)
    print(f"pinned panel: {path}")
    print(f"regions: {len(entries)}  membership hash: {panel_membership_hash(entries)[:16]}...")
    print(f"requests made: {requests_made}  evidence reused: {reused}")
    print(f"regions with >=1 advertised posting: {non_empty}/{len(entries)}")
    print(f"unresolved regions: {len(unresolved)} {unresolved[:10]}")
    ranks = [provenance[c].get("candidate_rank", 0) for c in provenance]
    deep = sum(1 for rank in ranks if rank >= 2)
    print(f"candidate rank used: 0={ranks.count(0)} 1={ranks.count(1)} 2+={deep}")
    print(f"sum advertised across regions: {sum(advertised)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
