.PHONY: help setup test lint format

help: ## List targets
	@grep -E "^[a-z-]+:.*##" $(MAKEFILE_LIST) | sed -E "s/:.*## /\t/"

setup: ## Create .venv/ and install dependencies
	uv sync

test: ## Run all tests (one test: uv run pytest tests/test_org.py -k selects)
	uv run pytest -q

lint: ## Check code with ruff
	uv run ruff check .

format: ## Format code with ruff
	uv run ruff format .
