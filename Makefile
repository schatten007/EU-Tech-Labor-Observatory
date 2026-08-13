# make check is THE gate. It must stay fully offline: fixtures in tests/fixtures/ are
# simultaneously the test basis and the API-quota firewall. If this target ever touches
# the network, an agent will route around it and the whole verification story collapses.
# Never edit this target to make it pass.

export DBT_PROFILES_DIR := transform
DBT := uv run --offline dbt

.PHONY: check lint types test dbt sample probe clean

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

# Offline: rebuilds the committed sample from the committed fixtures.
sample:
	uv run python scripts/probe.py --sample

# NOT part of check. Hits live APIs. Main checkout only, never a worktree.
probe:
	uv run python scripts/probe.py --live

clean:
	$(DBT) clean
	rm -rf .mypy_cache .ruff_cache .pytest_cache
