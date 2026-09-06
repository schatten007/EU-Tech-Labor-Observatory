"""Build pinned MPSV codelist -> NUTS 2024 crosswalk CSVs (opt-in network).

Increment 2 (Czechia): the ``kraje`` / ``okresy`` / ``obce`` codelists published
at data.mpsv.cz carry the region mapping the MPSVCollector needs. The kraje
codelist carries ``kodNuts3`` directly (CZ010-CZ080, unchanged in NUTS 2024);
okresy link to a kraj and obce link to an okres, so both resolve to a NUTS 3
code through the same chain.

Run once per schema/codelist change:

    python -m scrapers.reference_mpsv            # writes data/reference/mpsv_*.csv

Outputs (committed, keep the offline gate working):

    data/reference/mpsv_kraje_nuts_2024.csv   14 rows
    data/reference/mpsv_okresy_kraj_2024.csv  78 rows
    data/reference/mpsv_obce_kraj_2024.csv   ~6.2k rows
    data/reference/reference_manifest_mpsv.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

KRAJE_URL = "https://data.mpsv.cz/od/soubory/ciselniky/kraje.json"
OKRESY_URL = "https://data.mpsv.cz/od/soubory/ciselniky/okresy.json"
OBCE_URL = "https://data.mpsv.cz/od/soubory/ciselniky/obce.json"

SOURCE_URLS: dict[str, str] = {"kraje": KRAJE_URL, "okresy": OKRESY_URL, "obce": OBCE_URL}

#: Snapshot tag for the pinned files (date the codelists were fetched).
SOURCE_VERSION = "2026-08-21"

#: Header of every crosswalk CSV, matching data/reference/geography_nuts_2024.csv.
COLUMNS = ("source_type", "source_code", "nuts_code", "nuts_label", "source_url", "source_version")

USER_AGENT = "EU-Tech-Labour-Observatory/0.1 (robots-and-ToS-compliant, reference build)"


def _nazev(item: dict[str, Any]) -> str:
    nazev = item.get("nazev")
    if isinstance(nazev, dict):
        return nazev.get("cs") or ""
    return ""


def _write_csv(path: Path, rows: list[tuple[str, str, str, str, str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_reference(root: Path, *, get: Callable[[str], httpx.Response]) -> dict[str, int]:
    """Fetch the three codelists and write the pinned crosswalk CSVs.

    ``get`` is injected so tests can mock the network. Returns the row count
    written per file (''kraje'', ''okresy'', ''obce'').
    """
    root.mkdir(parents=True, exist_ok=True)
    kraje = get(KRAJE_URL).json()["polozky"]
    okresy = get(OKRESY_URL).json()["polozky"]
    obce = get(OBCE_URL).json()["polozky"]

    kraj_rows: list[tuple[str, str, str, str, str, str]] = []
    for k in kraje:
        kraj_rows.append(("kraj", k["id"], k["kodNuts3"], _nazev(k), KRAJE_URL, SOURCE_VERSION))

    kraj_map = {k["id"]: (k["kodNuts3"], _nazev(k)) for k in kraje}

    okres_rows: list[tuple[str, str, str, str, str, str]] = []
    skipped_okresy = 0
    for o in okresy:
        resolved = kraj_map.get(o.get("kraj") or "")
        if resolved is None:
            skipped_okresy += 1
            continue
        okres_rows.append(("okres", o["id"], resolved[0], resolved[1], OKRESY_URL, SOURCE_VERSION))

    okres_map = {o["id"]: o.get("kraj") for o in okresy}

    obec_rows: list[tuple[str, str, str, str, str, str]] = []
    skipped_obce = 0
    for b in obce:
        kraj_id = okres_map.get(b.get("okres") or "")
        resolved = kraj_map.get(kraj_id or "")
        if resolved is None:
            skipped_obce += 1
            continue
        obec_rows.append(("obec", b["id"], resolved[0], resolved[1], OBCE_URL, SOURCE_VERSION))

    files = {
        "mpsv_kraje_nuts_2024.csv": kraj_rows,
        "mpsv_okresy_kraj_2024.csv": okres_rows,
        "mpsv_obce_kraj_2024.csv": obec_rows,
    }
    row_counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for name, rows in files.items():
        _write_csv(root / name, rows)
        row_counts[name] = len(rows)
        hashes[name] = _sha256(root / name)

    manifest = {
        "source": "mpsv-codelists",
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_urls": SOURCE_URLS,
        "row_counts": row_counts,
        "skipped_unresolvable": {"okresy": skipped_okresy, "obce": skipped_obce},
        "hashes": hashes,
    }
    (root / "reference_manifest_mpsv.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return row_counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the MPSV codelist -> NUTS 2024 crosswalk")
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    args = parser.parse_args()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=120.0, follow_redirects=True
    ) as client:
        counts = build_reference(args.root, get=client.get)

    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"manifest: {args.root / 'reference_manifest_mpsv.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
