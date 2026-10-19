"""Dynamic numbered menu and list selection components for Rich CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Tuple, TypeVar

from rich.console import Console
from rich.prompt import Prompt

T = TypeVar("T")


@dataclass
class MenuItem:
    """An action item in a dynamic menu."""

    label: str
    action: Callable[[], Any]
    key: Optional[str] = None  # None for auto-numbering 1..N, or explicit letter/char (e.g. '0', 'Q')


@dataclass
class PreferenceItem:
    """A user preference setting in the preferences editor."""

    label: str
    get_value: Callable[[], str]
    edit_action: Callable[[], Any]


def prompt_choice_from_list(
    console: Console,
    title: str,
    options: List[Tuple[T, str]],  # (value, display_label)
    default_value: Optional[T] = None,
) -> T:
    """Dynamically display a numbered list of choices (1..N) and prompt user for selection."""
    console.print(f"\n[bold cyan]{title}:[/bold cyan]")
    default_idx = "1"

    for idx, (val, display) in enumerate(options, start=1):
        console.print(f"  [{idx}] {display}")
        if default_value is not None and val == default_value:
            default_idx = str(idx)

    valid_choices = [str(i) for i in range(1, len(options) + 1)]
    choice = Prompt.ask("Choose option", choices=valid_choices, default=default_idx).strip()
    selected_idx = int(choice) - 1
    return options[selected_idx][0]


class DynamicMenu:
    """Renders a dynamically numbered list of menu actions with support for letter keys."""

    def __init__(self, title: str):
        self.title = title
        self.items: List[MenuItem] = []

    def add(self, label: str, action: Callable[[], Any], key: Optional[str] = None) -> DynamicMenu:
        """Add an action item to the menu."""
        self.items.append(MenuItem(label=label, action=action, key=key))
        return self

    def show_and_execute(self, console: Console, default: str = "1") -> Any:
        """Render the menu with dynamic numbers, prompt for choice, and execute the handler."""
        console.print(f"\n[bold cyan]{self.title}:[/bold cyan]")

        # Separate auto-numbered items from explicit key items (e.g. '0', 'Q')
        numbered_items: List[MenuItem] = []
        keyed_items: List[MenuItem] = []

        for item in self.items:
            if item.key is None:
                numbered_items.append(item)
            else:
                keyed_items.append(item)

        # 1. Print numbered items dynamically
        for idx, item in enumerate(numbered_items, start=1):
            console.print(f"  [{idx}] {item.label}")

        # 2. Print keyed items (e.g. '0' for exit, 'Q' for return)
        for item in keyed_items:
            console.print(f"  [{item.key}] {item.label}")

        # Build choices
        choices_map = {}
        for idx, item in enumerate(numbered_items, start=1):
            choices_map[str(idx)] = item
        for item in keyed_items:
            assert item.key is not None
            choices_map[item.key.upper()] = item
            choices_map[item.key.lower()] = item

        valid_choices = [str(i) for i in range(1, len(numbered_items) + 1)] + [
            item.key for item in keyed_items if item.key is not None
        ]

        choice = Prompt.ask(
            "\nChoose an option",
            choices=valid_choices,
            default=default,
        ).strip()

        selected_item = choices_map.get(choice.upper()) or choices_map.get(choice)
        if selected_item:
            return selected_item.action()
        return None
