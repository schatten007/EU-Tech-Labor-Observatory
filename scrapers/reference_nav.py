"""Build the pinned NAV fylke/kommune -> NUTS 2024 crosswalk (opt-in network).

Increment 6 (Norway). The NAV feed exposes region as **names, not codes**
(``workLocations[].county`` = ``"VESTLAND"``, ``workLocations[].municipal`` =
``"BERGEN"``, ``_feed_entry.municipal`` = ``"ØSTRE TOTEN"``), so the crosswalk is
name-keyed and both key types are written.

Three authoritative inputs, all verified live on 2026-08-23:

1. **Eurostat GISCO NUTS 2024** attribute table — the authority for the target
   codes and labels::

       GET https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv

   Norway has **17 NUTS 3 codes** (a 5-character ``NUTS_ID`` is level 3):
   ``NO020`` Innlandet, ``NO060`` Trøndelag, ``NO071`` Nordland, ``NO072`` Troms,
   ``NO073`` Finnmark, ``NO081`` Oslo, ``NO083`` Østfold, ``NO084`` Akershus,
   ``NO085`` Buskerud, ``NO092`` Agder, ``NO093`` Vestfold, ``NO094`` Telemark,
   ``NO0A1`` Rogaland, ``NO0A2`` Vestland, ``NO0A3`` Møre og Romsdal, ``NO0B1``
   Jan Mayen, ``NO0B2`` Svalbard.

2. **SSB Klass 104 — fylker** (open JSON, no key)::

       GET https://data.ssb.no/api/klass/v1/classifications/104/codesAt.json?date=<d>

   16 codes live: the 15 counties plus ``99 Uoppgitt`` ("unspecified"), which has
   no NUTS 3 equivalent and is recorded as unmapped rather than guessed.

3. **SSB Klass 131 — kommuner** (same host): 358 codes live (357 municipalities
   plus ``9999 Uoppgitt``). A kommune code's **first two digits are its fylke
   code** (``4601`` Bergen -> ``46`` Vestland), so kommune -> fylke -> NUTS 3
   resolves without a correspondence table. Verified exhaustively: **all 358
   kommune codes have a prefix that exists in the fylke table (0 orphans)**;
   ``codesAt.json`` returns ``parentCode: null``, so the prefix rule is the join.

The join is by **name**, because that is all the feed gives. SSB writes Sami dual
names with a spaced hyphen (``"Nordland - Nordlånnda"``, ``"Troms - Romsa -
Tromssa"``) while GISCO uses slashes (``"Nordland/Nordlånnda"``,
``"Troms/Romsa/Tromssa"``), and the feed shouts everything in upper case, so both
sides are folded with :func:`scrapers.nav_norway.normalize_region_name` — the very
function the collector uses at lookup time, so the keys cannot drift. **Any
unmatched fylke raises** instead of being dropped silently (Increment 4/5
precedent: both builders achieved 0 unmatched).

Two deliberate decisions, recorded rather than hidden:

- **Historic kommune names are not included.** SSB Klass can serve them, but a
  pre-2020 municipality may have been split across two of today's counties, so
  its NUTS 3 assignment would be a guess. NAV's own docs state an ad "can never
  be active for more than 6 months", so historic names are rare in practice. Feed
  values that are not current kommuner (measured live: ``"?"`` appears 23 times on
  a single page, and strings such as ``"ÅMOT"`` are not current municipalities)
  therefore stay **unmapped and are reported honestly, never forced**.
- **A kommune name occurring in more than one fylke cannot be resolved from a
  name alone** (Norway has repeated names such as *Herøy* and *Bø*). Those keys
  are written with ``source_type = "kommune-ambiguous"`` and no code, so the
  collector reports ``ambiguous`` instead of picking one of two regions.

Unlike Increment 5's 529-request walk, this build is **three requests**, so no
resume state is needed (and none is pretended); ``get``/``sleep`` are still
injected so the tests drive it without network or delay.

Run once per SSB/NUTS change:

    python -m scrapers.reference_nav          # 3 paced requests, a few seconds

Outputs (committed so the offline gate keeps working):

    data/reference/nav_region_nuts_2024.csv
    data/reference/reference_manifest_nav.json
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

from scrapers.nav_norway import (
    FYLKE_KEY,
    KOMMUNE_AMBIGUOUS_KEY,
    KOMMUNE_KEY,
    NAV_REFERENCE_FILE,
    normalize_region_name,
)

#: Eurostat GISCO NUTS 2024 attribute table (CNTR_CODE, NUTS_ID, NAME_LATN, ...).
GISCO_NUTS_2024_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv"
)
KLASS_BASE = "https://data.ssb.no/api/klass/v1/classifications"
#: SSB Klass 104 = "Standard for fylkesinndeling" (counties).
KLASS_FYLKER_URL = f"{KLASS_BASE}/104/codesAt.json"
#: SSB Klass 131 = "Standard for kommuneinndeling" (municipalities).
KLASS_KOMMUNER_URL = f"{KLASS_BASE}/131/codesAt.json"

SOURCE_URLS: dict[str, str] = {
    "nuts_2024": GISCO_NUTS_2024_URL,
    "fylker": f"{KLASS_FYLKER_URL}?date=<date>",
    "kommuner": f"{KLASS_KOMMUNER_URL}?date=<date>",
}

#: Snapshot tag for the pinned file (date the classifications were read).
SOURCE_VERSION = "2026-08-23"

#: Header of every crosswalk CSV, matching data/reference/geography_nuts_2024.csv.
COLUMNS = ("source_type", "source_code", "nuts_code", "nuts_label", "source_url", "source_version")

MANIFEST_FILE = "reference_manifest_nav.json"

USER_AGENT = "EU-Tech-Labour-Observatory/0.1 (robots-and-ToS-compliant, reference build)"

#: A NUTS 3 identifier is five characters (``NO0A2``); level is not a CSV column.
NUTS3_ID_LENGTH = 5
#: SSB's "unspecified" bucket in both classifications; it has no NUTS 3 code.
SSB_UNSPECIFIED = "99"
#: Charter pacing floor: never faster than one request per second per host.
PACING_SECONDS = 1.0


def nuts3_labels(csv_text: str, country: str = "NO") -> dict[str, str]:
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


def klass_codes(payload: Any) -> list[dict[str, str]]:
    """The ``codes`` array of a Klass ``codesAt.json`` payload."""
    codes = payload.get("codes") if isinstance(payload, dict) else None
    if not isinstance(codes, list):
        return []
    return [
        {"code": str(item.get("code") or "").strip(), "name": str(item.get("name") or "").strip()}
        for item in codes
        if isinstance(item, dict) and item.get("code")
    ]


def match_fylker(
    fylker: list[dict[str, str]], labels: dict[str, str]
) -> tuple[dict[str, tuple[str, str, str]], list[str]]:
    """Join SSB fylker onto GISCO NUTS 3 by folded name.

    Returns ``{fylke_code: (nuts_code, nuts_label, ssb_name)}`` plus the list of
    SSB fylker that found no NUTS 3 code. ``99 Uoppgitt`` is expected to be in
    that list and is not an error; anything else is.
    """
    by_key = {normalize_region_name(label): code for code, label in labels.items()}
    matched: dict[str, tuple[str, str, str]] = {}
    unmatched: list[str] = []
    for fylke in fylker:
        nuts_code = by_key.get(normalize_region_name(fylke["name"]))
        if nuts_code is None:
            unmatched.append(f"{fylke['code']}:{fylke['name']}")
            continue
        matched[fylke["code"]] = (nuts_code, labels[nuts_code], fylke["name"])
    return matched, unmatched


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(
    path: Path,
    *,
    fylke_rows: dict[str, tuple[str, str]],
    kommune_rows: dict[str, tuple[str, str]],
    ambiguous: set[str],
) -> None:
    """Write the crosswalk sorted by type then folded key."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for key in sorted(fylke_rows):
            nuts_code, nuts_label = fylke_rows[key]
            writer.writerow(
                (FYLKE_KEY, key, nuts_code, nuts_label, KLASS_FYLKER_URL, SOURCE_VERSION)
            )
        for key in sorted(kommune_rows):
            nuts_code, nuts_label = kommune_rows[key]
            writer.writerow(
                (KOMMUNE_KEY, key, nuts_code, nuts_label, KLASS_KOMMUNER_URL, SOURCE_VERSION)
            )
        for key in sorted(ambiguous):
            writer.writerow(
                (KOMMUNE_AMBIGUOUS_KEY, key, "", "", KLASS_KOMMUNER_URL, SOURCE_VERSION)
            )


