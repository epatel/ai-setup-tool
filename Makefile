BIN ?= $(HOME)/.local/bin

.PHONY: help setup test lint format link

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

link: ## Link this checkout's ast into ~/.local/bin (override with BIN=dir)
	@test -x .venv/bin/ast || uv sync
	@mkdir -p "$(BIN)"
	@if [ -e "$(BIN)/ast" ] && [ ! -L "$(BIN)/ast" ]; then echo "$(BIN)/ast exists and is not a link; not replacing it" >&2; exit 1; fi
	@ln -sfn "$(CURDIR)/.venv/bin/ast" "$(BIN)/ast"
	@echo "$(BIN)/ast -> $(CURDIR)/.venv/bin/ast"
	@case ":$$PATH:" in *":$(BIN):"*) ;; *) echo "note: $(BIN) is not on your PATH";; esac
