# make check is THE gate. It must stay fully offline: synthetic rows are the test basis
# and the API-quota firewall. If this target ever touches the network, an agent will
# route around it and the whole verification story collapses.
# Never edit this target to make it pass.

export DBT_PROFILES_DIR := transform
DBT := uv run --offline dbt

.PHONY: check lint types test dbt sample site probe sweep live-site clean

check: lint types test dbt

lint:
	uv run --offline ruff check .
	uv run --offline ruff format --check .

types:
	uv run --offline mypy .

test:
	uv run --offline python -m pytest

dbt:
	$(DBT) parse --project-dir transform
	$(DBT) build --project-dir transform

# Offline: rebuilds the committed sample from synthetic rows.
sample:
	uv run --offline python -m scripts.probe --sample

# Offline: builds one static aggregate page from the local DuckDB models.
site: dbt
	uv run --offline python -m scripts.publish

# NOT part of check. Hits live APIs. Main checkout only, never a worktree.
probe:
	uv run python -m scripts.probe --live

# NOT part of check. Collects one complete canonical JobTech query sweep.
sweep:
	uv run python -m scripts.collect sweep

# Offline preview of final, immutable live partitions only. This does not collect data.
live-site:
	if not exist "data\raw\collections\jobtech" (echo Run make sweep before make live-site. & exit /b 1)
	if "$(OBSERVATORY_REFERENCE_TIME)"=="" (echo Set OBSERVATORY_REFERENCE_TIME to the current UTC timestamp. & exit /b 1)
	set "OBSERVATIONS_PATH=data/raw/collections/jobtech/*/*/observations.ndjson" && set "MANIFESTS_PATH=data/raw/collections/jobtech/*/*/manifest.json" && $(DBT) build --project-dir transform
	set "OBSERVATIONS_PATH=data/raw/collections/jobtech/*/*/observations.ndjson" && set "MANIFESTS_PATH=data/raw/collections/jobtech/*/*/manifest.json" && uv run --offline python -m scripts.publish

clean:
	$(DBT) clean
	rm -rf .mypy_cache .ruff_cache .pytest_cache
