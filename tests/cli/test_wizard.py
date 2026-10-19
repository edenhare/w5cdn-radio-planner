"""Tests for interactive wizard helper methods."""

import io
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from cli.wizard.interactive import InteractiveWizard
from core.managers.preferences_manager import PreferencesManager


def test_wizard_select_target_radio():
    """Test target radio selection prompt."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    with patch("rich.prompt.IntPrompt.ask", return_value=1):
        selected_id = wizard._select_target_radio()
        assert selected_id is not None
        assert selected_id in {r.id for r in wizard.radio_mgr.list_radios()}


def test_wizard_flow_preferences(tmp_path: Path):
    """Test numbered preferences selection and editing item 1 (Callsign), then Q to return."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # First ask: select option "1", prompt for callsign returns "W5TEST", then select "Q" to exit
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "W5TEST", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.callsign == "W5TEST"
    assert "User Preferences & Settings:" in out.getvalue()
    assert "[1] Amateur Callsign:" in out.getvalue()
