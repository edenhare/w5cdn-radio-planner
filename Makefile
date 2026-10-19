.PHONY: default install test test-cov lint format check run

default:
	@echo "Available targets: install, test, test-cov, lint, format, check, run"

install:
	uv sync

test:
	uv run poe test

test-cov:
	uv run poe test-cov

lint:
	uv run poe lint

format:
	uv run poe format

check:
	uv run poe check

run:
	uv run poe run
