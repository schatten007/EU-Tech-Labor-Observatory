"""Privacy boundary for normalized posting records.

Raw API responses stay under ignored data/raw/. Collectors pass normalized records
through this module before writing analytical or publishable data.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any

SAFE_FIELDS = (
    "source",
    "scope_id",
    "sweep_id",
    "observed_at",
    "first_published",
    "last_modified",
    "removed_at",
    "country",
    "nuts_code",
    "nuts_label",
    "region_mapping_status",
    "region_mapping_method",
    "nuts_version",
    "esco_occupation_uri",
    "esco_occupation_label",
    "occupation_mapping_status",
    "occupation_mapping_confidence",
    "occupation_mapping_method",
    "source_language",
    "jobtech_taxonomy_version",
    "esco_version",
    "lang",
    "skill_uris",
    "skill_mappings",
    "number_of_vacancies",
)


def key_from_env() -> bytes:
    key = os.environ.get("OBSERVATORY_HMAC_KEY", "").encode()
    if len(key) < 32:
        raise ValueError("OBSERVATORY_HMAC_KEY must be at least 32 characters")
    return key


def sanitize_record(record: dict[str, Any], key: bytes) -> dict[str, Any]:
    if len(key) < 32:
        raise ValueError("HMAC key must be at least 32 bytes")
    source = record.get("source")
    source_id = record.get("source_id")
    if not isinstance(source, str) or not source or not isinstance(source_id, str) or not source_id:
        raise ValueError("source and source_id must be non-empty strings")

    # ponytail: an allowlist is both shorter and safer than maintaining every PII alias.
    safe = {field: record[field] for field in SAFE_FIELDS if field in record}
    safe["source_id"] = hmac.new(key, f"{source}\0{source_id}".encode(), hashlib.sha256).hexdigest()
    return safe


def sanitize_file(source: Path, target: Path, key: bytes) -> None:
    if source.resolve() == target.resolve():
        raise ValueError("input and output paths must differ")
    target.parent.mkdir(parents=True, exist_ok=True)
    with source.open(encoding="utf-8") as rows, target.open("w", encoding="utf-8") as output:
        for line in rows:
            if line.strip():
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("each JSON line must be an object")
                output.write(json.dumps(sanitize_record(record, key), ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Sanitize normalized NDJSON postings")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    args = parser.parse_args()
    sanitize_file(args.source, args.target, key_from_env())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
