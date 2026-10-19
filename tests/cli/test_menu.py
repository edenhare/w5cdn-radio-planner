"""Unit tests for DynamicMenu and prompt_choice_from_list."""

import io
from unittest.mock import patch

from rich.console import Console

from cli.ui.menu import DynamicMenu, PreferenceItem, prompt_choice_from_list


def test_dynamic_menu_auto_numbering_and_dispatch():
    """Verify DynamicMenu numbers options 1..N and dispatches to handler."""
    out = io.StringIO()
    console = Console(file=out)

    called = []
    menu = DynamicMenu("Test Menu")
    menu.add("First Option", lambda: called.append("first"))
    menu.add("Second Option", lambda: called.append("second"))
    menu.add("Exit", lambda: called.append("exit"), key="0")

    # Select "2"
    with patch("rich.prompt.Prompt.ask", return_value="2"):
        menu.show_and_execute(console)

    assert called == ["second"]
    output = out.getvalue()
    assert "[1] First Option" in output
    assert "[2] Second Option" in output
    assert "[0] Exit" in output


def test_dynamic_menu_letter_key_dispatch():
    """Verify DynamicMenu dispatches explicit letter keys like Q."""
    out = io.StringIO()
    console = Console(file=out)

    called = []
    menu = DynamicMenu("Submenu")
    menu.add("Action A", lambda: called.append("A"))
    menu.add("Return to Main Menu", lambda: called.append("quit"), key="Q")

    with patch("rich.prompt.Prompt.ask", return_value="Q"):
        menu.show_and_execute(console)

    assert called == ["quit"]
    output = out.getvalue()
    assert "[1] Action A" in output
    assert "[Q] Return to Main Menu" in output


def test_prompt_choice_from_list():
    """Verify prompt_choice_from_list displays 1..N and returns selected item value."""
    out = io.StringIO()
    console = Console(file=out)

    options = [
        ("OPT_A", "Alpha Choice"),
        ("OPT_B", "Beta Choice"),
        ("OPT_C", "Gamma Choice"),
    ]

    with patch("rich.prompt.Prompt.ask", return_value="3"):
        val = prompt_choice_from_list(console, "Select Greek Letter", options, default_value="OPT_A")

    assert val == "OPT_C"
    output = out.getvalue()
    assert "[1] Alpha Choice" in output
    assert "[2] Beta Choice" in output
    assert "[3] Gamma Choice" in output


def test_preference_item_dataclass():
    """Verify PreferenceItem getters and actions."""
    val = "146.520"
    item = PreferenceItem(
        label="Calling Frequency",
        get_value=lambda: val,
        edit_action=lambda: "edited",
    )
    assert item.label == "Calling Frequency"
    assert item.get_value() == "146.520"
    assert item.edit_action() == "edited"
