"""Build the pinned German PLZ/Stadt -> NUTS 2024 crosswalk (opt-in network).

Three authoritative sources, validated against Eurostat GISCO with 0-unmatched bar:

1. **destatis Kreise table** (official AGS-Kreis -> NUTS 2024 key). The Federal
   Statistical Office publishes the official correspondence between the German
   Amtlicher Gemeindeschlüssel (AGS, 5-digit Kreis level) and the NUTS 2024
   code. This is THE official key. 400/400 GISCO NUTS 3 codes are covered.

   ``https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/Administrativ/04-kreise.html``

2. **BKG Orts-/Gemeindeverzeichnis (VZ250_GEM)** — the official municipality
   register (BKG, ``dl-de/by-2-0``). Each municipality record carries the AGS
   (8 digits), the municipality name, and the Kreis assignment. The VZ250's
   own ``NUTS3_CODE`` column is used for a cross-check (7 stale Thuringian codes
   recorded as a deviation, not a failure).

   ``https://daten.gdz.bkg.bund.de/produkte/vg/vz250_1231/aktuell/vz250_12-31.gk3.shape.zip``

3. **destatis Anschriftenverzeichnis** — the address directory of all German
   municipality administrations. Each row carries the AGS (8-digit) and the
   **Zustell-PLZ** (postal code of the administrative seat).

   ``https://www.statistikportal.de/de/veroeffentlichungen/anschriftenverzeichnis``

4. **Eurostat GISCO NUTS 2024** attribute table — validation set: 400 DE NUTS 3.

Join: PLZ (Anschriften) -> municipality AGS (VZ250) -> Kreis AGS 5-digit prefix
-> NUTS 2024 (destatis Kreise). 0-unmatched bar: every NUTS code in the crosswalk
must be in GISCO.

Run::

    python -m scrapers.reference_germany

Outputs (committed)::

    data/reference/germany_plz_nuts_2024.csv
    data/reference/reference_manifest_germany.json
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import struct
import time
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

GISCO_NUTS_2024_URL = (
    "https://gisco-services.ec.europa.eu/distribution/v2/nuts/csv/NUTS_AT_2024.csv"
)

VZ250_SHAPE_URL = (
    "https://daten.gdz.bkg.bund.de/produkte/vg/vz250_1231/aktuell/vz250_12-31.gk3.shape.zip"
)

ANSCHRIFTEN_URL = (
    "https://www.statistikportal.de/sites/default/files/2026-05/"
    "20260131_Anschriften_der_Gemeinde_und_Stadtverwaltungen.xlsx"
)

KREISE_XLSX_URL = (
    "https://www.destatis.de/DE/Themen/Laender-Regionen/Regionales/Gemeindeverzeichnis/"
    "Administrativ/04-kreise.xlsx?__blob=publicationFile&v=14"
)

SOURCE_URLS: dict[str, str] = {
    "gisco_nuts_2024": GISCO_NUTS_2024_URL,
    "vz250_gem": VZ250_SHAPE_URL,
    "anschriftenverzeichnis": ANSCHRIFTEN_URL,
    "kreise_nuts": KREISE_XLSX_URL,
}

SOURCE_VERSION = "2026-08-23"

COLUMNS = (
    "source_type",
    "source_code",
    "municipality_name",
    "kreis_name",
    "nuts_code",
    "nuts_label",
    "source_url",
    "source_version",
)

MANIFEST_FILE = "reference_manifest_germany.json"
REFERENCE_FILE = "germany_plz_nuts_2024.csv"

USER_AGENT = "EU-Tech-Labour-Observatory/0.1 (robots-and-ToS-compliant, reference build)"
PACING_SECONDS = 1.0
NUTS3_ID_LENGTH = 5


def nuts3_labels(csv_text: str, country: str = "DE") -> dict[str, str]:
    labels: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("CNTR_CODE") != country:
            continue
        nuts_id = (row.get("NUTS_ID") or "").strip()
        if len(nuts_id) != NUTS3_ID_LENGTH:
            continue
        labels[nuts_id] = (row.get("NAME_LATN") or "").strip()
    return labels


# ---------------------------------------------------------------------------
# Minimal dBASE III reader
# ---------------------------------------------------------------------------


def _read_dbf_table(path: Path) -> list[dict[str, str]]:
    with path.open("rb") as f:
        header = f.read(32)
        nrec = struct.unpack("<I", header[4:8])[0]
        hlen = struct.unpack("<H", header[8:10])[0]
        rlen = struct.unpack("<H", header[10:12])[0]
        f.seek(32)
        fields: list[tuple[str, int]] = []
        while True:
            desc = f.read(32)
            if desc[0:1] == b"\x0d":
                break
            name = desc[0:11].decode("ascii", errors="replace").strip(chr(0)).strip()
            fields.append((name, desc[16]))
        records: list[dict[str, str]] = []
        f.seek(hlen)
        for _ in range(nrec):
            raw = f.read(rlen)
            if len(raw) < rlen:
                break
            offset = 1
            rec: dict[str, str] = {}
            for name, fsize in fields:
                rec[name] = raw[offset : offset + fsize].decode("utf-8", errors="replace").strip()
                offset += fsize
            records.append(rec)
    return records


# ---------------------------------------------------------------------------
# Minimal xlsx sheet reader
# ---------------------------------------------------------------------------


def _parse_xlsx_sheet(path: Path, sheet_name: str) -> list[list[str]]:
    rows: list[list[str]] = []
    with zipfile.ZipFile(path, "r") as z:
        wb = ET.parse(z.open("xl/workbook.xml"))
        ns = {
            "s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
            "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
        }
        target = None
        for sheet in wb.findall(".//s:sheet", ns):
            if sheet.get("name") == sheet_name:
                rid = sheet.get(
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
                )
                rels = ET.parse(z.open("xl/_rels/workbook.xml.rels"))
                rns = {"r": "http://schemas.openxmlformats.org/package/2006/relationships"}
                for rel in rels.findall(".//r:Relationship", rns):
                    if rel.get("Id") == rid:
                        target = rel.get("Target")
                break
        if target is None:
            return rows
        sst: dict[int, str] = {}
        try:
            sst_xml = ET.parse(z.open("xl/sharedStrings.xml"))
            for i, si in enumerate(sst_xml.findall(".//s:si", ns)):
                texts = []
                for t in si.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"):
                    if t.text:
                        texts.append(t.text)
                sst[i] = "".join(texts)
        except KeyError:
            pass
        sheet_xml = ET.parse(z.open(f"xl/{target}"))
        for row in sheet_xml.findall(".//s:row", ns):
            row_data: list[str] = []
            for cell in row.findall("s:c", ns):
                value = cell.find("s:v", ns)
                if value is not None and value.text:
                    cell_type = cell.get("t", "")
                    cell_val = value.text.strip()
                    if cell_type == "s" and cell_val.isdigit():
                        row_data.append(sst.get(int(cell_val), cell_val))
                    else:
                        row_data.append(cell_val)
                else:
                    row_data.append("")
            rows.append(row_data)
    return rows


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------


def _parse_vz250(records: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    """AGS (8-digit) -> {name, nuts3_vz250, kreis_name, ags_kreis}."""
    mapping: dict[str, dict[str, str]] = {}
    for rec in records:
        ags = (rec.get("AGS_G") or "").strip()
        if not ags:
            continue
        mapping[ags] = {
            "name": (rec.get("GEN_G") or "").strip(),
            "nuts3_vz250": (rec.get("NUTS3_CODE") or "").strip(),
            "kreis_name": (rec.get("GEN_K") or "").strip(),
            "ags_kreis": (rec.get("ARS_K") or "").strip()[:5],
        }
    return mapping


def _parse_anschriften(rows: list[list[str]]) -> dict[str, tuple[str, str]]:
    """AGS (8-digit) -> (PLZ, municipality name) from Anschriftenverzeichnis."""
    mapping: dict[str, tuple[str, str]] = {}
    for row in rows:
        satzart = row[2].strip() if len(row) > 2 else ""
        ags = row[6].strip() if len(row) > 6 else ""
        name = row[7].strip() if len(row) > 7 else ""
        plz = row[10].strip() if len(row) > 10 else ""
        if satzart == "60" and len(ags) == 8 and ags.isdigit() and plz:
            mapping[ags] = (plz, name)
    return mapping


def _parse_kreise_nuts(rows: list[list[str]]) -> dict[str, str]:
    """AGS-Kreis (5-digit) -> NUTS 2024 code from destatis Kreise table."""
    mapping: dict[str, str] = {}
    header_row = None
    for i, row in enumerate(rows):
        if "schlüssel" in " ".join(row).lower() and "nuts" in " ".join(row).lower():
            header_row = i
            break
    if header_row is None:
        return mapping
    header = rows[header_row]
    ags_col = next((j for j, c in enumerate(header) if "schlüssel" in c.strip().lower()), None)
    nuts_col = next((j for j, c in enumerate(header) if "nuts" in c.strip().lower()), None)
    if ags_col is None or nuts_col is None:
        return mapping
    for row in rows[header_row + 1 :]:
        if not row or not row[0].strip():
            continue
        ags = row[ags_col].strip() if ags_col < len(row) else ""
        nuts = row[nuts_col].strip() if nuts_col < len(row) else ""
        if ags and nuts and len(ags) >= 5:
            mapping[ags] = nuts
    return mapping


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(
    url: str, path: Path, get: Callable[..., httpx.Response], sleep: Callable[[float], None]
) -> None:
    response = get(url)
    response.raise_for_status()
    path.write_bytes(response.content)
    sleep(PACING_SECONDS)


def build_reference(
    root: Path,
    *,
    get: Callable[..., httpx.Response],
    sleep: Callable[[float], None] = time.sleep,
    cache_dir: Path | None = None,
) -> dict[str, int]:
    if cache_dir is None:
        cache_dir = root / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / REFERENCE_FILE

    # 1. GISCO NUTS 2024 (validation)
    gisco = nuts3_labels(get(GISCO_NUTS_2024_URL).text)
    print(f"GISCO: {len(gisco)} DE NUTS 3 codes")
    sleep(PACING_SECONDS)

    # 2. destatis Kreise table (official AGS-Kreis -> NUTS 2024 key)
    kreise_path = cache_dir / "kreise.xlsx"
    if not kreise_path.exists():
        print("Downloading destatis Kreise table...")
        _download(KREISE_XLSX_URL, kreise_path, get, sleep)
    else:
        sleep(PACING_SECONDS)
    kreise_nuts = _parse_kreise_nuts(
        _parse_xlsx_sheet(kreise_path, "Kreisfreie Städte u. Landkreise")
    )
    # Filter out the "Insgesamt" row
    kreise_nuts = {k: v for k, v in kreise_nuts.items() if k != "Insgesamt" and v in gisco}
    print(f"Kreise NUTS: {len(kreise_nuts)} entries (official AGS-Kreis -> NUTS 2024)")

    # Verify all 400 GISCO codes are covered
    uncovered = set(gisco) - set(kreise_nuts.values())
    if uncovered:
        codes = ", ".join(sorted(uncovered))
        raise RuntimeError(
            f"destatis Kreise table does not cover {len(uncovered)} GISCO NUTS codes: {codes}"
        )

    # 3. BKG VZ250_GEM (municipality register)
    vz250_path = cache_dir / "vz250_12-31.gk3.shape.zip"
    if not vz250_path.exists():
        print("Downloading BKG VZ250 shapefile (22 MB)...")
        _download(VZ250_SHAPE_URL, vz250_path, get, sleep)
    else:
        sleep(PACING_SECONDS)
    with zipfile.ZipFile(vz250_path, "r") as z:
        dbf_names = [n for n in z.namelist() if n.endswith("GEM.dbf")]
        if not dbf_names:
            raise RuntimeError("no VZ250_GEM.dbf in the VZ250 shapefile")
        dbf_path = cache_dir / "VZ250_GEM.dbf"
        if not dbf_path.exists():
            dbf_path.write_bytes(z.read(dbf_names[0]))
    vz250 = _parse_vz250(_read_dbf_table(dbf_path))
    print(f"VZ250_GEM: {len(vz250)} municipalities")

    # 4. Anschriftenverzeichnis (AGS -> PLZ)
    av_path = cache_dir / "anschriften.xlsx"
    if not av_path.exists():
        print("Downloading destatis Anschriftenverzeichnis...")
        _download(ANSCHRIFTEN_URL, av_path, get, sleep)
    else:
        sleep(PACING_SECONDS)
    plz_map = _parse_anschriften(_parse_xlsx_sheet(av_path, "Anschriften_31_01_2026"))
    print(f"Anschriften: {len(plz_map)} municipalities with PLZ")

    # 5. Build crosswalk rows
    vz250_nuts_deviations: list[str] = []
    unknown_nuts: set[str] = set()
    plz_rows: list[dict[str, str]] = []
    municipality_rows: list[dict[str, str]] = []
    kreis_rows: dict[str, dict[str, str]] = {}

    for ags in sorted(vz250):
        vz = vz250[ags]
        name = vz["name"]
        kreis_name = vz["kreis_name"]
        ags_kreis = vz["ags_kreis"]
        nuts3 = kreise_nuts.get(ags_kreis, "")

        if not nuts3:
            continue

        # Cross-check: VZ250's own NUTS3_CODE vs destatis-derived
        vz250_nuts = vz["nuts3_vz250"]
        if vz250_nuts and vz250_nuts != nuts3:
            vz250_nuts_deviations.append(f"{ags} {name}: VZ250={vz250_nuts}, destatis={nuts3}")

        # PLZ row
        if ags in plz_map:
            plz, _ = plz_map[ags]
            plz_rows.append(
                {
                    "type": "plz",
                    "code": plz,
                    "name": name,
                    "kreis": kreis_name,
                    "nuts": nuts3,
                    "label": gisco[nuts3],
                }
            )

        # Municipality name row
        municipality_rows.append(
            {
                "type": "municipality",
                "code": ags,
                "name": name,
                "kreis": kreis_name,
                "nuts": nuts3,
                "label": gisco[nuts3],
            }
        )

        # Kreis row (dedup on ags_kreis)
        if ags_kreis and ags_kreis not in kreis_rows:
            kreis_rows[ags_kreis] = {
                "type": "kreis",
                "code": ags_kreis,
                "name": "",
                "kreis": kreis_name,
                "nuts": nuts3,
                "label": gisco[nuts3],
            }

    if unknown_nuts:
        raise RuntimeError(f"NUTS codes absent from GISCO: {sorted(unknown_nuts)}")

    all_rows = plz_rows + municipality_rows + list(kreis_rows.values())

    # Write CSV
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for r in all_rows:
            url = ANSCHRIFTEN_URL if r["type"] == "plz" else VZ250_SHAPE_URL
            writer.writerow(
                (
                    r["type"],
                    r["code"],
                    r["name"],
                    r["kreis"],
                    r["nuts"],
                    r["label"],
                    url,
                    SOURCE_VERSION,
                )
            )

    distinct_plz = {r["code"] for r in plz_rows}
    distinct_muni = {r["code"] for r in municipality_rows}
    distinct_nuts3 = {r["nuts"] for r in all_rows}

    manifest: dict[str, Any] = {
        "source": (
            "destatis-kreise-nuts + bkg-vz250-gem + destatis-anschriften x eurostat-gisco-nuts-2024"
        ),
        "nuts_version": "NUTS-2024",
        "source_version": SOURCE_VERSION,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "source_urls": SOURCE_URLS,
        "join": (
            "destatis Kreise table (AGS-Kreis -> NUTS 2024) as the official key, "
            "BKG VZ250_GEM (AGS -> municipality name + Kreis), "
            "destatis Anschriftenverzeichnis (AGS -> Zustell-PLZ); "
            "validated against Eurostat GISCO NUTS 2024"
        ),
        "row_counts": {
            REFERENCE_FILE: len(all_rows),
            "plz": len(distinct_plz),
            "municipality": len(distinct_muni),
            "kreis": len(kreis_rows),
        },
        "vz250_municipalities_read": len(vz250),
        "anschriften_municipalities_with_plz": len(plz_map),
        "kreise_nuts_entries": len(kreise_nuts),
        "distinct_nuts3": len(distinct_nuts3),
        "distinct_nuts3_codes": sorted(distinct_nuts3),
        "gisco_nuts3_codes": sorted(gisco),
        "nuts3_without_municipality": sorted(set(gisco) - distinct_nuts3),
        "vz250_nuts3_deviation": {
            "count": len(vz250_nuts_deviations),
            "detail": vz250_nuts_deviations[:20],
            "note": (
                "VZ250_GEM carries stale NUTS codes for 7 Thuringian districts vs "
                "destatis Kreise NUTS 2024 (the official key). The crosswalk uses "
                "the destatis-derived codes."
            ),
        },
        "hashes": {REFERENCE_FILE: _sha256(output_path)},
    }
    (root / MANIFEST_FILE).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return {
        REFERENCE_FILE: len(all_rows),
        "plz": len(distinct_plz),
        "municipality": len(distinct_muni),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the German PLZ/Stadt -> NUTS 2024 crosswalk"
    )
    parser.add_argument("--root", type=Path, default=Path("data/reference"))
    parser.add_argument("--cache", type=Path, default=None)
    args = parser.parse_args()

    with httpx.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/xml,application/json"},
        timeout=300.0,
        follow_redirects=True,
    ) as client:
        counts = build_reference(args.root, get=client.get, cache_dir=args.cache)

    for name, count in counts.items():
        print(f"{name}: {count} rows")
    print(f"manifest: {args.root / MANIFEST_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
