"""Unit tests for the CLI sequence and template organizer."""

from __future__ import annotations

from unittest.mock import patch

from rich.console import Console

from cli.wizard.sequence_editor import select_and_sequence_blocks
from core.managers.template_manager import TemplateManager


def test_sequence_editor_default_confirm():
    console = Console(record=True)
    tpl_mgr = TemplateManager()

    # User confirms the default sequence immediately
    with patch("rich.prompt.Prompt.ask", return_value="C"):
        seq = select_and_sequence_blocks(console, tpl_mgr)

    assert seq == [
        "TEMPLATE:calling_channels",
        "ROUTE_PLAN",
        "TEMPLATE:noaa_wx_channels",
    ]


def test_sequence_editor_reorder_and_confirm():
    console = Console(record=True)
    tpl_mgr = TemplateManager()

    # Move block 1 (TEMPLATE:calling_channels) to position 2
    prompt_side_effects = ["M", "C"]
    int_prompt_side_effects = [1, 2]

    with patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effects), \
         patch("rich.prompt.IntPrompt.ask", side_effect=int_prompt_side_effects):
        seq = select_and_sequence_blocks(console, tpl_mgr)

    assert seq == [
        "ROUTE_PLAN",
        "TEMPLATE:calling_channels",
        "TEMPLATE:noaa_wx_channels",
    ]


def test_sequence_editor_remove_block():
    console = Console(record=True)
    tpl_mgr = TemplateManager()

    # Remove block 3 (TEMPLATE:noaa_wx_channels), then confirm
    prompt_side_effects = ["R", "C"]
    int_prompt_side_effects = [3]

    with patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effects), \
         patch("rich.prompt.IntPrompt.ask", side_effect=int_prompt_side_effects):
        seq = select_and_sequence_blocks(console, tpl_mgr)

    assert seq == [
        "TEMPLATE:calling_channels",
        "ROUTE_PLAN",
    ]


def test_sequence_editor_cancel_returns_none():
    console = Console(record=True)
    tpl_mgr = TemplateManager()

    with patch("rich.prompt.Prompt.ask", return_value="B"):
        seq = select_and_sequence_blocks(console, tpl_mgr)

    assert seq is None


def test_sequence_editor_add_template():
    console = Console(record=True)
    tpl_mgr = TemplateManager()

    # Initial sequence with only ROUTE_PLAN
    # Add a template (calling_channels) to beginning, then confirm
    prompt_side_effects = ["A", "B", "C"]
    int_prompt_side_effects = [1]  # Select template #1

    with patch("rich.prompt.Prompt.ask", side_effect=prompt_side_effects), \
         patch("rich.prompt.IntPrompt.ask", side_effect=int_prompt_side_effects):
        seq = select_and_sequence_blocks(
            console,
            tpl_mgr,
            initial_sequence=["ROUTE_PLAN"],
        )

    assert seq == [
        "TEMPLATE:calling_channels",
        "ROUTE_PLAN",
    ]
