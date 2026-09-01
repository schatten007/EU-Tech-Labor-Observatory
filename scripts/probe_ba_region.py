"""Region-addressing probe: which ``wo=`` form reliably addresses a Kreis?

Germany step 2b, probe 2 (SCRAPER_ROADMAP.md 2b.2). Prior probes broke
``wo=Landkreis+…`` (all forms returned the same 7 Rosenheim postings) and
compound names such as ``Rhein-Sieg-Kreis`` fuzzy-missed to wrong regions.

The 400-unit frame is the ``source_type == "kreis"`` slice of the pinned
crosswalk (``data/reference/germany_plz_nuts_2024.csv``), which is the destatis
Kreise AGS->NUTS 2024 key.

Two modes, both printing a compact summary only:

* ``--shape`` -- print the SSR-state key shape once (top-level keys, the
  ``suchergebnis`` keys, and the keys of one result tile). No values beyond
  short scalars, never raw HTML.
* default -- test each candidate ``wo=`` form against a state-stratified sample
  of Kreise and print one line per tested Kreis
  (``key -> resolved NUTS 3 -> hit/miss``) plus totals.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.ba_jobsuche import (  # noqa: E402
    BA_BASE,
    BA_PACING_SECONDS,
    BA_USER_AGENT,
)

REFERENCE_CSV = Path("data/reference/germany_plz_nuts_2024.csv")
_NG_STATE = re.compile(
    r"<script[^>]*id=[\"']ng-state[\"'][^>]*>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)

_HEADERS = {
    "User-Agent": BA_USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "de-DE,de;q=0.9",
}

# Filled by probe_forms() before candidate_queries() is called.
_TOWNS: dict[str, tuple[str, str]] = {}
_LIMIT = 0


def load_frame() -> tuple[
    list[dict[str, str]], dict[str, str], dict[str, str], dict[str, list[str]]
]:
    """Return (kreis rows, plz->nuts, municipality->nuts if unique, nuts->plz list)."""
    rows = list(csv.DictReader(REFERENCE_CSV.open(encoding="utf-8")))
    kreis_rows = [r for r in rows if r["source_type"] == "kreis"]
    plz_to_nuts = {r["source_code"]: r["nuts_code"] for r in rows if r["source_type"] == "plz"}
    muni_counts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_type"] == "municipality":
            muni_counts[row["municipality_name"].casefold()].add(row["nuts_code"])
    muni_to_nuts = {
        name: next(iter(codes)) for name, codes in muni_counts.items() if len(codes) == 1
    }
    nuts_to_plz: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        if row["source_type"] == "plz":
            nuts_to_plz[row["nuts_code"]].append(row["source_code"])
    return kreis_rows, plz_to_nuts, muni_to_nuts, dict(nuts_to_plz)


def anchor_plz_by_nuts() -> dict[str, str]:
    """Deterministic anchor postcode per NUTS-3, derived from the reference only.

    Rule: within a NUTS-3 region, pick the municipality with the most postcode
    rows (a pure reference-derived proxy for the region's largest town, since
    big towns carry many postcodes), then its lexicographically smallest
    postcode. Ties break on the municipality name, so the result is stable and
    byte-identical across sweeps without any measurement or randomization.
    Postcodes that map to more than one NUTS-3 are excluded: they cannot carry
    single-region provenance (11 such codes, e.g. 76829 -> DEB33/DEB3H).
    """
    rows = [
        r for r in csv.DictReader(REFERENCE_CSV.open(encoding="utf-8")) if r["source_type"] == "plz"
    ]
    codes_to_nuts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        codes_to_nuts[row["source_code"]].add(row["nuts_code"])
    unambiguous = {code for code, nuts in codes_to_nuts.items() if len(nuts) == 1}
    by_region: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for row in rows:
        if row["source_code"] in unambiguous:
            by_region[row["nuts_code"]][row["municipality_name"]].append(row["source_code"])
    anchors: dict[str, str] = {}
    for nuts_code, municipalities in by_region.items():
        best_name = max(sorted(municipalities), key=lambda name: len(municipalities[name]))
        anchors[nuts_code] = min(municipalities[best_name])
    return anchors


def anchor_town_by_nuts() -> dict[str, tuple[str, str]]:
    """Deterministic anchor *town* per NUTS-3: (query form, query value).

    The census locked municipality-name segments as reliable (unique names carry
    single-NUTS-3 provenance); Kreis names that are not towns do not resolve at
    all. So the panel addresses each region by its largest town:

    * ``("name", <municipality>)`` when that municipality name is unique in the
      whole register -- the largest town is the one with the most postcode rows;
    * ``("plz", <postcode>)`` otherwise, reusing the unambiguous anchor
      postcode, exactly as the census resolved its 397 ambiguous names.
    """
    rows = list(csv.DictReader(REFERENCE_CSV.open(encoding="utf-8")))
    name_to_nuts: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_type"] == "municipality":
            name_to_nuts[row["municipality_name"].casefold()].add(row["nuts_code"])
    unique_names = {name for name, codes in name_to_nuts.items() if len(codes) == 1}
    plz_rows = [r for r in rows if r["source_type"] == "plz"]
    by_region: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in plz_rows:
        by_region[row["nuts_code"]][row["municipality_name"]].add(row["source_code"])
    anchors = anchor_plz_by_nuts()
    result: dict[str, tuple[str, str]] = {}
    for nuts_code, municipalities in by_region.items():
        ranked = sorted(
            municipalities,
            key=lambda name: (-len(municipalities[name]), name),
        )
        chosen = next((name for name in ranked if name.casefold() in unique_names), None)
        if chosen is not None:
            result[nuts_code] = ("name", chosen)
        elif nuts_code in anchors:
            result[nuts_code] = ("plz", anchors[nuts_code])
    return result


def stratified_sample(kreis_rows: list[dict[str, str]], size: int = 20) -> list[dict[str, str]]:
    """State-stratified deterministic sample: one Kreis per NUTS-1, then extras
    from the largest states until ``size`` is reached."""
    by_state: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in kreis_rows:
        by_state[row["nuts_code"][:3]].append(row)
    states = sorted(by_state)
    sample: list[dict[str, str]] = []
    for state in states:
        members = sorted(by_state[state], key=lambda r: r["nuts_code"])
        # Take from the middle so the sample is not all Kreisfreie Stadte.
        sample.append(members[len(members) // 2])
    largest = sorted(states, key=lambda s: (-len(by_state[s]), s))
    offset = 1
    while len(sample) < size:
        for state in largest:
            if len(sample) >= size:
                break
            members = sorted(by_state[state], key=lambda r: r["nuts_code"])
            index = (len(members) // 2 + offset) % len(members)
            candidate = members[index]
            if candidate not in sample:
                sample.append(candidate)
        offset += 1
    return sample


def extract_state(html: str) -> dict[str, Any] | None:
    match = _NG_STATE.search(html)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def find_result_block(state: dict[str, Any]) -> dict[str, Any] | None:
    for value in state.values():
        if isinstance(value, dict) and "maxErgebnisse" in value:
            return value
    return None


def tiles_of(block: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("stellenangebote", "jobs", "ergebnisse", "items"):
        value = block.get(key)
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    for value in block.values():
        if isinstance(value, list) and value and isinstance(value[0], dict):
            return value
    return []


def tile_location(tile: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (plz, ort) from a result tile, allowlist keys only.

    ``stellenlokationen[].adresse`` also carries ``strasse``; it is never read
    here and must never be stored (PII ban, SCRAPERS.md golden rule 4).
    """
    places = tile.get("stellenlokationen")
    if isinstance(places, list) and places and isinstance(places[0], dict):
        address = places[0].get("adresse")
        if isinstance(address, dict):
            plz = address.get("plz")
            ort = address.get("ort")
            return (str(plz) if plz else None, str(ort) if ort else None)
    return (None, None)


