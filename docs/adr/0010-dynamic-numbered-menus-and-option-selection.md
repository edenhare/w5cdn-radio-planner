# 10. Dynamic Numbered Menus and Option Selection System

## Status
Accepted

## Context
Previously, several menus and options across the CLI wizard (Main Menu, User Preferences & Settings, Language selection, Color Theme selection) hardcoded their option sequence numbers (e.g. `[1]`, `[2]`, `[3]`, etc.), valid choice validation lists (`choices=["1", "2", ... "10"]`), and sequential branching (`elif choice == "1"`).
This manual hardcoding was brittle and error-prone: adding, removing, or reordering an option required manual renumbering of labels, updating prompt choices, and refactoring multiple branch conditions.

## Decision
1. **Dynamic Option Selection (`prompt_choice_from_list`):**
   - Provide a generic dynamic selection helper for lists of options (e.g., Languages, Color Themes, Hardware models, Recipes).
   - Generates sequence numbers dynamically (`1..N`) via `enumerate(items, start=1)`.
   - Derives valid prompt choice strings dynamically from the list bounds.
   - Maps user input directly by sequence index (`items[int(choice) - 1]`).
2. **Dynamic Numbered Menus (`MenuItem` and `PreferenceItem`):**
   - Define menu options as lists of objects containing a label, action handler, and optional explicit letter key (e.g. `key="0"` for Exit, `key="Q"` for Return).
   - Dynamically number sequence options starting at `1`.
   - Dynamically assemble the validation choice list and dispatch user selection to the item's handler.
   - Separate options with explicit keys (letters or special digits) from sequentially numbered options.

## Consequences
- Eliminates hardcoded numbering and duplicate sequence branching.
- Adding, reordering, or removing a preference or menu item requires only modifying a single declarative list entry.
- Maintains full support for explicit mnemonic letter keys (`Q`, `C`, `N`, `E`, etc.).
