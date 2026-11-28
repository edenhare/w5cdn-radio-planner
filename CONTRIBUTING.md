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

- **Add a Radio Hardware Profile**: Add a YAML spec under `src/electron/resources/radios/` with verified `maxChannels`, `maxNameLength`, `startChannel`, `supportedBands`, `supportedModes`, `allowedSpecialChars`, and exporter `columns`.
- **Add or Refine Channel Templates**: Add YAML templates under `src/electron/resources/templates/` (e.g., regional simplex, tactical, or service bands).
- **Fix Bugs or Build Features**: Open an issue first for larger changes so we can align on design before you invest time.
- **Improve Documentation & Tests**: Clarify docs, expand Vitest and Playwright E2E tests (Good / Bad / Offline data), or verify real hardware imports in CHIRP / RT Systems.

---

## 3. Development Environment Setup

Requires **Node.js 22+ LTS** (includes `npm`):

```bash
# 1. Fork the repository on GitHub and clone your fork
git clone https://github.com/<your-username>/w5cdn-radio-planner.git
cd w5cdn-radio-planner

# 2. Install dependencies
npm install

# 3. Create a topic branch from main
git checkout -b feat/my-change
```

Optional Playwright browser setup for E2E testing:
```bash
npx playwright install chromium
```

---

## 4. Coding Standards & Project Guardrails

All Pull Requests must pass CI across Ubuntu & Windows (Node.js 22 LTS). Keep these rules in mind:

1. **Offline-First Cockpit UI**: Never introduce external CDN `<script>`, `<link>`, or font URLs in `src/static/index.html` or `src/static/styles.css`. All UI assets must work with zero internet access.
2. **Theme Token Hygiene**: Do not hardcode hex/rgb colors outside `:root[data-theme="..."]` blocks in `src/static/styles.css`. All 9 themes must remain readable and accessible.
3. **Strict TypeScript & Schema Validation**: Preserve strict TypeScript types (`npm run typecheck`) and line/column YAML schema diagnostics (`src/electron/shared/yamlDiagnostics.ts`).
4. **Security by Default**: Preserve `safeChildPath()` traversal guards, `csvSafeCell()` formula neutralization, Zip-Slip archive validation, and Electron `contextIsolation: true` / `sandbox: true`.
5. **Cross-Platform Line Endings**: Keep Linux shell scripts (`start.sh`, `scripts/install_linux_desktop.sh`) strictly LF (`\n`), enforced by `tests/electron/ui_integrity.test.ts` and Husky Git hooks.
6. **Coverage & Smoke Verification**: Include Vitest tests for new behavior (Good, Bad, and Missing/Offline cases) and verify the Electron desktop smoke test passes.

---

## 5. Running Checks Locally

Run the full quality gate before pushing:

```bash
# Verify version consistency across package.json & UI assets
npm run version:check

# TypeScript strict type checking
npm run typecheck

# Vitest unit, router, provider & UI integrity tests with V8 coverage
npm run test:cov

# Live Electron GUI + in-process API smoke test
npm run smoke

# Playwright real-browser Chromium E2E test suite
npm run test:e2e
```

---

## 6. Commit Messages & Pull Request Workflow

Use [Conventional Commits](https://www.conventionalcommits.org/) so `scripts/generate-changelog.mjs` categorizes release notes automatically:

- `feat(radios): add Yaesu FTM-300DR hardware profile`
- `fix(chirp): handle split offset edge case on 10m repeaters`
- `security(backup): tighten backup archive entry validation`
- `docs(readme): clarify Linux desktop launcher setup`
- `test(providers): add offline fallback tests for geocoding`

### Opening a PR
1. Push your branch to your fork and open a Pull Request targeting **`main`**.
2. Fill out the PR checklist in the template.
3. Sign the CLA by commenting `I have read the CLA Document and I hereby sign the CLA` when prompted.
4. Wait for all required CI checks (`Required PR Merge Gate`, `CodeQL`, and `CLA Assistant`) to pass.

---

## 7. Security Issues

If you discover a security vulnerability (e.g., XSS, path traversal, CSV injection, or unsafe archive extraction), please **do not** open a public issue with exploit details. Report it privately via GitHub Security Advisories on the repository so it can be patched responsibly.
