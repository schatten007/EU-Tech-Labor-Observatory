import json
import sys
from pathlib import Path
from typing import Never

from pytest import MonkeyPatch

from scripts import collect, probe, sanitize


def fail_network(*args: object, **kwargs: object) -> Never:
    raise AssertionError("default command attempted network access")


def test_probe_defaults_offline(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["probe.py"])
    monkeypatch.setattr(probe, "urlopen", fail_network)

    assert probe.main() == 2


def test_sanitize_record_keeps_analysis_without_identifiers() -> None:
    row = {
        "source": "example",
        "source_id": "native-42",
        "observed_at": "2026-08-13T12:00:00Z",
        "country": "SE",
        "skill_uris": ["urn:skill:python"],
        "title": "Private title",
        "text": "Private description",
        "employer": "Private employer",
        "contact": "Private contact",
        "url": "private-url",
    }
    key = b"test-only-key-with-at-least-32-bytes"

    safe = sanitize.sanitize_record(row, key)

    assert safe == sanitize.sanitize_record(row, key)
    assert safe["source_id"] != row["source_id"]
    assert safe.keys() == {"source", "source_id", "observed_at", "country", "skill_uris"}


def test_collect_jobtech_writes_sanitized_observations(tmp_path: Path) -> None:
    source = tmp_path / "jobtech.json"
    target = tmp_path / "observations.ndjson"
    source.write_text(
        json.dumps(
            {
                "hits": [
                    {
                        "id": "native-42",
                        "headline": "Private title",
                        "description": {"text": "Private description"},
                        "employer": {"name": "Private employer"},
                        "country_code": "SE",
                        "publication_date": "2026-08-13T12:00:00Z",
                        "number_of_vacancies": 2,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert collect.collect_jobtech(source, target, "2026-08-13T13:00:00Z", b"k" * 32) == 1
    row = json.loads(target.read_text(encoding="utf-8"))

    assert row["source"] == "jobtech"
    assert row["observed_at"] == "2026-08-13T13:00:00Z"
    assert row["number_of_vacancies"] == 2
    assert len(row["source_id"]) == 64
    assert row["nuts_code"] is None
    assert row["esco_occupation_uri"] is None
    assert "headline" not in row
    assert "employer" not in row
    assert "description" not in row
