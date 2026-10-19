# 6. Two-Stage Multi-Column Radio Hardware Selection

Date: 2026-10-19

## Status
Accepted

## Context
Target radio models were previously displayed in a single long flat list. As more radio models (Baofeng, BTECH, Wouxun, Alinco, Icom, Kenwood, AnyTone) and user custom profiles are added, flat lists become cumbersome to scan in a terminal.

## Decision
1. **Hierarchical Selection Flow**:
   - **Stage 1 (Brand Selection)**: Group registered radios by manufacturer Brand (e.g. Alinco, Baofeng, BTECH, Generic, Wouxun). Display them in a balanced multi-column Rich grid with numeric/letter selection indicators.
   - **Stage 2 (Model Selection)**: Once a brand is chosen, display all configured models for that brand in a multi-column grid showing model name, programmer format, max channels, and LCD limits.
2. **Back Navigation**:
   - The user can enter `B` to go back from Model selection to Brand selection, or `Q` to cancel.

## Consequences
- Clean, compact terminal presentation that scales naturally to dozens of radios without excessive vertical scrolling.
- Direct alignment with amateur radio operator expectations where manufacturer brand is the primary category.
