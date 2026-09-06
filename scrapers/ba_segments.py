"""BA Jobsuche segment frontier (Increment 9 — segmented German stock build).

The segmented collector does not query Germany as one 10,000-listing window; it
walks a *frontier* of location-bounded segments, each ``&wo=<key>&umkreis=0``
query, so every segment's pagination either ends in an empty page (provably
complete) or fills the 400-page cap (provably truncated, then subdivided). This
module defines the segment model, the durable frontier store
(``data/state/ba_segment_frontier.json``), and the initial segment tree.

Segment levels (locked by the gate probes recorded in ``SCRAPER_FEASIBILITY.md``):

- Level 0 — unscoped catch-all (1): collects postings with no resolvable
  location (the non-geographic markers). Tier-1 semantics only, never invents a
  region.
- Level 1 — Bundesländer (16): coarse tier and Tier-2 disambiguation context.
  Structural: processed with a truncation probe and marked ``subdivided`` with
  its municipality children (the children are the collection units).
- Level 2 — the regional-coverage backbone: **municipality-name segments** for
  the 10,085 single-NUTS-3 municipality names, plus **PLZ segments** for the 397
  names that span multiple NUTS 3 (each of those names has crosswalk PLZ rows,
  and every such PLZ maps to exactly one NUTS 3, so the source's own postcode
  filter is the disambiguator). Every level-2 segment carries exactly one NUTS 3.
- Level 3 — PLZ segments inside a truncated level-2 segment (the crosswalk's
  PLZ rows for that NUTS 3).
- Level 4 — recency slices (``&veroeffentlichtseit=N``) of a still-truncating
  level-3 segment, used only to subdivide, never to scope occupation.

``umkreis=0`` is the locked policy: Tier-3 provenance is ``mapped`` only under
``umkreis=0``; any radius downgrades Tier 3 to ``low_confidence``.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from scrapers.ba_jobsuche import GermanCrosswalk

#: Bundesland name (BA's ``wo=`` location index) -> NUTS-1 prefix (``nuts_code[:3]``).
BA_BUNDESLAENDER: dict[str, str] = {
    "Baden-Württemberg": "DE1",
    "Bayern": "DE2",
    "Berlin": "DE3",
    "Brandenburg": "DE4",
    "Bremen": "DE5",
    "Hamburg": "DE6",
    "Hessen": "DE7",
    "Mecklenburg-Vorpommern": "DE8",
    "Niedersachsen": "DE9",
    "Nordrhein-Westfalen": "DEA",
    "Rheinland-Pfalz": "DEB",
    "Saarland": "DEC",
    "Sachsen": "DED",
    "Sachsen-Anhalt": "DEE",
    "Schleswig-Holstein": "DEF",
    "Thüringen": "DEG",
}

#: Recency-window day values for level-4 subdivision (BA ``veroeffentlichtseit``).
BA_LEVEL4_RECENCY_DAYS: tuple[int, ...] = (1, 7, 30)

SegmentStatus = Literal["pending", "complete", "truncated", "subdivided", "failed"]


class Segment(BaseModel):
    """One location-bounded BA query in the subdivision tree.

    ``key`` is the exact query suffix appended to the search URL (e.g.
    ``"wo=Starnberg&umkreis=0"``); the unscoped catch-all uses ``""``. A segment
    whose ``nuts_code`` is a single NUTS 3 is a Tier-3 provenance source (the
    source's own location filter asserted that region); Bundesland/unscoped
    segments have ``nuts_code=None`` and never invoke Tier 3.
    """

    key: str
    level: int = Field(ge=0, le=4)
    nuts_code: str | None = None
    nuts1: str | None = None
    parent: str | None = None
    status: SegmentStatus = "pending"
    pages_fetched: int = Field(default=0, ge=0)
    rows_yielded: int = Field(default=0, ge=0)
    last_page_full: bool = False
    umkreis: int = 0
    recency_days: int | None = None


def _wo_key(value: str, *, umkreis: int, recency_days: int | None = None) -> str:
    """Build a segment key from a ``wo=`` value and the locked umkreis policy."""
    if value == "":
        return f"umkreis={umkreis}"
    from urllib.parse import quote

    key = f"wo={quote(value)}&umkreis={umkreis}"
    if recency_days is not None:
        key += f"&veroeffentlichtseit={recency_days}"
    return key


def build_initial_frontier(
    crosswalk: GermanCrosswalk,
    *,
    umkreis: int = 0,
) -> SegmentFrontier:
    """Build the level-0/1/2 frontier from the crosswalk (the ``--fresh`` set).

    Municipality names that resolve to exactly one NUTS 3 become name segments;
    the 397 names spanning several NUTS 3 become PLZ segments (each PLZ is a
    single-NUTS-3 key, so provenance is never ambiguous).
    """
    segments: list[Segment] = []

    # Level 0: unscoped national catch-all (no-location postings).
    segments.append(
        Segment(
            key="",
            level=0,
            nuts_code=None,
            nuts1=None,
            status="pending",
            umkreis=umkreis,
        )
    )

    # Level 1: Bundesländer. City-states whose name is also a municipality name
    # (Berlin, Bremen, Hamburg) are pre-marked ``subdivided``: the identical
    # level-2 municipality segment covers the whole state with a NUTS-3
    # provenance, so there is no separate Bundesland query to run.
    municipality_names = set(crosswalk.municipality_names_by_nuts3())
    for name, nuts1 in BA_BUNDESLAENDER.items():
        covered_by_city = name in municipality_names
        segments.append(
            Segment(
                key=_wo_key(name, umkreis=umkreis),
                level=1,
                nuts_code=None,
                nuts1=nuts1,
                status="subdivided" if covered_by_city else "pending",
                umkreis=umkreis,
            )
        )

    # Level 2: municipalities (single-NUTS-3 names) + PLZ for ambiguous names.
    for name, codes in crosswalk.municipality_names_by_nuts3().items():
        if len(codes) == 1:
            nuts = next(iter(codes))
            segments.append(
                Segment(
                    key=_wo_key(name, umkreis=umkreis),
                    level=2,
                    nuts_code=nuts,
                    nuts1=nuts[:3],
                    status="pending",
                    umkreis=umkreis,
                )
            )
            continue
        # Ambiguous name: use the name's PLZ rows (each maps to one NUTS 3).
        for plz, nuts in crosswalk.plz_rows_for_name(name):
            segments.append(
                Segment(
                    key=_wo_key(plz, umkreis=umkreis),
                    level=2,
                    nuts_code=nuts,
                    nuts1=nuts[:3],
                    status="pending",
                    umkreis=umkreis,
                )
            )

    return SegmentFrontier(segments)


class SegmentFrontier:
    """Durable, resumable segment store.

    The frontier is a dict keyed by ``(level, key)`` — a Bundesland segment and
    a municipality segment can share the same ``wo=`` value (Berlin is both a
    state and a city), so the level is part of the identity. Segments are
    processed atomically (a segment's pages are never split across runs); state
    is written after every segment, so an interrupted run loses at most one
    segment.
    """

    def __init__(self, segments: Iterable[Segment] | None = None) -> None:
        self._segments: dict[tuple[int, str], Segment] = {}
        if segments:
            for segment in segments:
                self._segments[(segment.level, segment.key)] = segment

    # -- persistence --------------------------------------------------------

    @classmethod
    def load(cls, path: Path) -> SegmentFrontier:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(Segment.model_validate(segment) for segment in data)

    def save(self, path: Path) -> None:
        payload = [segment.model_dump(mode="json") for segment in self._segments.values()]
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # -- access -------------------------------------------------------------

    def get(self, key: str, *, level: int | None = None) -> Segment | None:
        """Look up a segment by key; ``level`` disambiguates shared keys."""
        if level is not None:
            return self._segments.get((level, key))
        for (_lvl, k), segment in self._segments.items():
            if k == key:
                return segment
        return None

    def enqueue(self, segment: Segment) -> bool:
        """Add a child segment if its ``(level, key)`` is not already present."""
        if (segment.level, segment.key) in self._segments:
            return False
        self._segments[(segment.level, segment.key)] = segment
        return True

    def __len__(self) -> int:
        return len(self._segments)

    @property
    def segments(self) -> dict[tuple[int, str], Segment]:
        return self._segments

    def pending(self, *, min_level: int = 0) -> Iterator[Segment]:
        """Breadth-first, region-first order; only ``pending``/``failed`` yielded.

        Execution order follows the plan's §6 rule — **every Kreis (level 2) at
        level 2 first** — so the regional backbone (municipalities/PLZ) is
        collected before the catch-all tiers (level 0/1) and before any
        subdivision children (level 3/4). Within level 2 the order is by NUTS 3
        code then key, giving every region at least one segment before any
        region gets a second, and no metro subdivision starts until all
        level-2 segments are complete. A resumed run continues from
        ``pending``/``failed`` and never re-fetches a complete/subdivided
        segment.
        """
        # Processing priority: level 2 (regional backbone) first, then the
        # level-0 unscoped catch-all and level-1 Bundesländer probes, then the
        # level-3/4 subdivision children of truncated segments.
        _priority = {2: 0, 0: 1, 1: 2, 3: 3, 4: 4}
        ordered = sorted(
            (s for s in self._segments.values() if s.status in ("pending", "failed")),
            key=lambda s: (_priority[s.level], s.nuts_code or "", s.key),
        )
        return iter(s for s in ordered if s.level >= min_level)