async def probe_shape(client: httpx.AsyncClient) -> int:
    url = f"{BA_BASE}/jobsuche/suche?wo=Rosenheim&page=1"
    response = await client.get(url)
    state = extract_state(response.text)
    lines = ["PROBE ba-region shape"]
    if state is None:
        lines.append("ng-state: unparseable")
        print("\n".join(lines))
        return 1
    lines.append("state keys: " + ", ".join(sorted(state)[:6]))
    block = find_result_block(state)
    if block is None:
        lines.append("result block: absent")
        print("\n".join(lines))
        return 1
    lines.append("result keys: " + ", ".join(sorted(block)[:12]))
    tiles = tiles_of(block)
    lines.append(f"tiles: {len(tiles)}")
    lines.append("woOutput: " + json.dumps(block.get("woOutput"), ensure_ascii=False)[:200])
    if tiles:
        lines.append("tile keys: " + ",".join(sorted(tiles[0])))
        for key, value in sorted(tiles[0].items()):
            if isinstance(value, dict):
                lines.append(f"tile.{key}: " + json.dumps(value, ensure_ascii=False)[:180])
            elif isinstance(value, list) and value:
                lines.append(f"tile.{key}[0]: " + json.dumps(value[0], ensure_ascii=False)[:200])
    print("\n".join(lines[:20]))
    return 0


def candidate_queries(
    row: dict[str, str],
    nuts_to_plz: dict[str, list[str]],
    anchors: dict[str, str],
    form: str,
) -> str | None:
    name = row["kreis_name"]
    nuts = row["nuts_code"]
    if form == "plain":
        return f"wo={name}"
    if form == "plain0":
        return f"wo={name}&umkreis=0"
    if form == "label":
        # e.g. "Rosenheim, Landkreis" -- the destatis/GISCO NUTS label form.
        return f"wo={row['nuts_label']}&umkreis=0"
    if form == "lk":
        return f"wo=Landkreis {name}&umkreis=0"
    if form == "plz0":
        codes = sorted(nuts_to_plz.get(nuts, []))
        return f"wo={codes[0]}&umkreis=0" if codes else None
    if form == "anchor":
        anchor = anchors.get(nuts)
        return f"wo={anchor}&umkreis=0" if anchor else None
    if form == "anchor25":
        anchor = anchors.get(nuts)
        return f"wo={anchor}&umkreis=25" if anchor else None
    if form == "town":
        town = _TOWNS.get(nuts)
        return f"wo={town[1]}&umkreis=0" if town else None
    raise ValueError(form)


async def _get_state(client: httpx.AsyncClient, url: str) -> dict[str, Any] | None:
    """Fetch with one throttle cooldown, mirroring the collector's 403 policy."""
    for attempt in (0, 1):
        try:
            response = await client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code == 200:
            state = extract_state(response.text)
            if state is not None:
                return state
        if attempt == 0:
            # BA's Apache edge token bucket answers 403 after ~50 requests;
            # a 45 s idle window refills it (SCRAPER_FEASIBILITY.md).
            await asyncio.sleep(45.0)
    return None


async def probe_forms(client: httpx.AsyncClient, forms: list[str]) -> int:
    kreis_rows, plz_to_nuts, muni_to_nuts, nuts_to_plz = load_frame()
    anchors = anchor_plz_by_nuts()
    _TOWNS.update(anchor_town_by_nuts())
    sample = stratified_sample(kreis_rows, size=20)
    if _LIMIT:
        sample = sample[:_LIMIT]
    lines = [f"PROBE ba-region addressing (forms={','.join(forms)}, n={len(sample)})"]
    totals: dict[str, list[int]] = {form: [0, 0, 0] for form in forms}
    for form in forms:
        for row in sample:
            query = candidate_queries(row, nuts_to_plz, anchors, form)
            if query is None:
                totals[form][1] += 1
                totals[form][2] += 1
                continue
            url = f"{BA_BASE}/jobsuche/suche?{query}&page=1"
            state = await _get_state(client, url)
            block = find_result_block(state) if state else None
            total = block.get("maxErgebnisse") if block else None
            tiles = tiles_of(block) if block else []
            resolved: list[str] = []
            for tile in tiles[:10]:
                plz, ort = tile_location(tile)
                code = None
                if plz and plz in plz_to_nuts:
                    code = plz_to_nuts[plz]
                elif ort and ort.casefold() in muni_to_nuts:
                    code = muni_to_nuts[ort.casefold()]
                if code:
                    resolved.append(code)
            in_kreis = sum(1 for code in resolved if code == row["nuts_code"])
            locality = in_kreis / len(resolved) if resolved else 0.0
            hit = bool(total) and locality >= 0.8
            if hit:
                totals[form][0] += 1
            else:
                totals[form][1] += 1
            totals[form][2] += 1
            echo = ""
            mode = ""
            wo_output = block.get("woOutput") if block else None
            if isinstance(wo_output, dict):
                echo = str(wo_output.get("bereinigterOrt", ""))[:22]
                mode = str(wo_output.get("suchmodus", ""))[:16]
            lines.append(
                f"{form} {row['nuts_code']} {row['kreis_name'][:18]} "
                f"q={query.split('=')[1].split('&')[0][:16]} "
                f"total={total} loc={in_kreis}/{len(resolved)} "
                f"mode={mode} echo={echo} {'HIT' if hit else 'MISS'}"
            )
            await asyncio.sleep(BA_PACING_SECONDS)
    print("\n".join(lines))
    print(
        "TOTALS " + " | ".join(f"{form}: {vals[0]}/{vals[2]} hit" for form, vals in totals.items())
    )
    return 0


async def main() -> int:
    global _LIMIT
    parser = argparse.ArgumentParser()
    parser.add_argument("--shape", action="store_true")
    parser.add_argument("--forms", default="plain0")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    _LIMIT = args.limit
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=_HEADERS) as client:
        if args.shape:
            return await probe_shape(client)
        return await probe_forms(client, args.forms.split(","))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
