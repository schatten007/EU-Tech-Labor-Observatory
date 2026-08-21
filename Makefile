.PHONY: check lint types test scrape clean

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

clean:
	rm -rf .mypy_cache .ruff_cache .pytest_cache
