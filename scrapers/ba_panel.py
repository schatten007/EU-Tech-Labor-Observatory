"""Frozen NUTS-3 panel definition for BA Jobsuche (Germany step 2b).

The census (`de-stock-segmented`) was cancelled on 2026-08-31: the observatory's
published views need breadth and repeat observations, not exhaustive counts, and
only repeat sweeps of a *frozen* panel can populate the survival series. This
module pins that panel.

Design (locked by the 2026-09-01 probes E1-E6 in `SCRAPER_FEASIBILITY.md`):

* **Frame** -- the 400 ``source_type == "kreis"`` rows of the pinned crosswalk,
  the authoritative destatis AGS->NUTS 2024 key covering all 400 GISCO NUTS-3
  codes.
* **One query per region.** BA has *no* Kreis-level addressing: every
  ``wo=Landkreis X`` collapses to the same 7 Rosenheim postings and
  ``woOutput.suchmodus`` only ever takes the values ``ORTSUCHE``,
  ``UMKREISSUCHE`` or ``UNGUELTIG``. So each region is addressed by a place:
  its largest-town municipality when that name is unique in the register,
  otherwise its unambiguous anchor postcode. Always ``umkreis=0``, which the
  census proved tight (Tier-3 provenance stays ``mapped``).
* **Deterministic, therefore frozen.** Selection reads the pinned reference
  only -- no measurement, no randomisation, so there is no seed and no way for
  the query set to drift between sweeps. Membership drift would fabricate
  closures and corrupt survival durations.
* **Declared cap.** At most :data:`BA_PANEL_PAGE_CAP` pages (25 items each) per
  region. The cap is part of the declared scope: it is encoded in
  ``scope_json`` *and* stated in ``coverage_limitations`` as a stratified
  region-bounded sample, never hidden behind ``expected_pages == k``.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

#: Scope for the frozen panel. Distinct from the cancelled ``de-stock-segmented``
#: census scope, which is never re-swept (a resumption after the gap would
#: record a mass fake ``inferred_absence`` closure spike downstream).
BA_PANEL_SCOPE_ID = "de-nuts3-panel"

#: Within-stratum page cap, a scope constant. 400 regions x (1 + up to 3 more)
#: pages ~= 1,600 requests ~= 30 min at the charter's 1 s pacing floor.
BA_PANEL_PAGE_CAP = 4

#: Radius policy. ``0`` keeps the source's own location filter tight, which is
#: what makes per-region provenance ``mapped`` rather than ``low_confidence``.
BA_PANEL_UMKREIS = 0

#: Expected frame size: the destatis Kreise key covers every GISCO NUTS-3 code.
BA_PANEL_EXPECTED_REGIONS = 400

#: Sweep-1 acceptance bar (SCRAPER_ROADMAP.md step 2b DoD).
BA_PANEL_MIN_REGIONS = 390

#: Side file written next to the observations, carrying the per-region
#: denominators the published views need.
BA_PANEL_REGIONS_FILE = "panel_regions.json"

_REFERENCE_FILE = "germany_plz_nuts_2024.csv"

QueryForm = Literal["name", "plz"]


class PanelEntry(BaseModel, frozen=True):
    """One frozen panel stratum: exactly one region, exactly one query."""

    nuts_code: str
    nuts_label: str
    kreis_name: str
    form: QueryForm
    value: str

    @property
    def nuts1(self) -> str:
        return self.nuts_code[:3]

    @property
    def query(self) -> str:
        """The ``wo=`` query fragment. Byte-identical across sweeps."""
        return f"wo={self.value}&umkreis={BA_PANEL_UMKREIS}"

    @property
    def membership_line(self) -> str:
        """Canonical line hashed into the membership hash."""
        return f"{self.nuts_code}\t{self.form}\t{self.value}"


def _reference_rows(reference_dir: Path) -> list[dict[str, str]]:
    path = reference_dir / _REFERENCE_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"missing German crosswalk reference: {path} "
            "(rebuild with `python -m scrapers.reference_germany`)"
        )
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def build_panel(reference_dir: Path = Path("data/reference")) -> list[PanelEntry]:
    """Build the frozen panel: one query per NUTS-3, ordered by NUTS code.

    Selection is a pure function of the pinned reference file, so two builds
    from the same reference are byte-identical. The reference itself is pinned
    and its hash travels in the manifest's ``reference_hashes``.
    """
    rows = _reference_rows(reference_dir)

    kreis_rows = {row["nuts_code"]: row for row in rows if row["source_type"] == "kreis"}

    # Names that identify exactly one NUTS-3 across the whole register; the 397
    # ambiguous ones carry no single-region provenance and are not usable.
    name_regions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_type"] == "municipality" and row["municipality_name"]:
            name_regions[row["municipality_name"].casefold()].add(row["nuts_code"])
    unique_names = {name for name, codes in name_regions.items() if len(codes) == 1}

    # Postcodes that identify exactly one NUTS-3 (11 of 4,862 do not).
    plz_regions: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_type"] == "plz" and row["source_code"]:
            plz_regions[row["source_code"]].add(row["nuts_code"])
    unambiguous_plz = {code for code, codes in plz_regions.items() if len(codes) == 1}

    # Municipality -> its postcodes, per region, from unambiguous codes only.
    region_towns: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in rows:
        if row["source_type"] == "plz" and row["source_code"] in unambiguous_plz:
            region_towns[row["nuts_code"]][row["municipality_name"]].add(row["source_code"])

    # Municipality names per region from the municipality slice, which covers
    # 400/400 regions and is the fallback for the 4 regions whose postcodes are
    # all ambiguous.
    region_names: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row["source_type"] == "municipality" and row["municipality_name"]:
            region_names[row["nuts_code"]].add(row["municipality_name"])

    panel: list[PanelEntry] = []
    for nuts_code in sorted(kreis_rows):
        kreis = kreis_rows[nuts_code]
        towns = region_towns.get(nuts_code, {})
        # Largest-town proxy: most distinct postcodes, ties broken by name so
        # the choice is stable. Cities carry many postcodes, villages one.
        ranked = sorted(towns, key=lambda name: (-len(towns[name]), name))
        chosen_name = next((name for name in ranked if name.casefold() in unique_names), None)
        form: QueryForm
        if chosen_name is not None:
            form = "name"
            value = chosen_name
        elif ranked:
            # Fall back to the anchor postcode of the largest town, exactly as
            # the census resolved its 397 ambiguous municipality names.
            form = "plz"
            value = min(towns[ranked[0]])
        else:
            # No unambiguous postcode in this region at all: take a unique-name
            # municipality from the register instead.
            fallback = sorted(
                name for name in region_names.get(nuts_code, ()) if name.casefold() in unique_names
            )
            if not fallback:
                continue
            form = "name"
            value = fallback[0]
        panel.append(
            PanelEntry(
                nuts_code=nuts_code,
                nuts_label=kreis["nuts_label"],
                kreis_name=kreis["kreis_name"],
                form=form,
                value=value,
            )
        )
    return panel


def panel_membership_hash(panel: list[PanelEntry]) -> str:
    """SHA-256 over the ordered query list -- the frozen-panel integrity key.

    Any addition, removal, reordering or re-wording of a query changes this
    hash, which is what ``make check-ba-panel`` compares across sweeps.
    """
    digest = hashlib.sha256()
    digest.update("\n".join(entry.membership_line for entry in panel).encode("utf-8"))
    return digest.hexdigest()


def ba_panel_scope_params(panel: list[PanelEntry]) -> dict[str, object]:
    """Scope parameters for the manifest. ``scope_hash`` is the SHA-256 of this."""
    forms = sorted({entry.form for entry in panel})
    return {
        "country": "DE",
        "frame": "nuts3-kreise-destatis-2024",
        "frame_size": len(panel),
        "membership_hash": panel_membership_hash(panel),
        "page_cap_per_region": BA_PANEL_PAGE_CAP,
        "items_per_page": 25,
        "rows_cap_per_region": BA_PANEL_PAGE_CAP * 25,
        "query_forms": forms,
        "query_param": "wo",
        "umkreis": BA_PANEL_UMKREIS,
        "randomization": "none",
        "seed": None,
        "sample_design": "stratified region-bounded sample, not a census",
        "frozen": True,
        "replaces_scope": "de-stock-segmented (cancelled 2026-08-31)",
    }


def ba_panel_coverage_limitations(panel: list[PanelEntry]) -> str:
    """The declared cap, stated in prose for ``coverage_limitations``."""
    return (
        "Stratified region-bounded sample, not a census: the frozen NUTS-3 panel "
        f"queries {len(panel)} regions (frame = destatis Kreise AGS->NUTS 2024 key, "
        f"membership hash {panel_membership_hash(panel)[:16]}...), one place query "
        f"per region with umkreis={BA_PANEL_UMKREIS}, capped at "
        f"{BA_PANEL_PAGE_CAP} pages x 25 items = {BA_PANEL_PAGE_CAP * 25} rows per "
        "region. Regions whose advertised stock exceeds that cap are sampled, not "
        "enumerated; the per-region advertised totals (suchergebnis.maxErgebnisse) "
        f"are recorded in {BA_PANEL_REGIONS_FILE} so every region carries its own "
        "denominator. BA has no Kreis-level location filter, so a region is "
        "addressed by its largest unique-name town, or by its unambiguous anchor "
        "postcode where no unique name exists. The query set is frozen and "
        "unseeded: it is a pure function of the pinned reference, identical across "
        "sweeps."
    )


def write_panel_regions(partition: Path, meta: dict[str, Any]) -> Path:
    """Write the per-region denominator side file into a written partition."""
    path = partition / BA_PANEL_REGIONS_FILE
    path.write_text(
        json.dumps(meta, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path
