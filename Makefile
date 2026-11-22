SHELL := bash

BIN ?= $(HOME)/.local/bin

info: menu select

menu:
	echo "1 make setup                - create .venv and install dependencies (uv sync)"
	echo "2 make test                 - run all tests (one file or test: make test T=tests/test_org.py)"
	echo "3 make lint                 - check the code with ruff"
	echo "4 make format               - format the code with ruff"
	echo "5 make check                - lint + tests; run before committing"
	echo "6 make link                 - link this checkout's ast into ~/.local/bin (BIN=dir to change)"
	echo "7 make unlink               - remove that link"
	echo "8 make status               - ast status for this repo's own agent tools"
	echo "9 make update               - update this repo's own agent tools (ast update)"
	echo "10 make build               - build the wheel and sdist into dist/"
	echo "11 make clean               - remove dist/ and caches (keeps .venv)"
	echo "12 make update_phony        - update .PHONY in Makefile"

select:
	read -p ">>> " P ; "$(MAKE)" --no-print-directory menu | grep "^$$P " | cut -d ' ' -f2-3 | bash

.SILENT:

.PHONY: info menu select help setup test lint format check link unlink status update build clean update_phony 

help: menu

setup:
	uv sync

test:
	uv run pytest -q $(T)

lint:
	uv run ruff check .

format:
	uv run ruff format .

check: lint test

link:
	test -x .venv/bin/ast || uv sync
	mkdir -p "$(BIN)"
	if [ -e "$(BIN)/ast" ] && [ ! -L "$(BIN)/ast" ]; then echo "$(BIN)/ast exists and is not a link; not replacing it" >&2; exit 1; fi
	ln -sfn "$(CURDIR)/.venv/bin/ast" "$(BIN)/ast"
	echo "$(BIN)/ast -> $(CURDIR)/.venv/bin/ast"
	case ":$$PATH:" in *":$(BIN):"*) ;; *) echo "note: $(BIN) is not on your PATH";; esac

unlink:
	if [ -L "$(BIN)/ast" ]; then rm "$(BIN)/ast" && echo "removed $(BIN)/ast"; else echo "$(BIN)/ast is not a link; nothing removed"; fi

status:
	uv run ast status

update:
	uv run ast update

build:
	uv build

clean:
	rm -rf dist .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -not -path "./.venv/*" -prune -exec rm -rf {} +

update_phony:
	echo "##### Updating .PHONY targets #####"
	targets=$$(grep -E '^[a-zA-Z_][a-zA-Z0-9_-]*:' Makefile | grep -v '=' | cut -d: -f1 | tr '\n' ' '); \
	sed -i.bak "s/^\.PHONY:.*/.PHONY: $$targets/" Makefile && \
	echo "Updated .PHONY: $$targets" && \
	rm -f Makefile.bak
