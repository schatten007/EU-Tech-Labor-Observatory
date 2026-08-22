.PHONY: check lint types test scrape scrape-cz scrape-adzuna scrape-adzuna-nl reconcile reference-mpsv clean

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

# NOT part of check. Stamps removed_at on postings closed between the two most
# recent MPSV sweeps (compares HMAC source_ids only; writes closures.ndjson).
reconcile:
	uv run --offline python -m scrapers.reconcile_mpsv

# NOT part of check. Rebuilds the pinned MPSV codelist -> NUTS 2024 crosswalk
# from data.mpsv.cz (opt-in network; the CSVs are committed for the offline gate).
reference-mpsv:
	uv run --offline python -m scrapers.reference_mpsv

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache
