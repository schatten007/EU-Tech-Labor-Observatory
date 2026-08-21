"""HMAC-SHA256 pseudonymization (SCRAPERS.md Golden rule 5).

Native identifiers never leave this worktree; ``NormalizedRecord.source_id``
carries only the HMAC hex digest, keyed by the shared ``OBSERVATORY_HMAC_KEY``.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

MIN_KEY_BYTES = 32

ENV_FILE = Path(".env")


def pseudonymize(native_id: str, key: bytes) -> str:
    """HMAC-SHA256 hex digest of ``native_id`` under ``key`` (deterministic)."""
    return hmac.new(key, native_id.encode("utf-8"), hashlib.sha256).hexdigest()


def _read_dotenv(name: str) -> str | None:
    """Read ``KEY=VALUE`` from ``.env`` (no new dependency; whitespace-trimmed)."""
    if not ENV_FILE.exists():
        return None
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() == name:
            return value.strip()
    return None


def load_hmac_key() -> bytes:
    """Load the shared key from the environment or ``.env``; refuse short keys."""
    value = os.environ.get("OBSERVATORY_HMAC_KEY") or _read_dotenv("OBSERVATORY_HMAC_KEY")
    if not value:
        raise RuntimeError("OBSERVATORY_HMAC_KEY is not set (copy .env.example to .env)")
    key = value.encode("utf-8")
    if len(key) < MIN_KEY_BYTES:
        raise RuntimeError(f"OBSERVATORY_HMAC_KEY must be at least {MIN_KEY_BYTES} characters")
    return key
