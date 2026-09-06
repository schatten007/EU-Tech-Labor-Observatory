"""Build the pinned VDAB postcode -> NUTS 2024 crosswalk (opt-in network).

Increment 5 (Belgium — Flanders). VDAB's public landing pages expose no NUTS
code: the region signal is the landing-page slug's postcode
(``/vindeenjob/jobs/9000-gent``). Flanders' authoritative address register
returns NUTS 3 for a postcode **directly**, so a postcode -> NUTS 3 crosswalk
fully resolves the region dimension.

Two authoritative sources are used:

1. **Basisregisters Vlaanderen** (the Flemish government's address register,
   open JSON-LD, no robots.txt on the API host ⇒ nothing disallowed):

       GET https://api.basisregisters.vlaanderen.be/v2/postinfo?limit=500
           -> {"postInfoObjecten": [{"identificator": {"objectId": "9000"}, ...}],
               "volgende": "...?offset=500&limit=500"}          (list; no nuts3)

       GET https://api.basisregisters.vlaanderen.be/v2/postinfo/9000
           -> {"gemeente": {"objectId": "44021", ... "Gent"}, "nuts3": "BE234"}

   ``nuts3`` appears only on the **detail** payload, so the builder walks every
   enumerated postcode once (~1.1k paced requests, ~20 minutes at the charter's
   1 s floor). Postcodes the register no longer serves answer
   ``410 Verwijderde postcode`` (verified live: Brussels ``1000``) or ``404``;
   they are counted and skipped, never guessed.

2. **Eurostat GISCO NUTS 2024** attribute table (``NUTS_AT_2024.csv``) — the
   validation set. Belgium has 44 NUTS 3 codes, 22 of them Flemish
   (``BE21x``–``BE25x``); a 5-character ``NUTS_ID`` is level 3. Every ``nuts3``
   the register returns is checked against that set and any unmatched code is
   **reported loudly**, never silently dropped (Increment 4 precedent).

The walk is **restartable**: rows are flushed to the CSV every
``FLUSH_EVERY`` postcodes and an existing CSV is loaded on start, so an
interrupted build resumes where it stopped. Use ``--fresh`` to ignore it.

Run once per register/NUTS change:

    python -m scrapers.reference_vdab            # ~20 min, paced at 1 s

Outputs (committed so the offline gate keeps working):

    data/reference/vdab_postcode_nuts_2024.csv
    data/reference/reference_manifest_vdab.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scrapers.vdab import VDAB_REFERENCE_FILE

#: Eurostat GISCO NUTS 2024 attribute table (CNTR_CODE, NUTS_ID, NAME_LATN, ...).
GISCO_NUTS_2024_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv"
)
BASISREGISTERS_BASE = "https://api.basisregisters.vlaanderen.be/v2"
POSTINFO_LIST_URL = f"{BASISREGISTERS_BASE}/postinfo"
POSTINFO_DETAIL_URL = f"{BASISREGISTERS_BASE}/postinfo/{{postcode}}"

SOURCE_URLS: dict[str, str] = {
    "postinfo_list": f"{POSTINFO_LIST_URL}?limit=500",
    "postinfo_detail": POSTINFO_DETAIL_URL,
    "nuts_2024": GISCO_NUTS_2024_URL,
}

#: Snapshot tag for the pinned file (date the register was walked).
SOURCE_VERSION = "2026-08-22"

#: Header of every crosswalk CSV, matching data/reference/geography_nuts_2024.csv.
COLUMNS = ("source_type", "source_code", "nuts_code", "nuts_label", "source_url", "source_version")

MANIFEST_FILE = "reference_manifest_vdab.json"

USER_AGENT = "EU-Tech-Labour-Observatory/0.1 (robots-and-ToS-compliant, reference build)"

#: A NUTS 3 identifier is five characters (``BE234``); level is not a CSV column.
NUTS3_ID_LENGTH = 5
#: Flemish NUTS 3 codes are BE21x..BE25x (22 of Belgium's 44).
FLEMISH_NUTS3 = re.compile(r"^BE2[1-5]\d$")

#: Charter pacing floor: never faster than one request per second per host.
PACING_SECONDS = 1.0
#: Flush the CSV every N postcodes so an interrupted walk is restartable.
FLUSH_EVERY = 50
#: Page size of the postinfo list endpoint.
LIST_LIMIT = 500
#: Postcodes are four digits; the register also serves non-geographic ids.
POSTCODE = re.compile(r"^\d{4}$")


def nuts3_labels(csv_text: str) -> dict[str, str]:
    """Map Belgian NUTS 3 code -> Latin label from the GISCO NUTS 2024 table."""
    labels: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("CNTR_CODE") != "BE":
            continue
        nuts_id = (row.get("NUTS_ID") or "").strip()
        if len(nuts_id) != NUTS3_ID_LENGTH:
            continue
        labels[nuts_id] = (row.get("NAME_LATN") or "").strip()
    return labels


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_existing(path: Path) -> dict[str, tuple[str, str]]:
    """Postcodes already written by an earlier run (the resume state)."""
    if not path.exists():
        return {}
    rows: dict[str, tuple[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["source_code"].strip()] = (row["nuts_code"], row["nuts_label"])
    return rows


def write_csv(path: Path, mapping: dict[str, tuple[str, str]]) -> None:
    """Write the crosswalk sorted by postcode (atomic per flush)."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for postcode in sorted(mapping):
            nuts_code, nuts_label = mapping[postcode]
            writer.writerow(
                (
                    "postcode",
                    postcode,
                    nuts_code,
                    nuts_label,
                    POSTINFO_DETAIL_URL.format(postcode=postcode),
                    SOURCE_VERSION,
                )
            )


