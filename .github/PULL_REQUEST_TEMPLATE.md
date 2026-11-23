## Summary

<!-- Briefly describe what this PR changes and why. Link any related issue: Closes #123 -->

## Type of Change

- [ ] Bug fix (`fix:`)
- [ ] New feature (`feat:`)
- [ ] Radio hardware profile / channel template addition
- [ ] Security hardening (`security:`)
- [ ] Refactor / performance (`refactor:` / `perf:`)
- [ ] Documentation / tests / CI (`docs:` / `test:` / `ci:`)

## Verification

- [ ] `uv run poe lint` passes with zero errors
- [ ] `uv run poe test` passes (and new/updated unit tests are included)
- [ ] If UI changed: verified offline behavior (no external CDNs), theme tokens, and Playwright E2E/WCAG (`uv run --group dev --group ui poe ui-test`)
- [ ] If radio/exporter changed: verified exported CSV structure

## Contributor License Agreement (CLA)

- [ ] I have read [CONTRIBUTING.md](CONTRIBUTING.md) and agree to the [Contributor License Agreement (CLA.md)](CLA.md) *(first-time contributors: reply to the CLA bot comment with `I have read the CLA Document and I hereby sign the CLA`)*.
