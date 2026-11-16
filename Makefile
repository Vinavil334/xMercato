.PHONY: install check test lint format

install:
	uv sync --extra dev

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format . && uv run ruff check --fix .

test:
	uv run pytest -q

check: lint test
