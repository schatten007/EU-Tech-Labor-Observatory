"""Release checks over the built dashboard page: accessibility, links, disclosure, no-JS.

Not part of `make check`: it inspects a build artefact rather than the source tree. Standard
library only, and it never opens a connection - external URLs are compared as strings against
an allowlist, never fetched.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from scripts.publish import METHODOLOGY_VERSION, ROOT, SECTIONS, SUPPRESSION_THRESHOLD, TARGET

# Documented source and licence hosts. Checked as strings; nothing here is requested.
ALLOWED_URL_PREFIXES = ("https://data.jobtechdev.se/", "http://data.europa.eu/esco/")
# The only elements the inline script is allowed to reveal, so `hidden` on anything else
# would mean server-rendered content that a reader without JavaScript never sees.
ENHANCEMENT_ATTRS = (
    "data-filters",
    "data-loading",
    "data-error",
    "data-csv",
    "data-filtered-empty",
)
COUNT_HEADERS = frozenset(
    {
        "postings",
        "advertised vacancies",
        "openings",
        "closures",
        "active postings",
        "active vacancies",
    }
)
# Only these two views mask small counts; see transform/macros/suppress_small_counts.sql.
MASKED_TABLES = frozenset({"table-survival-basis", "table-survival-flows"})
# Columns those views mask on another column's count, so publishing one while its keying count
# reads suppressed would republish the suppressed group.
DEPENDENT_COLUMNS = {
    "postings": ("advertised vacancies", "median days", "p25–p75 days", "max days"),
    "active postings": ("active vacancies",),
}
# Attributes that make a browser fetch something; `href` on a link is handled separately.
ASSET_ATTRS = ("src", "srcset", "data", "poster", "action", "formaction", "background")
HEADINGS = {f"h{level}": level for level in range(1, 7)}
CONTROLS = ("input", "select", "textarea")
SECRET = re.compile(r"\b[0-9a-f]{32,}\b", re.IGNORECASE)
EMAIL = re.compile(r"[^\s<>@]+@[^\s<>@]+\.[a-z]{2,}", re.IGNORECASE)
NUMBER = re.compile(r"^-?\d[\d,]*(\.\d+)?$")
BLANK = re.compile(r"\s+")


@dataclass
class Table:
    """Just enough of one rendered table to answer the caption, header, and cell questions."""

    identifier: str
    caption: bool = False
    headers: list[str] = field(default_factory=list)
    unscoped: int = 0
    fallbacks: int = 0
    body: list[list[str]] = field(default_factory=list)


class Page(HTMLParser):
    """Collect the structure the release rules need, then let check_page judge it."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self.version = ""
        self.noscript = False
        self.ids: list[str] = []
        self.headings: list[int] = []
        self.hrefs: list[str] = []
        self.assets: list[str] = []
        self.labelled: set[str] = set()
        self.controls: list[tuple[str, str, str, bool]] = []
        self.images: list[str | None] = []
        self.figures: list[str] = []
        self.hidden: list[str] = []
        self.tables: list[Table] = []
        self.text: list[str] = []
        self.attributes: list[str] = []
        self._quiet = 0
        self._label = 0
        self._table: Table | None = None
        self._head = False
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        self.attributes.extend(values.values())
        if tag in {"script", "style"}:
            self._quiet += 1
        if tag == "html":
            self.lang = values.get("lang", "")
            self.version = values.get("data-methodology-version", "")
        if "id" in values:
            self.ids.append(values["id"])
        if "hidden" in values and not any(attr in values for attr in ENHANCEMENT_ATTRS):
            self.hidden.append(tag)
        if tag in HEADINGS:
            self.headings.append(HEADINGS[tag])
        if tag == "a":
            self.hrefs.append(values.get("href", ""))
        if tag == "noscript":
            self.noscript = True
        if tag == "link" and values.get("rel") == "stylesheet":
            self.assets.append(values.get("href", ""))
        self.assets.extend(
            values[attr]
            for attr in ASSET_ATTRS
            if values.get(attr) and not values[attr].startswith("data:")
        )
        if tag == "img":
            self.images.append(values.get("alt"))
        if tag == "svg" and values.get("role") == "img":
            self.figures.append(values.get("aria-label", ""))
        if tag == "label":
            self._label += 1
            if values.get("for"):
                self.labelled.add(values["for"])
        if tag in CONTROLS:
            self.controls.append(
                (tag, values.get("id", ""), values.get("aria-label", ""), bool(self._label))
            )
        if tag == "table":
            self._table = Table(values.get("id", ""))
            self.tables.append(self._table)
        if tag == "caption" and self._table:
            self._table.caption = True
        if tag == "thead":
            self._head = True
        if tag == "tr":
            self._row = None
            if self._table and not self._head:
                if "data-row" in values:
                    self._row = []
                    self._table.body.append(self._row)
                elif "data-filtered-empty" not in values:
                    self._table.fallbacks += 1
        if tag in {"th", "td"}:
            self._cell = []
            if tag == "th" and self._head and self._table and "scope" not in values:
                self._table.unscoped += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self._quiet = max(self._quiet - 1, 0)
        if tag == "label":
            self._label = max(self._label - 1, 0)
        if tag in {"th", "td"} and self._cell is not None:
            text = BLANK.sub(" ", "".join(self._cell)).strip()
            if self._table and self._head and tag == "th":
                self._table.headers.append(text.lower())
            elif self._row is not None:
                self._row.append(text)
            self._cell = None
        if tag == "thead":
            self._head = False
        if tag == "table":
            self._table = None

    def handle_data(self, data: str) -> None:
        if self._quiet:
            return
        self.text.append(data)
        if self._cell is not None:
            self._cell.append(data)


