"""Unit tests for HMAC pseudonymization (charter Golden rule 5)."""

from pathlib import Path

import pytest
from pytest import MonkeyPatch

from scrapers.sanitize import load_hmac_key, pseudonymize

KEY = b"test-only-key-with-at-least-32-bytes"


def test_pseudonymize_is_deterministic_hex_and_hides_native_id() -> None:
    first = pseudonymize("native-1", KEY)
    assert pseudonymize("native-1", KEY) == first
    assert len(first) == 64
    assert first != "native-1"


def test_pseudonymize_is_keyed() -> None:
    assert pseudonymize("native-1", KEY) != pseudonymize("native-1", b"x" * 32)


def test_load_hmac_key_requires_a_long_enough_secret(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OBSERVATORY_HMAC_KEY", raising=False)
    with pytest.raises(RuntimeError):
        load_hmac_key()

    monkeypatch.setenv("OBSERVATORY_HMAC_KEY", "short")
    with pytest.raises(RuntimeError):
        load_hmac_key()

    monkeypatch.setenv("OBSERVATORY_HMAC_KEY", "k" * 32)
    assert load_hmac_key() == b"k" * 32


def test_load_hmac_key_prefers_env_over_dotenv(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"OBSERVATORY_HMAC_KEY={'k' * 40}\n", encoding="utf-8")
    monkeypatch.setenv("OBSERVATORY_HMAC_KEY", "short")

    with pytest.raises(RuntimeError):
        load_hmac_key()


def test_load_hmac_key_falls_back_to_dotenv(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OBSERVATORY_HMAC_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(f"OBSERVATORY_HMAC_KEY={'k' * 40}\n", encoding="utf-8")

    assert load_hmac_key() == b"k" * 40
