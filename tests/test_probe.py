import sys
from typing import Never

from pytest import MonkeyPatch

from scripts import probe, sanitize


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
