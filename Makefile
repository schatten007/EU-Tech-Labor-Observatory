.PHONY: check lint types test scrape scrape-cz scrape-adzuna scrape-adzuna-nl scrape-ft scrape-vdab scrape-nav scrape-finland scrape-ba-jobsuche scrape-ba-panel check-ba-panel reconcile reference-mpsv reference-ft reference-vdab reference-nav reference-finland reference-germany clean

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

# Wired to Increment 5: VDAB public job-search website (Belgium - Flanders).
# HTML surface only: the Vacature API v4 is blocked (partnership + signed
# agreement) and /api/vindeenjob/ is robots-disallowed, so neither is touched.
# Landing pages carry 28 tiles each and have no pagination, so coverage is
# breadth-based: the default 500-page budget walks one landing page per distinct
# Flemish postcode (~10 min at 1.2 s pacing), reaches all 22 Flemish NUTS 3
# arrondissements and clears the DoD's 5,000 rows. Add --max-pages N to shorten.
scrape-vdab:
	uv run --offline python main.py --source be --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 6: NAV stillings-feed (Norway). The feed is an append-only
# EVENT LOG, so a sweep is a window, never a snapshot: --since sets the
# If-Modified-Since backfill in days (omit it to resume the persisted cursor at
# data/state/nav_feed_cursor.json, which is what a daily poll should do), and
# --max-details caps the ad-detail requests. Honest runtime: pages are cheap
# (1,000 events each) but every detail is one paced request, so the default
# 1,500-detail budget is ~25 minutes at the 1 s floor and a 5,000-detail sweep is
# ~1.5 hours. Needs no credentials - it falls back to NAV's public token - but
# uses NAV_FEED_TOKEN from .env when a private consumer token exists.
scrape-nav:
	uv run --offline python main.py --source no --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 7: Työmarkkinatori / Job Market Finland jobposting search
# API (P67 via the KEHA Centre's Kipa platform). REQUIRES CREDENTIALS THIS LAB
# DOES NOT HOLD: a KEHA-issued TMT_KIPA_SUBSCRIPTION_KEY in .env *and* a
# KEHA-side IP opening on api.ahtp.fi (both Kipa hosts drop TCP 443 otherwise).
# Without the key the collector raises before opening a socket. The API has no
# pagination: one POST streams the whole PUBLISHED result set as NDJSON, so
# honest runtime is one paced request plus however long the body takes to read
# (minutes, not hours) - there is no per-page budget and --max-pages is rejected.
# Use --max-rows 100 for the smoke pull, --status ARCHIVED for the closed set,
# and --fresh to ignore the watermark in data/state/finland_tmt_cursor.json.
scrape-finland:
	uv run --offline python main.py --source fi --date $(shell date -u +%Y-%m-%d)

# Wired to the Germany active lane (step 2): BA Jobsuche public website.
# SSR HTML search pages (Angular) at 1 s pacing; the internal REST API
# (rest.arbeitsagentur.de) is WAF-403 even from a browser, so the collector is
# an HTML parser, not an API client. Honest runtime: ~1 s per page; a 200-page
# sweep (~2,000 postings at ~10/page, less with dedupe) is ~5 minutes.
scrape-ba-jobsuche:
	uv run --offline python main.py --source ba --date $(shell date -u +%Y-%m-%d)

# Wired to Increment 9 (Germany, step 2): BA Jobsuche segmented regional census.
# Walks the resumable frontier (data/state/ba_segment_frontier.json) instead of
# one unscoped window: every Bundesland (probed), every municipality/PLZ segment
# walked to completeness, truncated metros subdivided into PLZ/recency children.
# Honest runtime: ~1 s per page, so a small municipality is ~2 pages and the
# full ~10,500-segment census is many hours; run in bounded resumable chunks
# with --max-segments N (checked BETWEEN segments, never mid-segment). Default
# resumes pending segments; use --fresh to rebuild the frontier. --umkreis 0
# (default) keeps Tier-3 provenance mapped; a radius downgrades Tier 3.
scrape-ba-segmented:
	uv run --offline python main.py --source ba --segmented --date $(shell date -u +%Y-%m-%d)

