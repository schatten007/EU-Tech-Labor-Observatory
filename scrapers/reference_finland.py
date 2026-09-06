"""Build the pinned Finnish kunta/maakunta -> NUTS 2024 crosswalk (opt-in network).

Increment 7 (Finland). The P67 payload gives **codes, not names**
(``location.municipalities`` = KUNTA codes at ``maxLength 3``,
``location.regions`` = MAAKUNTA codes at ``maxLength 2``), so this crosswalk is
code-keyed and needs no name folding — unlike Increment 6, where NAV forced a
name join and Sami dual names had to be reconciled.

The obvious source is **not** used on purpose: Työmarkkinatori publishes its own
``KUNTA`` and ``MAAKUNTA`` codesets at
``https://tyomarkkinatori.fi/api/codes/v1/kopa/<CODESET>/koodit``, but the
portal's ``robots.txt`` says ``Disallow: /api/`` (and ``Disallow: /*/api/``), so
those paths are off-limits under the charter's first golden rule and are not
fetched, not even once. Statistics Finland serves the same relation as an
official classification key and is the better authority anyway.

Three authoritative inputs, all verified live on 2026-08-23:

1. **Eurostat GISCO NUTS 2024** attribute table — the authority for the target
   codes and labels::

       GET https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv

   Finland has **19 NUTS 3 codes** (a 5-character ``NUTS_ID`` is level 3):
   ``FI196`` Satakunta, ``FI198`` Keski-Suomi, ``FI199`` Etelä-Pohjanmaa,
   ``FI19A`` Pohjanmaa, ``FI19B`` Pirkanmaa, ``FI1B1`` Helsinki-Uusimaa,
   ``FI1C1`` Varsinais-Suomi, ``FI1C2`` Kanta-Häme, ``FI1C5`` Etelä-Karjala,
   ``FI1C6`` Päijät-Häme, ``FI1C7`` Kymenlaakso, ``FI1D5`` Keski-Pohjanmaa,
   ``FI1D7`` Lappi, ``FI1D8`` Kainuu, ``FI1D9`` Pohjois-Pohjanmaa, ``FI1DA``
   Etelä-Savo, ``FI1DB`` Pohjois-Savo, ``FI1DC`` Pohjois-Karjala, ``FI200``
   Åland.

2. **Statistics Finland classification key ``kunta_1_20260101#nuts_2_20260101``**
   (open JSON, no key; ``data.stat.fi/robots.txt`` is 404, i.e. absent)::

       GET https://data.stat.fi/api/classifications/v2/correspondenceTables/
           kunta_1_20260101%23nuts_2_20260101/maps

   The table describes itself as *"Vuoden 2026 kuntien ja NUTS 1-3, Suomi
   hierarkia -luokituksen (**virallinen NUTS 2024**) välinen luokitusavain"* and
   returns **924 maps = 308 municipalities × NUTS levels 1, 2 and 3**. Only the
   level-3 maps are kept.

3. **Statistics Finland key ``kunta_1_20260101#maakunta_1_20260101``** (same
   host): 308 maps, municipality -> region.

The maakunta layer is **derived and then verified, never assumed**: folding
kunta -> maakunta against kunta -> NUTS 3 must give exactly one NUTS 3 code per
maakunta. It does (19 maakunnat, 0 ambiguous), which is the empirical proof that
a Finnish maakunta *is* a NUTS 3 region — so ``location.regions`` can be resolved
as confidently as ``location.municipalities``. Should a future vintage break
that, the offending maakunta is written as ``maakunta-ambiguous`` **with no
code** so the collector reports ``ambiguous`` instead of picking a region.

Loud failures, matching the Increment 4/5/6 bar of 0 unmatched:

- a level-3 NUTS code that Eurostat GISCO NUTS 2024 does not know **raises**;
- a municipality present in one key but missing from the other **raises**;
- an empty response from either key **raises**.

Like Increment 6 this is **three requests**, so no resume state is needed (and
none is pretended); ``get``/``sleep`` are injected so the tests drive it without
network or delay.

Run once per Statistics Finland / NUTS vintage change::

    python -m scrapers.reference_finland            # 3 paced requests, seconds

Outputs (committed so the offline gate keeps working)::

    data/reference/finland_tmt_region_nuts_2024.csv
    data/reference/reference_manifest_finland.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from scrapers.finland_tmt import (
    KUNTA_KEY,
    MAAKUNTA_AMBIGUOUS_KEY,
    MAAKUNTA_KEY,
    TMT_REFERENCE_FILE,
    normalize_kunta_code,
    normalize_maakunta_code,
)

#: Eurostat GISCO NUTS 2024 attribute table (CNTR_CODE, NUTS_ID, NAME_LATN, ...).
GISCO_NUTS_2024_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv"
)
STAT_FI_BASE = "https://data.stat.fi/api/classifications/v2/correspondenceTables"

#: Statistics Finland classification vintage. Bump this when a new year's
#: ``kunta_1_YYYYMMDD#nuts_2_YYYYMMDD`` key is published (municipalities merge).
CLASSIFICATION_DATE = "20260101"

#: Snapshot tag for the pinned file (date the classifications were read).
SOURCE_VERSION = "2026-08-23"

#: Header of every crosswalk CSV, matching data/reference/geography_nuts_2024.csv.
COLUMNS = ("source_type", "source_code", "nuts_code", "nuts_label", "source_url", "source_version")

MANIFEST_FILE = "reference_manifest_finland.json"

USER_AGENT = "EU-Tech-Labour-Observatory/0.1 (robots-and-ToS-compliant, reference build)"

#: A NUTS 3 identifier is five characters (``FI1B1``); level is not a CSV column.
NUTS3_ID_LENGTH = 5
#: Only the level-3 target maps of the kunta -> NUTS key are kept.
NUTS3_LEVEL = 3
#: Charter pacing floor: never faster than one request per second per host.
PACING_SECONDS = 1.0

#: Query parameters used for both classification keys (verified live).
MAPS_PARAMS = {"content": "data", "meta": "min", "lang": "fi"}


def kunta_nuts_url(date: str = CLASSIFICATION_DATE) -> str:
    """URL of the municipality -> NUTS 2024 key (``#`` percent-encoded)."""
    return f"{STAT_FI_BASE}/kunta_1_{date}%23nuts_2_{date}/maps"


def kunta_maakunta_url(date: str = CLASSIFICATION_DATE) -> str:
    """URL of the municipality -> region key (``#`` percent-encoded)."""
    return f"{STAT_FI_BASE}/kunta_1_{date}%23maakunta_1_{date}/maps"


def nuts3_labels(csv_text: str, country: str = "FI") -> dict[str, str]:
    """Map NUTS 3 code -> Latin label for ``country`` from the GISCO 2024 table."""
    labels: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("CNTR_CODE") != country:
            continue
        nuts_id = (row.get("NUTS_ID") or "").strip()
        if len(nuts_id) != NUTS3_ID_LENGTH:
            continue
        labels[nuts_id] = (row.get("NAME_LATN") or "").strip()
    return labels


def correspondence_maps(payload: Any) -> list[dict[str, Any]]:
    """The list of maps in a Statistics Finland ``/maps`` payload."""
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _item_code(entry: dict[str, Any], key: str) -> str:
    item = entry.get(key)
    if not isinstance(item, dict):
        return ""
    return str(item.get("code") or "").strip()


def _item_level(entry: dict[str, Any], key: str) -> int | None:
    item = entry.get(key)
    if not isinstance(item, dict):
        return None
    level = item.get("level")
    if not isinstance(level, int | float | str):
        return None
    try:
        return int(float(level))  # Statistics Finland serializes ``level`` as 3.00
    except ValueError:
        return None


def _item_name(entry: dict[str, Any], key: str) -> str:
    item = entry.get(key)
    if not isinstance(item, dict):
        return ""
    names = item.get("classificationItemNames")
    if isinstance(names, list):
        for name in names:
            if isinstance(name, dict) and name.get("name"):
                return str(name["name"]).strip()
    return ""


def kunta_to_nuts3(maps: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    """``{kunta_code: nuts3_code}`` plus ``{kunta_code: kunta_name}`` for level 3."""
    codes: dict[str, str] = {}
    names: dict[str, str] = {}
    for entry in maps:
        if _item_level(entry, "targetItem") != NUTS3_LEVEL:
            continue
        kunta = normalize_kunta_code(_item_code(entry, "sourceItem"))
        nuts = _item_code(entry, "targetItem").upper()
        if not kunta or not nuts:
            continue
        codes[kunta] = nuts
        names[kunta] = _item_name(entry, "sourceItem")
    return codes, names


def kunta_to_maakunta(maps: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    """``{kunta_code: maakunta_code}`` plus ``{maakunta_code: maakunta_name}``."""
    codes: dict[str, str] = {}
    names: dict[str, str] = {}
    for entry in maps:
        kunta = normalize_kunta_code(_item_code(entry, "sourceItem"))
        maakunta = normalize_maakunta_code(_item_code(entry, "targetItem"))
        if not kunta or not maakunta:
            continue
        codes[kunta] = maakunta
        names.setdefault(maakunta, _item_name(entry, "targetItem"))
    return codes, names


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(
    path: Path,
    *,
    kunta_rows: dict[str, tuple[str, str]],
    maakunta_rows: dict[str, tuple[str, str]],
    ambiguous: set[str],
    date: str,
) -> None:
    """Write the crosswalk sorted by type then code."""
    kunta_url = kunta_nuts_url(date)
    maakunta_url = kunta_maakunta_url(date)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for code in sorted(kunta_rows):
            nuts_code, nuts_label = kunta_rows[code]
            writer.writerow((KUNTA_KEY, code, nuts_code, nuts_label, kunta_url, SOURCE_VERSION))
        for code in sorted(maakunta_rows):
            nuts_code, nuts_label = maakunta_rows[code]
            writer.writerow(
                (MAAKUNTA_KEY, code, nuts_code, nuts_label, maakunta_url, SOURCE_VERSION)
            )
        for code in sorted(ambiguous):
            writer.writerow((MAAKUNTA_AMBIGUOUS_KEY, code, "", "", maakunta_url, SOURCE_VERSION))


def build_reference(
    root: Path,
    *,
    get: Callable[..., httpx.Response],
    sleep: Callable[[float], None] = time.sleep,
    date: str = CLASSIFICATION_DATE,
) -> dict[str, int]:
    """Read GISCO + both Statistics Finland keys and write the pinned crosswalk.

    ``get``/``sleep`` are injected so tests drive the build without network or
    delay. A NUTS 3 code missing from GISCO NUTS 2024, or a municipality present
    in one classification key but not the other, raises instead of being written.
    """
    root.mkdir(parents=True, exist_ok=True)
    path = root / TMT_REFERENCE_FILE

    labels = nuts3_labels(get(GISCO_NUTS_2024_URL).text)
    if not labels:
        raise RuntimeError(f"no Finnish NUTS 3 codes found in {GISCO_NUTS_2024_URL}")
    sleep(PACING_SECONDS)

    nuts_maps = correspondence_maps(get(kunta_nuts_url(date), params=MAPS_PARAMS).json())
    if not nuts_maps:
        raise RuntimeError(f"Statistics Finland returned no maps for {kunta_nuts_url(date)}")
    sleep(PACING_SECONDS)

    maakunta_maps = correspondence_maps(get(kunta_maakunta_url(date), params=MAPS_PARAMS).json())
    if not maakunta_maps:
        raise RuntimeError(f"Statistics Finland returned no maps for {kunta_maakunta_url(date)}")

    kunta_nuts, kunta_names = kunta_to_nuts3(nuts_maps)
    if not kunta_nuts:
        raise RuntimeError(
            f"no level-{NUTS3_LEVEL} target maps in {kunta_nuts_url(date)} "
            "(the key returns NUTS levels 1-3; level 3 is the one this crosswalk needs)"
        )
    unknown = sorted({code for code in kunta_nuts.values() if code not in labels})
    if unknown:
        raise RuntimeError(
            "Statistics Finland NUTS 3 codes absent from Eurostat GISCO NUTS 2024: "
            + ", ".join(unknown)
        )

    kunta_maakunta, maakunta_names = kunta_to_maakunta(maakunta_maps)
    missing_maakunta = sorted(set(kunta_nuts) - set(kunta_maakunta))
    missing_nuts = sorted(set(kunta_maakunta) - set(kunta_nuts))
    if missing_maakunta or missing_nuts:
        raise RuntimeError(
            "the two Statistics Finland keys disagree about the municipality set: "
            f"{len(missing_maakunta)} without a maakunta ({', '.join(missing_maakunta[:5])}), "
            f"{len(missing_nuts)} without a NUTS 3 ({', '.join(missing_nuts[:5])})"
        )

    kunta_rows = {code: (nuts, labels[nuts]) for code, nuts in kunta_nuts.items()}

    # maakunta -> the distinct NUTS 3 codes its municipalities resolve to
    candidates: dict[str, set[str]] = defaultdict(set)
    for kunta, maakunta in kunta_maakunta.items():
        nuts = kunta_nuts.get(kunta)
        if nuts:
            candidates[maakunta].add(nuts)

    maakunta_rows: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for maakunta, codes in candidates.items():
        if len(codes) > 1:
            ambiguous.add(maakunta)
            continue
        nuts = next(iter(codes))
        maakunta_rows[maakunta] = (nuts, labels[nuts])

    write_csv(
        path,
        kunta_rows=kunta_rows,
        maakunta_rows=maakunta_rows,
        ambiguous=ambiguous,
        date=date,
    )

    mapped_nuts = {code for code, _ in kunta_rows.values()}
    manifest = {
        "source": (
            "stat.fi-kunta-nuts-2024-key + stat.fi-kunta-maakunta-key x eurostat-gisco-nuts-2024"
        ),
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "classification_date": date,
        "source_urls": {
            "nuts_2024": GISCO_NUTS_2024_URL,
            "kunta_nuts": kunta_nuts_url(date),
            "kunta_maakunta": kunta_maakunta_url(date),
        },
        "join": (
            "Statistics Finland classification key kunta -> NUTS (level 3 maps only), "
            "validated against Eurostat GISCO NUTS 2024; maakunta -> NUTS 3 derived by "
            "folding the kunta -> maakunta key and verified to be single-valued"
        ),
        "codeset_source_not_used": {
            "url": "https://tyomarkkinatori.fi/api/codes/v1/kopa/KUNTA/koodit",
            "reason": (
                "the portal's robots.txt disallows /api/ and /*/api/ for all user-agents, "
                "so the source's own KUNTA/MAAKUNTA codesets are off-limits under "
                "SCRAPERS.md golden rule 1; Statistics Finland serves the same relation"
            ),
        },
        "row_counts": {
            TMT_REFERENCE_FILE: len(kunta_rows) + len(maakunta_rows) + len(ambiguous),
            KUNTA_KEY: len(kunta_rows),
            MAAKUNTA_KEY: len(maakunta_rows),
            MAAKUNTA_AMBIGUOUS_KEY: len(ambiguous),
        },
        "kunta_nuts_maps_read": len(nuts_maps),
        "kunta_maakunta_maps_read": len(maakunta_maps),
        "gisco_nuts3_codes": sorted(labels),
        "distinct_nuts3_mapped": sorted(mapped_nuts),
        "nuts3_without_municipality": sorted(set(labels) - mapped_nuts),
        "ambiguous_maakunta_codes": sorted(ambiguous),
        "maakunta_join": {
            code: {
                "name": maakunta_names.get(code, ""),
                "nuts_code": nuts_code,
                "nuts_label": nuts_label,
            }
            for code, (nuts_code, nuts_label) in sorted(maakunta_rows.items())
        },
        "municipalities_read": len(kunta_names),
        "historic_names_included": False,
        "historic_names_reason": (
            "the API sends current KUNTA/MAAKUNTA codes, not names, and Statistics "
            "Finland publishes one key per vintage; a merged municipality's code is "
            "absent from the current key and stays unmapped rather than being guessed"
        ),
        "hashes": {TMT_REFERENCE_FILE: _sha256(path)},
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        TMT_REFERENCE_FILE: len(kunta_rows) + len(maakunta_rows) + len(ambiguous),
        KUNTA_KEY: len(kunta_rows),
        MAAKUNTA_KEY: len(maakunta_rows),
        MAAKUNTA_AMBIGUOUS_KEY: len(ambiguous),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build the Finnish kunta/maakunta -> NUTS 2024 crosswalk "
            "(Statistics Finland classification keys x Eurostat GISCO)"
        )
    )
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    parser.add_argument(
        "--date",
        default=CLASSIFICATION_DATE,
        help=(
            "Statistics Finland classification vintage, e.g. 20260101 "
            f"(default: {CLASSIFICATION_DATE})"
        ),
    )
    args = parser.parse_args()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=120.0,
        follow_redirects=True,
    ) as client:
        counts = build_reference(args.root, get=client.get, date=args.date)

    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"manifest: {args.root / MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
