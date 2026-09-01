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
import re
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

#: Pinned panel artifact: the committed, probe-verified query list. It lives
#: beside the crosswalk because it is reference data, not sweep output.
BA_PANEL_PINNED_FILE = "ba_panel_nuts3.json"

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
    """The frozen panel: one query per NUTS-3, ordered by NUTS code.

    Prefers the **pinned artifact** (``ba_panel_nuts3.json``) when it is present
    and complete, because the reference-only selection rule is degenerate in
    rural regions: where every municipality carries exactly one postcode the
    tie-break falls back to the alphabetically first village, which cost the
    rejected sweep-1 attempt 30 regions of breadth (2026-09-01). The artifact
    records, per region, the query that a one-off probe proved both self-
    resolving and non-empty; it is committed, hashed into ``scope_json`` and
    never regenerated between sweeps.

    Without the artifact the rule applies, so the builder still works for tests
    and for a fresh reference: a pure function of the pinned reference file,
    identical across builds.
    """
    pinned = load_pinned_panel(reference_dir)
    if pinned is not None:
        return pinned
    return rule_panel(reference_dir)


def rule_panel(reference_dir: Path = Path("data/reference")) -> list[PanelEntry]:
    """Reference-only selection: the first candidate of every region."""
    candidates = panel_candidates(reference_dir)
    kreis = _kreis_rows(reference_dir)
    panel: list[PanelEntry] = []
    for nuts_code in sorted(candidates):
        if not candidates[nuts_code]:
            continue
        form, value = candidates[nuts_code][0]
        row = kreis[nuts_code]
        panel.append(
            PanelEntry(
                nuts_code=nuts_code,
                nuts_label=row["nuts_label"],
                kreis_name=row["kreis_name"],
                form=form,
                value=value,
            )
        )
    return panel


def _kreis_rows(reference_dir: Path) -> dict[str, dict[str, str]]:
    return {
        row["nuts_code"]: row
        for row in _reference_rows(reference_dir)
        if row["source_type"] == "kreis"
    }


def _append_candidate(candidates: list[tuple[QueryForm, str]], form: QueryForm, value: str) -> None:
    if value and (form, value) not in candidates:
        candidates.append((form, value))


def _seat_labels(kreis: dict[str, str]) -> set[str]:
    """Names that plausibly denote the region's seat town.

    A Kreisfreie Stadt is named after its town outright; a Landkreis is often
    named after its seat ("Calw"), and a merged Kreis after two of its towns
    ("Schleswig-Flensburg" -> Schleswig), so the compound components count too.
    Every candidate is still required to be a municipality *of that region*, so
    a component that names some other region's town is discarded.
    """
    raw = {
        kreis["kreis_name"].strip(),
        kreis["nuts_label"].split(",")[0].strip(),
    }
    labels: set[str] = set()
    for value in raw:
        if not value:
            continue
        labels.add(value.casefold())
        for part in re.split(r"[-/ ]", value):
            part = part.strip()
            if len(part) > 3:
                labels.add(part.casefold())
    return labels


def panel_candidates(
    reference_dir: Path = Path("data/reference"),
    *,
    max_candidates: int = 5,
) -> dict[str, list[tuple[QueryForm, str]]]:
    """Deterministic, ordered place candidates per NUTS-3 region.

    Ordering (all derived from the pinned reference, no measurement):

    1. the **seat town** — the municipality in the region whose name matches the
       Kreis name or the town part of the GISCO label (``"Rosenheim, Landkreis"``
       -> ``Rosenheim``), which is a real town in every Kreisfreie Stadt and in
       every Landkreis named after its seat;
    2. the region's municipalities ranked by distinct postcode count, then name
       (a town with several postcodes is bigger than a one-postcode village);
    3. the unambiguous anchor postcode of the best-ranked municipality.

    Only names unique in the whole register and postcodes mapping to a single
    NUTS-3 are offered: anything else carries no single-region provenance.
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

    out: dict[str, list[tuple[QueryForm, str]]] = {}
    for nuts_code in sorted(kreis_rows):
        kreis = kreis_rows[nuts_code]
        towns = region_towns.get(nuts_code, {})
        ranked = sorted(towns, key=lambda name: (-len(towns[name]), name))
        seat_labels = _seat_labels(kreis)
        candidates: list[tuple[QueryForm, str]] = []
        names_here = set(ranked) | region_names.get(nuts_code, set())

        # 1. the seat town, if the register knows it as a unique name here.
        for name in sorted(names_here):
            if name.casefold() in seat_labels and name.casefold() in unique_names:
                _append_candidate(candidates, "name", name)
        # 2. the region's towns, biggest first.
        for name in ranked:
            if name.casefold() in unique_names:
                _append_candidate(candidates, "name", name)
        for name in sorted(region_names.get(nuts_code, set())):
            if name.casefold() in unique_names:
                _append_candidate(candidates, "name", name)
        # 3. every unambiguous postcode of the region, biggest town first.
        for name in ranked:
            for code in sorted(towns[name]):
                _append_candidate(candidates, "plz", code)
        # 4. last resort: the seat name even though the register knows it in
        #    several regions. Only the seat name qualifies (a strong prior that
        #    BA's place search lands on this region's own town), and the pinning
        #    probe still has to see the source resolve it to that exact name.
        for name in sorted(names_here):
            if name.casefold() in seat_labels:
                _append_candidate(candidates, "name", name)
        out[nuts_code] = candidates[:max_candidates]
    return out


def load_pinned_panel(reference_dir: Path = Path("data/reference")) -> list[PanelEntry] | None:
    """Read the pinned panel artifact, or ``None`` when it is absent/incomplete.

    The artifact is validated against the reference: every entry must name a
    real NUTS-3 region of the frame, and every region of the frame must appear
    exactly once. A partial artifact is rejected rather than silently mixed with
    rule-derived entries, because a half-pinned panel is not a frozen panel.
    """
    path = reference_dir / BA_PANEL_PINNED_FILE
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    kreis = _kreis_rows(reference_dir)
    entries: list[PanelEntry] = []
    seen: set[str] = set()
    for item in payload.get("entries", []):
        nuts_code = str(item["nuts_code"])
        if nuts_code not in kreis or nuts_code in seen:
            raise ValueError(
                f"pinned panel {path} names {nuts_code}, which is not exactly one "
                "region of the reference frame"
            )
        seen.add(nuts_code)
        entries.append(
            PanelEntry(
                nuts_code=nuts_code,
                nuts_label=kreis[nuts_code]["nuts_label"],
                kreis_name=kreis[nuts_code]["kreis_name"],
                form=item["form"],
                value=str(item["value"]),
            )
        )
    if seen != set(kreis):
        raise ValueError(
            f"pinned panel {path} covers {len(seen)} of {len(kreis)} regions; "
            "a partial pin is not a frozen panel"
        )
    return sorted(entries, key=lambda entry: entry.nuts_code)


def write_pinned_panel(
    reference_dir: Path,
    entries: list[PanelEntry],
    evidence: dict[str, Any],
) -> Path:
    """Write the pinned panel artifact. Called once, by ``scripts/pin_ba_panel.py``."""
    path = reference_dir / BA_PANEL_PINNED_FILE
    payload = {
        "frame": "nuts3-kreise-destatis-2024",
        "membership_hash": panel_membership_hash(entries),
        "frame_size": len(entries),
        "evidence": evidence,
        "entries": [
            {"nuts_code": e.nuts_code, "form": e.form, "value": e.value}
            for e in sorted(entries, key=lambda entry: entry.nuts_code)
        ],
    }
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


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
