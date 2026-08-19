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

# Lazy on purpose: this powershell call runs only when live-site expands REFERENCE_TIME. An
# exported OBSERVATORY_REFERENCE_TIME still wins, but it is read inside powershell and
# shape-checked there, so a malformed value never reaches the recipe. Failure prints nothing.
STAMP = $(shell powershell -NoProfile -Command "$$t = $$env:OBSERVATORY_REFERENCE_TIME; if (-not $$t) { $$t = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }; if ($$t -match '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$$') { $$t }")

# Fail closed, because the silent path is the dangerous one: an empty stamp reaches cmd.exe as
# set "VAR=", which UNSETS it, so dbt would fall back to its sample default and publish a live
# sweep as fresh with a negative age. $(or) expands STAMP once, so one powershell call.
REFERENCE_TIME = $(or $(STAMP),$(error could not resolve a valid UTC OBSERVATORY_REFERENCE_TIME; expected yyyy-mm-ddThh:mm:ssZ))

.PHONY: check lint types test evaluate dbt sample site release-check probe sweep reference live-site clean

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

# NOT part of check. Collects one complete canonical JobTech query sweep.
sweep:
	$(UV_LIVE) python -m scripts.collect sweep

# NOT part of check. Rebuilds pinned reference crosswalks from the JobTech Taxonomy API.
reference:
	uv run python -m scripts.build_reference

# Offline preview of final, immutable live partitions only. This does not collect data.
live-site:
	if not exist "data\raw\collections\jobtech" (echo Run make sweep before make live-site. & exit /b 1)
	set "OBSERVATORY_REFERENCE_TIME=$(REFERENCE_TIME)" && set "OBSERVATIONS_PATH=data/raw/collections/jobtech/*/*/observations.ndjson" && set "MANIFESTS_PATH=data/raw/collections/jobtech/*/*/manifest.json" && $(DBT) build --project-dir transform
	set "OBSERVATIONS_PATH=data/raw/collections/jobtech/*/*/observations.ndjson" && set "MANIFESTS_PATH=data/raw/collections/jobtech/*/*/manifest.json" && uv run --offline python -m scripts.publish

clean:
	$(DBT) clean
	rm -rf .mypy_cache .ruff_cache .pytest_cache
