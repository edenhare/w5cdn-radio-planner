# Contributing to W5CDN RadioPlanner

Thank you for your interest in improving **W5CDN RadioPlanner**! Contributions of all sizes—from new radio hardware YAML specs and channel templates to bug fixes, documentation, and features—are welcome.

---

## 1. Licensing, Ownership & Contributor License Agreement (CLA)

- **Project License**: W5CDN RadioPlanner is licensed under the **GNU General Public License v3.0 (GPL-3.0)** — see [LICENSE](LICENSE).
- **Project Ownership**: Copyright © 2026 **Eden Hare (W5CDN)**.
- **CLA Required for External PRs**: Before any external Pull Request can be merged, contributors must sign our lightweight [Contributor License Agreement (CLA.md)](CLA.md).
  - You keep copyright and attribution for your work while granting the Project Owner full rights to distribute and re-license contributions as the project evolves.
  - When you open your first PR, the **CLA Assistant** workflow will prompt you to reply with:
    ```text
    I have read the CLA Document and I hereby sign the CLA
    ```
  - You only need to sign once per GitHub account.

---

## 2. Ways to Contribute

- **Add a Radio Hardware Profile**: Add a YAML spec under `src/core/resources/radios/` with verified `maxChannels`, `maxNameLength`, `startChannel`, `supportedBands`, `supportedModes`, `allowedSpecialChars`, and exporter `columns`.
- **Add or Refine Channel Templates**: Add YAML templates under `src/core/resources/templates/` (e.g., regional simplex, tactical, or service bands).
- **Fix Bugs or Build Features**: Open an issue first for larger changes so we can align on design before you invest time.
- **Improve Documentation & Tests**: Clarify docs, expand tri-state tests (Good / Bad / Offline data), or verify real hardware imports in CHIRP / RT Systems.

---

## 3. Development Environment Setup

Requires **Python 3.11+** and [`uv`](https://docs.astral.sh/uv/):

```bash
# 1. Fork the repository on GitHub and clone your fork
git clone https://github.com/<your-username>/w5cdn-radio-planner.git
cd w5cdn-radio-planner

# 2. Install runtime + dev dependencies
uv sync --group dev

# 3. Create a topic branch from main
git checkout -b feat/my-change
```

Optional dependency groups:
```bash
# Playwright E2E + axe-core WCAG 2.1 AA testing
uv sync --group dev --group ui
uv run --group dev --group ui playwright install chromium

# PyInstaller standalone packaging
uv sync --group packaging
```

---

## 4. Coding Standards & Project Guardrails

All Pull Requests must pass CI across Ubuntu & Windows (Python 3.11 & 3.12). Keep these rules in mind:

1. **Offline-First Cockpit UI**: Never introduce external CDN `<script>`, `<link>`, or font URLs in `src/web/static/index.html` or `styles.css`. All UI assets must work with zero internet access.
2. **Theme Token Hygiene**: Do not hardcode hex/rgb colors outside `:root[data-theme="..."]` blocks in `src/web/static/styles.css`. All 9 themes must remain WCAG 2.1 AA compliant.
3. **No Bare or Overly Broad Exceptions**: Web, desktop, updater, and provider modules must catch specific exception types (enforced by `tests/test_code_quality.py`).
4. **Security by Default**: Preserve localhost Host/Origin validation, `safe_child_path()` traversal guards, `csv_safe_cell()` formula neutralization, and XXE-safe XML parsing.
5. **Cross-Platform Line Endings**: Keep Linux shell scripts (`start.sh`, `scripts/install_linux_desktop.sh`) strictly LF (`\n`), enforced by `tests/web/test_ui_integrity.py`.
6. **Coverage Gate**: Maintain at least **75%** total test coverage (`--cov-fail-under=75`) and include tests for new behavior (Good, Bad, and Missing/Offline cases).

---

## 5. Running Checks Locally

Run the full quality gate before pushing:

```bash
# Linter & formatter
uv run poe lint
uv run poe format

# Unit, API, security, AST quality & static UI integrity tests
uv run poe test

# Full check (lint + test)
uv run poe check

# Coverage report (CI requires >= 75%)
uv run poe test-cov

# Playwright real-browser E2E & WCAG 2.1 AA tests (optional locally, required in CI)
uv run --group dev --group ui poe ui-test
```

---

## 6. Commit Messages & Pull Request Workflow

Use [Conventional Commits](https://www.conventionalcommits.org/) so `scripts/generate_changelog.py` categorizes release notes automatically:

- `feat(radios): add Yaesu FTM-300DR hardware profile`
- `fix(chirp): handle split offset edge case on 10m repeaters`
- `security(web): tighten backup archive entry validation`
- `docs(readme): clarify Linux desktop launcher setup`
- `test(core): add offline fallback tests for geocoding`

### Opening a PR
1. Push your branch to your fork and open a Pull Request targeting **`main`**.
2. Fill out the PR checklist in the template.
3. Sign the CLA by commenting `I have read the CLA Document and I hereby sign the CLA` when prompted.
4. Wait for all required CI checks (`Required PR Merge Gate`, `CodeQL`, and `CLA Assistant`) to pass and for maintainer review. All merges into `main` require maintainer approval.

---

## 7. Security Issues

If you discover a security vulnerability (e.g., XSS, path traversal, CSV injection, unsafe archive extraction, or localhost CSRF bypass), please **do not** open a public issue with exploit details. Report it privately via GitHub Security Advisories on the repository so it can be patched responsibly.
