# Justfile for RadioPlanner
set shell := ["powershell.exe", "-NoProfile", "-Command"]

# Default recipe: list available recipes
default:
    @just --list

# Install dependencies using uv
install:
    uv sync

# Run tests
test:
    uv run poe test

# Run tests with coverage
test-cov:
    uv run poe test-cov

# Run linter
lint:
    uv run poe lint

# Format code
format:
    uv run poe format

# Run checks (lint + test)
check:
    uv run poe check

# Run Playwright UI E2E & WCAG accessibility tests
ui-test:
    uv run --group dev --group ui poe ui-test

# Run the RadioPlanner CLI / Cockpit entrypoint
run:
    uv run poe run

# Launch the standalone desktop window
desktop:
    uv run poe desktop

# Build portable standalone bundle (.zip)
build:
    uv run --group packaging poe build
