# make check is THE gate. It must stay fully offline: synthetic rows are the test basis
# and the API-quota firewall. If this target ever touches the network, an agent will
# route around it and the whole verification story collapses.
# Never edit this target to make it pass.

export DBT_PROFILES_DIR := transform
DBT := uv run --offline dbt

# .env holds only OBSERVATORY_HMAC_KEY, and only the networked collector loads it. Never wire
# it into check: a data path or reference time from a file would stop the gate testing the
# synthetic sample. The flag is conditional so a clone without .env still works.
UV_LIVE := uv run $(if $(wildcard .env),--env-file .env,)

# Lazy on purpose: this runs only when live-site expands REFERENCE_TIME. An exported
# OBSERVATORY_REFERENCE_TIME still wins, but python reads and shape-checks it, so the value never
# passes through a shell. Python, not powershell, because recipes run under cmd.exe when make is
# started from PowerShell and under sh when it is started from Git Bash.
STAMP = $(shell uv run --offline python -c "import datetime,os,re;t=os.environ.get('OBSERVATORY_REFERENCE_TIME') or datetime.datetime.now(datetime.UTC).isoformat(timespec='seconds').replace('+00:00','Z');print(t if re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z',t) else '')")

# Fail closed, because the silent path is the dangerous one: an empty stamp would let dbt fall back
# to its sample default and publish a live sweep as fresh with a negative age.
REFERENCE_TIME = $(or $(STAMP),$(error could not resolve a valid UTC OBSERVATORY_REFERENCE_TIME; expected yyyy-mm-ddThh:mm:ssZ))

# Expanded only inside the live-site recipe, so check and site never pay for the glob.
# Every collector, not just jobtech: the leading wildcard is the source segment, so a new collector
# is published by storing a partition and needs no Makefile edit. The depth stays exactly three
# segments (source/scope_id/sweep_id) because that is the stored shape; widening the depth instead
# would match nested paths and silently double-count a sweep. The count printed by live-site must
# equal the per-source counts summed - if it does not, the glob is wrong, not the count.
LIVE_SWEEPS = $(wildcard data/raw/collections/*/*/*/manifest.json)
LIVE_READY = $(if $(LIVE_SWEEPS),$(words $(LIVE_SWEEPS)),$(error no stored sweeps found; run make sweep before make live-site))

.PHONY: check lint types test evaluate dbt sample site release-check probe sweep sweep-datait sweep-all reference live-site export-app clean

check: lint types test evaluate dbt

lint:
	uv run --offline ruff check .
	uv run --offline ruff format --check .

types:
	uv run --offline mypy .

test:
	uv run --offline python -m pytest

evaluate:
	uv run --offline python -m scripts.evaluate

dbt:
	$(DBT) parse --project-dir transform
	$(DBT) build --project-dir transform

# Offline: rebuilds the committed sample from synthetic rows.
sample:
	uv run --offline python -m scripts.probe --sample

# Offline: builds one static aggregate page from the local DuckDB models.
site: dbt
	uv run --offline python -m scripts.publish

# NOT part of check: it inspects a build artefact. Offline; external URLs are never fetched.
release-check: site
	uv run --offline python -m scripts.release_check

# NOT part of check. Hits live APIs. Main checkout only, never a worktree.
probe:
	uv run python -m scripts.probe --live

# NOT part of check. Collects one complete canonical JobTech keyword sweep.
sweep:
	$(UV_LIVE) python -m scripts.collect sweep

# The id is read back from the collector rather than repeated here: a copy that drifted would
# still collect happily, just under a third scope nobody meant to open. Lazy, so only a live
# sweep pays for the call. An empty value makes argparse refuse the run instead of widening it.
JOBTECH_DATA_IT_FIELD = $(shell uv run --offline python -c "from scripts.collect import JOBTECH_DATA_IT_FIELD as field;print(field)")

# NOT part of check. The second scope: JobTech's own Data/IT occupation field, ~26 pages.
sweep-datait:
	$(UV_LIVE) python -m scripts.collect sweep --occupation-field $(JOBTECH_DATA_IT_FIELD)

# Both scopes, serially (do not run this under -j; two live sweeps would race the same API).
# Never retire a scope: an abandoned scope's postings can never be closed and render forever.
sweep-all: sweep sweep-datait

# NOT part of check. Rebuilds pinned reference crosswalks from the JobTech Taxonomy API.
reference:
	uv run python -m scripts.build_reference

# Offline preview of final, immutable live partitions only. This does not collect data.
# All stored sources are read, not jobtech alone, and the depth is pinned to three segments for the
# reason given above LIVE_SWEEPS. Publishing more than one scope is a separate concern: the page
# still verifies its own scope assumptions, so a second scope is expected to fail publish loudly
# rather than be summed into one ranking.
# tag:sample_fixture is excluded because those tests are exact assertions about the synthetic
# sample (its zero-row sweep, its stale scope, its closure and key-rotation timeline): on live
# partitions they cannot fire, so running them would only claim coverage they do not give. Every
# untagged test still runs here, including coverage, freshness, grain, and suppression.
# make exports the paths itself instead of the recipe setting them, because `set "VAR=value" &&`
# is cmd.exe-only: under Git Bash's sh it sets positional parameters and silently leaves dbt
# reading the synthetic sample while the page claims to be live.
live-site: export OBSERVATIONS_PATH := data/raw/collections/*/*/*/observations.ndjson
live-site: export MANIFESTS_PATH := data/raw/collections/*/*/*/manifest.json
live-site: export OBSERVATORY_REFERENCE_TIME = $(REFERENCE_TIME)
live-site:
	@echo publishing from $(LIVE_READY) stored sweeps
	$(DBT) build --project-dir transform --exclude tag:sample_fixture
	uv run --offline python -m scripts.publish

# NOT part of check. Offline: rebuilds the live views exactly as live-site does, then writes
# app/data.json - the fresh app's entire world (Plan A v2). The app never computes a statistic:
# whatever is not in this export is not shown. Same paths, same glob depth and same reference
# time as live-site, so the export and the page can never describe different sweeps.
export-app: export OBSERVATIONS_PATH := data/raw/collections/*/*/*/observations.ndjson
export-app: export MANIFESTS_PATH := data/raw/collections/*/*/*/manifest.json
export-app: export OBSERVATORY_REFERENCE_TIME = $(REFERENCE_TIME)
export-app:
	@echo exporting from $(LIVE_READY) stored sweeps
	$(DBT) build --project-dir transform --exclude tag:sample_fixture
	uv run --offline python -m scripts.export_app_data

clean:
	$(DBT) clean --project-dir transform
	uv run --offline python -c "import shutil;[shutil.rmtree(p,ignore_errors=True) for p in ('.mypy_cache','.ruff_cache','.pytest_cache')]"
