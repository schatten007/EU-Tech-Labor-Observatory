"""Collect a private JobTech response into sanitized observation NDJSON.

This command is offline. The input is a raw response recorded by probe.py and the
output belongs under ignored data/raw/.

    uv run python -m scripts.collect SOURCE TARGET
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from scripts.sanitize import key_from_env, sanitize_record


def normalize_jobtech_hit(hit: dict[str, Any], observed_at: str) -> dict[str, Any]:
    source_id = hit.get("id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("JobTech hit has no non-empty id")

    address = hit.get("workplace_address")
    if not isinstance(address, dict):
        address = {}

    return {
        "source": "jobtech",
        "source_id": source_id,
        "observed_at": observed_at,
        "first_published": hit.get("publication_date"),
        "last_modified": hit.get("last_publication_date"),
        "removed_at": hit.get("removed_date"),
        "nuts_code": None,
        "country": hit.get("country_code") or address.get("country_code") or "SE",
        "esco_occupation_uri": None,
        "lang": "sv",
        "skill_uris": [],
        "number_of_vacancies": hit.get("number_of_vacancies"),
    }


def collect_jobtech(source: Path, target: Path, observed_at: str, key: bytes) -> int:
    """Normalize and sanitize all hits in one recorded JobTech response."""
    if source.resolve() == target.resolve():
        raise ValueError("input and output paths must differ")
    payload = json.loads(source.read_text(encoding="utf-8"))
    hits = payload.get("hits") if isinstance(payload, dict) else None
    if not isinstance(hits, list):
        raise ValueError("JobTech response must contain a hits list")

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as output:
        for hit in hits:
            if not isinstance(hit, dict):
                raise ValueError("each JobTech hit must be an object")
            safe = sanitize_record(normalize_jobtech_hit(hit, observed_at), key)
            output.write(json.dumps(safe, ensure_ascii=False) + "\n")
    return len(hits)


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect a recorded JobTech response")
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument(
        "--observed-at",
        default=datetime.now(UTC).isoformat(),
        help="observation timestamp (default: current UTC time)",
    )
    args = parser.parse_args()
    count = collect_jobtech(args.source, args.target, args.observed_at, key_from_env())
    print(f"wrote {args.target} ({count} observations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
