"""Envelope probe: does the BA Jobsuche search response carry a total-hits field?

Germany step 2b, probe 1 (SCRAPER_ROADMAP.md 2b.1). The 2026-08-24 probe found
no server-rendered ``Treffer``/``Ergebnisse`` node in the HTML. This probe looks
one level deeper: embedded SSR state (``<script>`` JSON blobs, ``serverApp-state``
and friends) and any ``totalCount``/``hits``-shaped key anywhere in the response.

Prints a compact summary only (<= 20 lines): field name, JSON path, example
value -- or ``absent``. Never prints raw HTML or a full payload.

Serial, 1 s+ pacing, BA user-agent, robots honoured by the collector contract.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.ba_jobsuche import (  # noqa: E402
    BA_BASE,
    BA_PACING_SECONDS,
    BA_USER_AGENT,
)

# State-shaped script tags the Angular/SSR stack is known to use.
_SCRIPT_TAG = re.compile(
    r"<script([^>]*)>(.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_ID_ATTR = re.compile(r"""id=["']([^"']+)["']""", re.IGNORECASE)
_TYPE_ATTR = re.compile(r"""type=["']([^"']+)["']""", re.IGNORECASE)

# Any key that could plausibly carry a total-hits count.
_COUNT_KEY = re.compile(
    r"total|treffer|ergebnis|hits|count|anzahl|maxErgebnisse|numFound",
    re.IGNORECASE,
)

_PROBE_CITIES = ("Berlin", "Hamburg", "Rosenheim")

# Detail-link ids, used only to count tiles rendered on the page.
_REF_ID_PROBE = re.compile(r"/jobsuche/jobdetail/([^/\s\"']+)")


def _walk(node: Any, path: str, out: list[tuple[str, Any]]) -> None:
    """Collect (json_path, value) for count-shaped integer leaves."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else key
            if _COUNT_KEY.search(str(key)) and isinstance(value, (int, float, str)):
                out.append((child, value))
            _walk(value, child, out)
    elif isinstance(node, list):
        # Only descend a bounded prefix: SSR state can hold thousands of tiles.
        for index, value in enumerate(node[:3]):
            _walk(value, f"{path}[{index}]", out)


def _scan_scripts(html: str) -> tuple[list[str], list[tuple[str, str, Any]]]:
    """Return (state-script descriptors, count-shaped hits inside parsed JSON)."""
    descriptors: list[str] = []
    hits: list[tuple[str, str, Any]] = []
    for attrs, body in _SCRIPT_TAG.findall(html):
        script_id = _ID_ATTR.search(attrs)
        script_type = _TYPE_ATTR.search(attrs)
        name = script_id.group(1) if script_id else (
            script_type.group(1) if script_type else "<anonymous>"
        )
        stripped = body.strip()
        if not stripped:
            continue
        looks_like_state = bool(script_id) or (
            script_type and "json" in script_type.group(1).lower()
        )
        if looks_like_state:
            descriptors.append(f"{name} ({len(stripped)} chars)")
        # Try a direct JSON parse; SSR state scripts are usually pure JSON.
        candidate = stripped
        if candidate.startswith("{") or candidate.startswith("["):
            try:
                parsed = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue
            leaves: list[tuple[str, Any]] = []
            _walk(parsed, "", leaves)
            for json_path, value in leaves:
                hits.append((name, json_path, value))
    return descriptors, hits


def _scan_raw(html: str) -> list[tuple[str, str]]:
    """Fallback: count-shaped `"key": <int>` pairs anywhere in the response."""
    found: list[tuple[str, str]] = []
    for match in re.finditer(
        r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:\s*(\d{1,9})', html
    ):
        key, value = match.group(1), match.group(2)
        if _COUNT_KEY.search(key):
            found.append((key, value))
    return found


async def main() -> int:
    lines: list[str] = []
    headers = {
        "User-Agent": BA_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9",
        "Accept-Language": "de-DE,de;q=0.9",
    }
    all_script_names: set[str] = set()
    all_hits: dict[tuple[str, str], Any] = {}
    raw_hits: dict[str, str] = {}
    statuses: list[str] = []
    per_city: dict[str, Any] = {}
    per_city_tiles: dict[str, int] = {}

    async with httpx.AsyncClient(
        timeout=30.0, follow_redirects=True, headers=headers
    ) as client:
        for city in _PROBE_CITIES:
            url = f"{BA_BASE}/jobsuche/suche?wo={city}&page=1"
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:  # pragma: no cover - live probe
                statuses.append(f"{city}=ERR({type(exc).__name__})")
                await asyncio.sleep(BA_PACING_SECONDS)
                continue
            statuses.append(
                f"{city}={response.status_code}/{len(response.text)}B"
            )
            if response.status_code == 200:
                descriptors, hits = _scan_scripts(response.text)
                all_script_names.update(descriptors)
                for name, json_path, value in hits:
                    all_hits.setdefault((name, json_path), value)
                    if json_path.endswith("maxErgebnisse"):
                        per_city[city] = value
                for key, value in _scan_raw(response.text):
                    raw_hits.setdefault(key, value)
                tiles = len(_REF_ID_PROBE.findall(response.text))
                per_city_tiles[city] = tiles
            await asyncio.sleep(BA_PACING_SECONDS)

        # JSON envelope check: the SSR page may be backed by a REST endpoint.
        api_url = (
            f"{BA_BASE}/jobsuche/api/jobs?wo=Berlin&page=1&size=25"
        )
        try:
            api_response = await client.get(
                api_url, headers={**headers, "Accept": "application/json"}
            )
            api_note = f"{api_response.status_code}/{len(api_response.text)}B"
            if api_response.status_code == 200 and api_response.text.startswith(
                ("{", "[")
            ):
                try:
                    parsed = json.loads(api_response.text)
                except (json.JSONDecodeError, ValueError):
                    api_note += " non-json"
                else:
                    leaves: list[tuple[str, Any]] = []
                    _walk(parsed, "", leaves)
                    for json_path, value in leaves[:5]:
                        all_hits.setdefault(("jobsuche/api/jobs", json_path), value)
        except httpx.HTTPError as exc:  # pragma: no cover - live probe
            api_note = f"ERR({type(exc).__name__})"

    lines.append("PROBE ba-envelope (total-hits field)")
    lines.append("pages: " + ", ".join(statuses))
    lines.append(f"api/jobs: {api_note}")
    lines.append(
        "state-scripts: "
        + (", ".join(sorted(all_script_names)[:4]) if all_script_names else "none")
    )
    if all_hits:
        for (name, json_path), value in list(all_hits.items())[:8]:
            shown = str(value)[:40]
            lines.append(f"HIT script={name} path={json_path} example={shown}")
    else:
        lines.append("HIT ssr-state: absent (no count-shaped key in parsed JSON)")
    for city in _PROBE_CITIES:
        lines.append(
            f"per-region {city}: maxErgebnisse="
            f"{per_city.get(city, 'absent')} tiles={per_city_tiles.get(city, 0)}"
        )
    if raw_hits:
        for key, value in list(raw_hits.items())[:6]:
            lines.append(f"RAW key={key} example={value}")
    else:
        lines.append("RAW regex: absent (no count-shaped \"key\": int in response)")
    verdict = "PRESENT" if (all_hits or raw_hits) else "ABSENT"
    lines.append(f"VERDICT total-hits field: {verdict}")
    print("\n".join(lines[:20]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