def _small(value: str) -> bool:
    """True when a count cell publishes a group the suppression rule should have masked."""
    number = value.replace(",", "")
    return number.isdigit() and 0 < int(number) < SUPPRESSION_THRESHOLD


def _link_problem(href: str, ids: set[str]) -> str:
    if not href:
        return "empty href: an empty link points back at the page"
    if href.startswith("#"):
        return "" if href[1:] in ids else f"internal link {href} has no matching id"
    if href.startswith(("http://", "https://")):
        if href.startswith(ALLOWED_URL_PREFIXES):
            return ""
        return f"external link outside the documented allowlist: {href}"
    if href.startswith(("mailto:", "tel:")):
        return f"contact link published on an aggregate page: {href}"
    return f"relative link {href} cannot resolve in a single-file page"


def _masked_problems(table: Table) -> list[str]:
    """Suppression rules for one view that masks small counts, keyed by column header."""
    problems: list[str] = []
    counts = [header for header in table.headers if header in COUNT_HEADERS]
    if not counts:
        problems.append(
            f"table {table.identifier} has no recognised count column, so its suppression "
            "rule never ran"
        )
    for key, dependents in DEPENDENT_COLUMNS.items():
        if key in table.headers and not any(name in table.headers for name in dependents):
            problems.append(
                f"table {table.identifier} publishes {key} without any column masked with it, "
                "so the dependent-column rule never ran"
            )
    for cells in table.body:
        row = dict(zip(table.headers, cells, strict=False))
        problems.extend(
            f"table {table.identifier} publishes {row[header]} in the {header} column, "
            f"below the suppression threshold of {SUPPRESSION_THRESHOLD}"
            for header in counts
            if _small(row.get(header, ""))
        )
        for key, dependents in DEPENDENT_COLUMNS.items():
            if row.get(key) != "suppressed":
                continue
            problems.extend(
                f"table {table.identifier} publishes {row[name]} in the {name} column while its "
                f"{key} count is suppressed"
                for name in dependents
                if NUMBER.match(row.get(name, ""))
            )
    return problems


def check_page(html: str) -> list[str]:
    """Every release rule for the built page, as a flat list of human-readable problems."""
    page = Page()
    page.feed(html)
    ids = set(page.ids)
    text = BLANK.sub(" ", "".join(page.text))
    scanned = f"{text} {' '.join(page.attributes)}"
    problems: list[str] = []

    # Accessibility.
    if not page.lang:
        problems.append("the html element has no lang attribute")
    if page.headings.count(1) != 1:
        problems.append(f"expected exactly one h1, found {page.headings.count(1)}")
    for previous, level in zip(page.headings, page.headings[1:], strict=False):
        if level > previous + 1:
            problems.append(f"heading order skips from h{previous} to h{level}")
    for table in page.tables:
        name = table.identifier or "unnamed table"
        if not table.caption:
            problems.append(f"table {name} has no caption")
        if not table.headers:
            problems.append(f"table {name} has no column headers")
        if table.unscoped:
            problems.append(f"table {name} has {table.unscoped} header cell(s) without scope")
        if not table.body and not table.fallbacks:
            problems.append(f"table {name} renders no rows, not even an empty state")
    for tag, identifier, label, wrapped in page.controls:
        if not label and not wrapped and identifier not in page.labelled:
            problems.append(f"{tag} control {identifier or '(no id)'} has no label")
    if any(alt is None for alt in page.images):
        problems.append("an img element has no alt attribute")
    for index, label in enumerate(page.figures):
        if not label:
            problems.append(f"chart {index + 1} has role=img but no aria-label")
    for identifier in sorted({value for value in page.ids if page.ids.count(value) > 1}):
        problems.append(f"id {identifier} is used more than once")

    # Links and assets: verified offline, never requested.
    for href in page.hrefs:
        problem = _link_problem(href, ids)
        if problem:
            problems.append(problem)
    problems.extend(f"external asset requested: {asset or '(empty src)'}" for asset in page.assets)

    # Aggregate disclosure risk. A renamed table or column would silently disable these rules,
    # so a masked view that is absent from the page is itself a problem.
    published = {table.identifier for table in page.tables}
    problems.extend(
        f"masked view {identifier} is missing from the page, so its suppression rule never ran"
        for identifier in sorted(MASKED_TABLES - published)
    )
    for table in page.tables:
        if table.identifier in MASKED_TABLES:
            problems.extend(_masked_problems(table))
    if SECRET.search(scanned):
        problems.append("a pseudonym or key-like token is rendered in the page text or attributes")
    if EMAIL.search(scanned):
        problems.append("an email address is rendered in the page text or attributes")
    if f"1 to {SUPPRESSION_THRESHOLD - 1}" not in text:
        problems.append(
            f"the page does not state the suppression rule as 1 to {SUPPRESSION_THRESHOLD - 1}"
        )

    # Readable without JavaScript, and traceable to a build.
    for slug, _heading in SECTIONS:
        if slug not in ids:
            problems.append(f"section {slug} is missing from the page")
    for tag in sorted(set(page.hidden)):
        problems.append(f"server-rendered {tag} element is hidden without JavaScript")
    if not page.noscript:
        problems.append("no noscript explanation for the JavaScript-only controls")
    if page.version != METHODOLOGY_VERSION:
        problems.append(
            f"page methodology version {page.version or '(missing)'} "
            f"does not match {METHODOLOGY_VERSION}"
        )
    return problems


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else TARGET
    if not target.exists():
        print(f"missing {target}: run make site first")
        return 1
    problems = check_page(target.read_text(encoding="utf-8"))
    for problem in problems:
        print(f"- {problem}")
    label = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"{'FAIL' if problems else 'ok'} {label}: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
