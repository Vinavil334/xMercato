.PHONY: install check test lint format app

install:
	uv sync --extra dev

lint:
	uv run ruff check . && uv run ruff format --check .

format:
	uv run ruff format . && uv run ruff check --fix .

test:
	uv run pytest -q

check: lint test

app:
	uv run streamlit run app/streamlit_app.py