def build_reference(
    root: Path,
    *,
    get: Callable[..., httpx.Response],
    sleep: Callable[[float], None] = time.sleep,
    date: str | None = None,
) -> dict[str, int]:
    """Read GISCO + both SSB classifications and write the pinned crosswalk.

    ``get``/``sleep`` are injected so tests drive the build without network or
    delay. An SSB fylke other than ``99 Uoppgitt`` that finds no NUTS 3 code
    raises instead of being written, and so does a kommune whose two-digit prefix
    is not a known fylke.
    """
    root.mkdir(parents=True, exist_ok=True)
    path = root / NAV_REFERENCE_FILE
    as_of = date or datetime.now(UTC).date().isoformat()

    labels = nuts3_labels(get(GISCO_NUTS_2024_URL).text)
    if not labels:
        raise RuntimeError(f"no Norwegian NUTS 3 codes found in {GISCO_NUTS_2024_URL}")
    sleep(PACING_SECONDS)

    fylker = klass_codes(get(KLASS_FYLKER_URL, params={"date": as_of}).json())
    if not fylker:
        raise RuntimeError(f"SSB Klass 104 returned no codes for {as_of}")
    sleep(PACING_SECONDS)

    kommuner = klass_codes(get(KLASS_KOMMUNER_URL, params={"date": as_of}).json())
    if not kommuner:
        raise RuntimeError(f"SSB Klass 131 returned no codes for {as_of}")

    matched, unmatched = match_fylker(fylker, labels)
    unexpected = [entry for entry in unmatched if not entry.startswith(f"{SSB_UNSPECIFIED}:")]
    if unexpected:
        raise RuntimeError(
            "SSB fylker with no Eurostat GISCO NUTS 2024 match (name join failed): "
            + ", ".join(unexpected)
        )

    fylke_rows: dict[str, tuple[str, str]] = {}
    for nuts_code, nuts_label, ssb_name in matched.values():
        fylke_rows[normalize_region_name(ssb_name)] = (nuts_code, nuts_label)

    # kommune folded name -> the distinct NUTS 3 codes its fylke prefixes imply
    candidates: dict[str, dict[str, str]] = defaultdict(dict)
    orphan_prefixes: list[str] = []
    unspecified_kommuner: list[str] = []
    for kommune in kommuner:
        prefix = kommune["code"][:2]
        if prefix == SSB_UNSPECIFIED:
            unspecified_kommuner.append(f"{kommune['code']}:{kommune['name']}")
            continue
        hit = matched.get(prefix)
        if hit is None:
            orphan_prefixes.append(f"{kommune['code']}:{kommune['name']}")
            continue
        candidates[normalize_region_name(kommune["name"])][hit[0]] = hit[1]
    if orphan_prefixes:
        raise RuntimeError(
            "SSB kommuner whose two-digit fylke prefix is not a mapped fylke: "
            + ", ".join(orphan_prefixes)
        )

    kommune_rows: dict[str, tuple[str, str]] = {}
    ambiguous: set[str] = set()
    for key, codes in candidates.items():
        if not key:
            continue
        if len(codes) > 1:
            ambiguous.add(key)
            continue
        code = next(iter(codes))
        kommune_rows[key] = (code, codes[code])

    write_csv(path, fylke_rows=fylke_rows, kommune_rows=kommune_rows, ambiguous=ambiguous)

    mapped_nuts = {code for code, _ in fylke_rows.values()} | {
        code for code, _ in kommune_rows.values()
    }
    manifest = {
        "source": "ssb-klass-104-fylker + ssb-klass-131-kommuner x eurostat-gisco-nuts-2024",
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "classification_date": as_of,
        "source_urls": SOURCE_URLS,
        "join": (
            "SSB fylke/kommune name -> folded name -> GISCO NUTS 2024 level 3 (NO); "
            "kommune -> fylke via the code's first two digits"
        ),
        "row_counts": {
            NAV_REFERENCE_FILE: len(fylke_rows) + len(kommune_rows) + len(ambiguous),
            FYLKE_KEY: len(fylke_rows),
            KOMMUNE_KEY: len(kommune_rows),
            KOMMUNE_AMBIGUOUS_KEY: len(ambiguous),
        },
        "ssb_fylker_read": len(fylker),
        "ssb_kommuner_read": len(kommuner),
        "gisco_nuts3_codes": sorted(labels),
        "distinct_nuts3_mapped": sorted(mapped_nuts),
        "nuts3_without_ssb_fylke": sorted(set(labels) - mapped_nuts),
        "unmatched_fylker": unmatched,
        "unspecified_kommuner": unspecified_kommuner,
        "ambiguous_kommune_names": sorted(ambiguous),
        "fylke_join": {
            name: {"nuts_code": code, "nuts_label": label}
            for code, label, name in sorted(matched.values(), key=lambda item: item[0])
        },
        "historic_names_included": False,
        "historic_names_reason": (
            "A pre-2020 kommune may have been split across two of today's counties, so its "
            "NUTS 3 assignment would be a guess; NAV ads are never active longer than ~6 "
            "months, so historic names are rare. Unknown feed names stay unmapped."
        ),
        "hashes": {NAV_REFERENCE_FILE: _sha256(path)},
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        NAV_REFERENCE_FILE: len(fylke_rows) + len(kommune_rows) + len(ambiguous),
        FYLKE_KEY: len(fylke_rows),
        KOMMUNE_KEY: len(kommune_rows),
        KOMMUNE_AMBIGUOUS_KEY: len(ambiguous),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the NAV fylke/kommune -> NUTS 2024 crosswalk (SSB Klass x GISCO)"
    )
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    parser.add_argument(
        "--date", default=None, help="classification date for SSB Klass (default: today, UTC)"
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
