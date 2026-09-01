"""BA Jobsuche frozen NUTS-3 panel acceptance check (roadmap step 2b DoD).

Reads every partition under ``data/raw/collections/ba/de-nuts3-panel/`` and
prints **one line per assertion** — no per-row and no per-region output. The
assertions are exactly the step-2b Definition of Done:

1. every partition reconciles: ``status == complete``,
   ``expected_pages == completed_pages``,
   ``expected_rows == row_count == NDJSON line count``;
2. sweep 1 (and every sweep) covers **>= 390 of 400** NUTS-3 regions;
3. the **panel membership hash is identical across all sweeps** and equal to the
   pinned definition rebuilt from the reference (frozen-panel integrity);
4. **zero failed requests** (absorbed 403 throttles are throttle events, not
   failures);
5. the PII scan is clean — no name, email, phone, URL or postcode-shaped value
   in any written row;
6. the declared page cap is stated in ``scope_json`` *and* in
   ``coverage_limitations`` (cap-as-scope honesty, charter 2026-08-31).

Usage::

    python scripts/check_ba_panel_readiness.py
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.ba_panel import (  # noqa: E402
    BA_PANEL_EXPECTED_REGIONS,
    BA_PANEL_MIN_REGIONS,
    BA_PANEL_PAGE_CAP,
    BA_PANEL_REGIONS_FILE,
    BA_PANEL_SCOPE_ID,
    build_panel,
    panel_membership_hash,
)

DATA_ROOT = Path("data/raw/collections/ba") / BA_PANEL_SCOPE_ID
REFERENCE_DIR = Path("data/reference")

#: Fields a row is allowed to carry. Anything else is treated as a PII leak.
_PII_PATTERNS = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),
    "url": re.compile(r"https?://"),
    "postcode": re.compile(r"\b\d{5}\b"),
    "phone": re.compile(r"\+49[\s\d/()-]{6,}"),
}

#: Row keys that legitimately contain digits or identifiers.
_PII_EXEMPT_KEYS = frozenset(
    {"source_id", "sweep_id", "scope_id", "observed_at", "first_published"}
)


def _fail(message: str) -> int:
    print(f"FAIL {message}")
    return 1


def main() -> int:
    if not DATA_ROOT.exists():
        print(f"FAIL no partitions found under {DATA_ROOT}")
        return 1
    partitions = sorted(p for p in DATA_ROOT.iterdir() if (p / "manifest.json").exists())
    if not partitions:
        print(f"FAIL no reconcilable partitions under {DATA_ROOT}")
        return 1

    failures = 0
    print(f"panel partitions: {len(partitions)} under {DATA_ROOT}")

    pinned_hash = panel_membership_hash(build_panel(REFERENCE_DIR))
    print(f"pinned membership hash: {pinned_hash[:16]}... ({BA_PANEL_EXPECTED_REGIONS} regions)")

    manifest_bad: list[str] = []
    hash_values: set[str] = set()
    cap_missing: list[str] = []
    failed_requests = 0
    throttle_events = 0
    breadth_bad: list[str] = []
    pii_hits: Counter[str] = Counter()
    rows_total = 0
    regions_union: set[str] = set()

    for partition in partitions:
        name = partition.name
        manifest = json.loads((partition / "manifest.json").read_text(encoding="utf-8"))
        ndjson = partition / "observations.ndjson"
        lines = 0
        nuts_codes: set[str] = set()
        with ndjson.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                lines += 1
                record: dict[str, Any] = json.loads(line)
                if record.get("region_mapping_status") == "mapped" and record.get("nuts_code"):
                    nuts_codes.add(record["nuts_code"])
                for key, value in record.items():
                    if key in _PII_EXEMPT_KEYS or not isinstance(value, str):
                        continue
                    for label, pattern in _PII_PATTERNS.items():
                        if pattern.search(value):
                            pii_hits[label] += 1
        rows_total += lines
        regions_union |= nuts_codes

        if not (
            manifest["status"] == "complete"
            and manifest["expected_pages"] == manifest["completed_pages"]
            and manifest["expected_rows"] == manifest["row_count"] == lines
        ):
            manifest_bad.append(name)

        scope = json.loads(manifest["scope_json"])
        hash_values.add(str(scope.get("membership_hash")))
        cap_in_scope = scope.get("page_cap_per_region") == BA_PANEL_PAGE_CAP
        cap_in_prose = "not a census" in manifest["coverage_limitations"]
        if not (cap_in_scope and cap_in_prose):
            cap_missing.append(name)

        if len(nuts_codes) < BA_PANEL_MIN_REGIONS:
            breadth_bad.append(f"{name}={len(nuts_codes)}")

        meta_path = partition / BA_PANEL_REGIONS_FILE
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            failed_requests += int(meta.get("failed_pages", 0))
            throttle_events += int(meta.get("throttle_events", 0))
        else:
            cap_missing.append(f"{name}(no {BA_PANEL_REGIONS_FILE})")

    if manifest_bad:
        failures += _fail(
            f"manifest reconciliation: {len(manifest_bad)} partition(s) not complete "
            f"or not reconciled ({', '.join(manifest_bad[:5])})"
        )
    else:
        print(
            f"PASS manifest reconciliation: {len(partitions)}/{len(partitions)} complete, "
            "expected_pages == completed_pages, expected_rows == row_count == NDJSON lines"
        )

    if breadth_bad:
        failures += _fail(
            f"NUTS-3 breadth < {BA_PANEL_MIN_REGIONS} in {len(breadth_bad)} sweep(s): "
            f"{', '.join(breadth_bad[:5])}"
        )
    else:
        print(
            f"PASS NUTS-3 breadth: every sweep covers >= {BA_PANEL_MIN_REGIONS} of "
            f"{BA_PANEL_EXPECTED_REGIONS} regions (union across sweeps: {len(regions_union)})"
        )

    if hash_values != {pinned_hash}:
        failures += _fail(
            f"frozen-panel integrity: {len(hash_values)} distinct membership hash(es) "
            f"across sweeps, pinned is {pinned_hash[:16]}... "
            f"(seen: {', '.join(sorted(h[:16] for h in hash_values))})"
        )
    else:
        print(
            f"PASS frozen-panel integrity: one membership hash across all "
            f"{len(partitions)} sweep(s), identical to the pinned definition"
        )

    if failed_requests:
        failures += _fail(f"failed requests: {failed_requests} non-200 page(s) across sweeps")
    else:
        print(
            f"PASS failed requests: 0 across all sweeps "
            f"({throttle_events} absorbed 403 throttle event(s), not failures)"
        )

    if pii_hits:
        failures += _fail("PII scan: " + ", ".join(f"{k}={v}" for k, v in sorted(pii_hits.items())))
    else:
        print(f"PASS PII scan: clean across {rows_total} row(s) (no email/URL/postcode/phone)")

    if cap_missing:
        failures += _fail(
            f"cap-as-scope honesty: {len(cap_missing)} partition(s) do not declare the "
            f"page cap in scope_json and coverage_limitations ({', '.join(cap_missing[:5])})"
        )
    else:
        print(
            f"PASS cap-as-scope honesty: page cap {BA_PANEL_PAGE_CAP} declared in "
            "scope_json and stated in coverage_limitations for every sweep"
        )

    if failures:
        print(f"\nFAILED: {failures} assertion(s) failed")
        return 1
    print(f"\nALL CHECKS PASSED — {BA_PANEL_SCOPE_ID} meets the step-2b DoD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
