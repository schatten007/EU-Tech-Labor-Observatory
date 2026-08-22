.PHONY: check lint types test scrape scrape-cz scrape-adzuna scrape-adzuna-nl scrape-ft reconcile reference-mpsv reference-ft clean

check: lint types test

lint:
	uv run --offline ruff check .
	uv run --offline ruff format --check .

types:
	uv run --offline mypy .

test:
	uv run --offline python -m pytest

# Wired to Increment 1: CBOP/ePraca Poland (all active offers).
scrape:
	uv run --offline python main.py --source pl --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 2: Úřad práce / MPSV Czechia (daily active-set dump).
scrape-cz:
	uv run --offline python main.py --source cz --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 3: Adzuna Germany (all active listings, free-tier budget).
# Free tier caps at 250 hits/day; the collector's default page budget (240
# pages x 50) keeps a plain sweep inside the daily quota.
scrape-adzuna:
	uv run --offline python main.py --source adzuna --country de --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 3: Adzuna Netherlands via the same collector (config only).
scrape-adzuna-nl:
	uv run --offline python main.py --source adzuna --country nl --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 4: France Travail Offres d'emploi v2 (all active offers).
# One query caps at 3,150 offers (window <=150, start <=3000), so the sweep runs
# one query per departement (101) plus one unsegmented query, deduped on HMAC
# source_id. Full segmentation is ~2.1k windows at the charter's 1 s pacing;
# add --max-pages N for a shorter budgeted sweep (N windows x 150 offers).
scrape-ft:
	uv run --offline python main.py --source ft --date $(shell date -u +%Y-%m-%d)

# NOT part of check. Stamps removed_at on postings closed between the two most
# recent MPSV sweeps (compares HMAC source_ids only; writes closures.ndjson).
reconcile:
	uv run --offline python -m scrapers.reconcile_mpsv

# NOT part of check. Rebuilds the pinned MPSV codelist -> NUTS 2024 crosswalk
# from data.mpsv.cz (opt-in network; the CSVs are committed for the offline gate).
reference-mpsv:
	uv run --offline python -m scrapers.reference_mpsv

# NOT part of check. Rebuilds the pinned France Travail departement -> NUTS 2024
# crosswalk (FT referentiel/departements x Eurostat GISCO NUTS 2024; opt-in
# network, needs FRANCE_TRAVAIL_* credentials; the CSV is committed).
reference-ft:
	uv run --offline python -m scrapers.reference_francetravail

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache
