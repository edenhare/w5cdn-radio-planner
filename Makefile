.PHONY: default install test test-cov ui-test lint format check run desktop build

default:
	@echo "Available targets: install, test, test-cov, ui-test, lint, format, check, run, desktop, build"

install:
	uv sync

test:
	uv run poe test

test-cov:
	uv run poe test-cov

ui-test:
	uv run --group dev --group ui poe ui-test

lint:
	uv run poe lint

format:
	uv run poe format

check:
	uv run poe check

run:
	uv run poe run

desktop:
	uv run poe desktop

build:
	uv run --group packaging poe build
