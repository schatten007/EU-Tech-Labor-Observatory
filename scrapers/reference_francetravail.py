"""Build the pinned France Travail département -> NUTS 2024 crosswalk (opt-in network).

Increment 4 (France). The API Offres d'emploi exposes no NUTS codes: a posting's
location is ``lieuTravail`` (``commune`` INSEE code, ``codePostal``, and a
``libelle`` prefixed with the département code). French NUTS 3 regions *are* the
101 départements, so a département -> NUTS 3 crosswalk fully resolves the region
dimension.

Two authoritative sources are joined on the département name:

1. France Travail ``referentiel/departements`` (101 rows: ``code``, ``libelle``,
   ``region``) — the source-side codes the collector actually sees.
2. Eurostat GISCO NUTS 2024 attribute table (``NUTS_AT_2024.csv``) — the
   authoritative NUTS 2024 codes and Latin names; FR level 3 has exactly 101
   rows (level derived from the 5-character ``NUTS_ID``).

The join was verified live on 2026-08-22: **101/101 départements matched, no
leftover NUTS 3 code, no manual override needed** (names are compared
accent-, case- and punctuation-insensitively). A mismatch is reported instead of
silently dropped.

Run once per NUTS/codelist change:

    python -m scrapers.reference_francetravail     # writes data/reference/francetravail_*.csv

Outputs (committed so the offline gate keeps working):

    data/reference/francetravail_departements_nuts_2024.csv   101 rows
    data/reference/reference_manifest_francetravail.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import unicodedata
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

from scrapers.france_travail import (
    FT_API_BASE,
    FT_REFERENCE_FILE,
    FT_SCOPE,
    FT_TOKEN_REALM,
    FT_TOKEN_URL,
    FT_USER_AGENT,
    france_travail_credentials,
)

#: Eurostat GISCO NUTS 2024 attribute table (CNTR_CODE, NUTS_ID, NAME_LATN, ...).
GISCO_NUTS_2024_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv"
)
DEPARTEMENTS_URL = f"{FT_API_BASE}/referentiel/departements"

SOURCE_URLS: dict[str, str] = {
    "departements": DEPARTEMENTS_URL,
    "nuts_2024": GISCO_NUTS_2024_URL,
}

#: Snapshot tag for the pinned file (date the codelists were fetched).
SOURCE_VERSION = "2026-08-22"

#: Header of every crosswalk CSV, matching data/reference/geography_nuts_2024.csv.
COLUMNS = ("source_type", "source_code", "nuts_code", "nuts_label", "source_url", "source_version")

MANIFEST_FILE = "reference_manifest_francetravail.json"

#: A NUTS 3 identifier is five characters (``FR101``); level is not a CSV column.
NUTS3_ID_LENGTH = 5


def normalize_name(text: str) -> str:
    """Accent-, case- and punctuation-insensitive form used for the name join."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    alnum = "".join(char if char.isalnum() else " " for char in stripped.lower())
    return " ".join(alnum.split())


def fetch_access_token(post: Callable[..., httpx.Response]) -> str:
    """Mint an OAuth2 client-credentials token (``post`` injected for tests)."""
    client_id, client_secret = france_travail_credentials()
    response = post(
        FT_TOKEN_URL,
        params={"realm": FT_TOKEN_REALM},
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": FT_SCOPE,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if response.status_code != 200:
        raise RuntimeError(f"France Travail token endpoint returned {response.status_code}")
    token = response.json()["access_token"]
    if not isinstance(token, str) or not token:
        raise RuntimeError("France Travail token endpoint returned no access_token")
    return token


def nuts3_by_name(csv_text: str) -> dict[str, tuple[str, str]]:
    """Map normalized FR NUTS 3 name -> (NUTS code, label) from the GISCO table."""
    mapping: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("CNTR_CODE") != "FR":
            continue
        nuts_id = (row.get("NUTS_ID") or "").strip()
        if len(nuts_id) != NUTS3_ID_LENGTH:
            continue
        label = (row.get("NAME_LATN") or "").strip()
        mapping[normalize_name(label)] = (nuts_id, label)
    return mapping


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_reference(
    root: Path,
    *,
    get: Callable[..., httpx.Response],
    post: Callable[..., httpx.Response],
) -> dict[str, int]:
    """Fetch both codelists, join them and write the pinned crosswalk CSV.

    ``get`` / ``post`` are injected so tests can mock the network. Returns the
    row count written and the number of unmatched départements (always 0 for a
    clean build; a non-empty mismatch list raises instead).
    """
    root.mkdir(parents=True, exist_ok=True)
    token = fetch_access_token(post)

    by_name = nuts3_by_name(get(GISCO_NUTS_2024_URL).text)
    departements = get(
        DEPARTEMENTS_URL,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    ).json()

    rows: list[tuple[str, str, str, str, str, str]] = []
    unmatched: list[str] = []
    for item in departements:
        code = str(item["code"])
        hit = by_name.get(normalize_name(str(item["libelle"])))
        if hit is None:
            unmatched.append(f"{code}:{item['libelle']}")
            continue
        rows.append(("departement", code, hit[0], hit[1], DEPARTEMENTS_URL, SOURCE_VERSION))
    if unmatched:
        raise RuntimeError(
            "France Travail départements without a NUTS 2024 match: " + ", ".join(unmatched)
        )

    rows.sort(key=lambda row: row[1])
    path = root / FT_REFERENCE_FILE
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)

    manifest = {
        "source": "francetravail-referentiel-departements x eurostat-gisco-nuts-2024",
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_urls": SOURCE_URLS,
        "join": "departement libelle -> NUTS 3 NAME_LATN (accent/case/punctuation-insensitive)",
        "row_counts": {FT_REFERENCE_FILE: len(rows)},
        "unmatched_departements": unmatched,
        "hashes": {FT_REFERENCE_FILE: _sha256(path)},
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {FT_REFERENCE_FILE: len(rows)}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the France Travail département -> NUTS 2024 crosswalk"
    )
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    args = parser.parse_args()

    with httpx.Client(
        headers={"User-Agent": FT_USER_AGENT}, timeout=120.0, follow_redirects=True
    ) as client:
        counts = build_reference(args.root, get=client.get, post=client.post)

    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"manifest: {args.root / MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