def enumerate_postcodes(
    get: Callable[..., httpx.Response], *, sleep: Callable[[float], None]
) -> list[str]:
    """Every postcode the register lists, followed page by page via ``volgende``."""
    postcodes: list[str] = []
    seen: set[str] = set()
    url: str | None = f"{POSTINFO_LIST_URL}?limit={LIST_LIMIT}"
    while url:
        response = get(url)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("postInfoObjecten") or []
        for item in items:
            code = str((item.get("identificator") or {}).get("objectId") or "").strip()
            if POSTCODE.match(code) and code not in seen:
                seen.add(code)
                postcodes.append(code)
        next_url = payload.get("volgende")
        url = str(next_url) if next_url else None
        if url:
            sleep(PACING_SECONDS)
    return sorted(postcodes)


def build_reference(
    root: Path,
    *,
    get: Callable[..., httpx.Response],
    sleep: Callable[[float], None] = time.sleep,
    resume: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    """Walk the register, validate every ``nuts3`` against GISCO and write the CSV.

    ``get`` / ``sleep`` are injected so tests can drive the walk without network
    or delay. Returns the counts recorded in the manifest. A ``nuts3`` value that
    is not a Belgian NUTS 2024 level-3 code raises instead of being written.
    """
    root.mkdir(parents=True, exist_ok=True)
    path = root / VDAB_REFERENCE_FILE

    labels = nuts3_labels(get(GISCO_NUTS_2024_URL).text)
    if not labels:
        raise RuntimeError(f"no Belgian NUTS 3 codes found in {GISCO_NUTS_2024_URL}")
    sleep(PACING_SECONDS)

    mapping = load_existing(path) if resume else {}
    postcodes = enumerate_postcodes(get, sleep=sleep)
    if limit is not None:
        postcodes = postcodes[:limit]

    unknown_nuts: list[str] = []
    non_flemish: list[str] = []
    skipped: dict[str, int] = {}
    resolved_now = 0
    for index, postcode in enumerate(postcodes, start=1):
        if postcode in mapping:
            continue
        sleep(PACING_SECONDS)
        response = get(POSTINFO_DETAIL_URL.format(postcode=postcode))
        if response.status_code in (404, 410):
            # 410 "Verwijderde postcode" (e.g. Brussels 1000) / 404 unknown.
            skipped[str(response.status_code)] = skipped.get(str(response.status_code), 0) + 1
            continue
        response.raise_for_status()
        nuts3 = str(response.json().get("nuts3") or "").strip()
        if not nuts3:
            skipped["no_nuts3"] = skipped.get("no_nuts3", 0) + 1
            continue
        if nuts3 not in labels:
            unknown_nuts.append(f"{postcode}:{nuts3}")
            continue
        if not FLEMISH_NUTS3.match(nuts3):
            non_flemish.append(f"{postcode}:{nuts3}")
        mapping[postcode] = (nuts3, labels[nuts3])
        resolved_now += 1
        if index % FLUSH_EVERY == 0:
            write_csv(path, mapping)

    if unknown_nuts:
        raise RuntimeError(
            "Basisregisters returned nuts3 values absent from Eurostat GISCO NUTS 2024: "
            + ", ".join(unknown_nuts)
        )

    write_csv(path, mapping)
    flemish = sorted({code for code, _ in mapping.values() if FLEMISH_NUTS3.match(code)})
    manifest = {
        "source": "basisregisters-vlaanderen-postinfo x eurostat-gisco-nuts-2024",
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_urls": SOURCE_URLS,
        "join": "postinfo/{postcode}.nuts3 -> GISCO NUTS 2024 level 3 (BE), validated",
        "row_counts": {VDAB_REFERENCE_FILE: len(mapping)},
        "postcodes_enumerated": len(postcodes),
        "postcodes_resolved_this_run": resolved_now,
        "postcodes_skipped": skipped,
        "distinct_nuts3": len({code for code, _ in mapping.values()}),
        "flemish_nuts3": flemish,
        "non_flemish_nuts3": sorted(set(non_flemish)),
        "unmatched_nuts3": unknown_nuts,
        "hashes": {VDAB_REFERENCE_FILE: _sha256(path)},
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {VDAB_REFERENCE_FILE: len(mapping)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the VDAB postcode -> NUTS 2024 crosswalk (Basisregisters Vlaanderen)"
    )
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    parser.add_argument(
        "--fresh", action="store_true", help="ignore an existing CSV instead of resuming it"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="stop after N enumerated postcodes (smoke test)"
    )
    args = parser.parse_args()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=120.0,
        follow_redirects=True,
    ) as client:
        counts = build_reference(args.root, get=client.get, resume=not args.fresh, limit=args.limit)

    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"manifest: {args.root / MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
