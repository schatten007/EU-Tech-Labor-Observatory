"""Diagnose the two E4 misses with the collector's own crosswalk resolver.

Prints <= 12 lines: for one query, the tile postcode/place and what
``GermanCrosswalk`` resolves it to. Never prints raw HTML.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scrapers.ba_jobsuche import BA_BASE, GermanCrosswalk  # noqa: E402
from scripts.probe_ba_region import (  # noqa: E402
    _HEADERS,
    extract_state,
    find_result_block,
    tile_location,
    tiles_of,
)


async def main() -> int:
    crosswalk = GermanCrosswalk(Path("data/reference"))
    lines: list[str] = []
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, headers=_HEADERS) as client:
        for label, query in (("DE244-Hof", "Hof"), ("DEB33-Landau", "76829")):
            response = await client.get(f"{BA_BASE}/jobsuche/suche?wo={query}&umkreis=0&page=1")
            state = extract_state(response.text)
            block = find_result_block(state) if state else None
            if block is None:
                lines.append(f"{label}: no state (status={response.status_code})")
                await asyncio.sleep(2.0)
                continue
            tiles = tiles_of(block)
            lines.append(
                f"{label} total={block.get('maxErgebnisse')} tiles={len(tiles)} "
                f"echo={block.get('woOutput', {}).get('bereinigterOrt')}"
            )
            for tile in tiles[:3]:
                plz, ort = tile_location(tile)
                by_plz = crosswalk.resolve_by_plz(plz)
                by_city = crosswalk.resolve_by_city(ort)
                lines.append(
                    f"  plz={plz} ort={str(ort)[:22]} "
                    f"by_plz={by_plz.nuts_code}/{by_plz.status} "
                    f"by_city={by_city.nuts_code}/{by_city.status}"
                )
            await asyncio.sleep(2.0)
    print("\n".join(lines[:12]))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