# NOT part of check. Rebuilds the pinned German PLZ/Stadt -> NUTS 2024 crosswalk
# (destatis Kreise AGS->NUTS official key x BKG VZ250_GEM municipality register
# x destatis Anschriftenverzeichnis Zustell-PLZ, validated against Eurostat
# GISCO NUTS 2024; opt-in network, no credentials). Downloads are cached under
# data/reference/.cache. The CSV is committed for the offline gate.
reference-germany:
	uv run --offline python -m scrapers.reference_germany

# NOT part of check. Increment 9 DoD proof (plan §9): loads every partition
# under ba/de-stock-segmented, reconciles the manifests, and asserts the
# app-derived thresholds (mapped share >=85%, >=390/400 NUTS 3 with >=1 mapped
# posting, unmapped <=5%). Run after the segmented census chunks; fails loudly
# if the DE slice is not push-ready.
check-ba-segmented:
	uv run --offline python scripts/check_ba_segmented_readiness.py

# Wired to Increment 9, Germany step 2b: the frozen NUTS-3 panel
# (scope de-nuts3-panel). One pinned place query per NUTS-3 region, capped at 4
# pages x 25 items, ~1,600 requests ~= 30 min at the 1 s pacing floor. The query
# set is a pure function of the pinned crosswalk, so it is byte-identical across
# sweeps: designed for WEEKLY re-sweep (survival resolution can never be finer
# than the sweep interval, and postings live ~30 days). Redirect the output to a
# log; never stream a 30-minute sweep into a session.
#   make scrape-ba-panel *> logs/ba-panel-sweep1.log      (PowerShell)
scrape-ba-panel:
	uv run --offline python main.py --source ba --panel --date $(shell date -u +%Y-%m-%d)

# NOT part of check. Asserts the step-2b Definition of Done across ALL panel
# partitions and prints one line per assertion: manifest reconciliation,
# >=390/400 NUTS-3 breadth per sweep, one membership hash across sweeps equal to
# the pinned definition, zero failed requests, clean PII scan, and the page cap
# declared in both scope_json and coverage_limitations.
check-ba-panel:
	uv run --offline python scripts/check_ba_panel_readiness.py

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

# NOT part of check. Rebuilds the pinned VDAB postcode -> NUTS 2024 crosswalk
# (Basisregisters Vlaanderen postinfo/{postcode}.nuts3 x Eurostat GISCO NUTS
# 2024; opt-in network, no credentials). Walks 529 Flemish postcodes at the 1 s
# charter floor: ~9 minutes. Restartable - an interrupted run resumes from the
# partial CSV; use --fresh to start over. The CSV is committed for the gate.
reference-vdab:
	uv run --offline python -m scrapers.reference_vdab

# NOT part of check. Rebuilds the pinned NAV fylke/kommune -> NUTS 2024 crosswalk
# (SSB Klass 104 fylker + 131 kommuner x Eurostat GISCO NUTS 2024; opt-in
# network, no credentials). Only 3 requests, so it finishes in seconds and needs
# no resume state. The CSV is committed for the offline gate.
reference-nav:
	uv run --offline python -m scrapers.reference_nav

# NOT part of check. Rebuilds the pinned Finnish kunta/maakunta -> NUTS 2024
# crosswalk (Statistics Finland classification keys kunta#nuts and kunta#maakunta
# x Eurostat GISCO NUTS 2024; opt-in network, no credentials). Only 3 requests,
# so it finishes in seconds and needs no resume state. Työmarkkinatori's OWN
# KUNTA/MAAKUNTA codesets are deliberately NOT used: tyomarkkinatori.fi/robots.txt
# disallows /api/, which is where they live. The CSV is committed for the gate.
reference-finland:
	uv run --offline python -m scrapers.reference_finland

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache
