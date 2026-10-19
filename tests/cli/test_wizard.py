"""Tests for interactive wizard helper methods."""

import io
from unittest.mock import patch

from rich.console import Console

from cli.wizard.interactive import InteractiveWizard


def test_wizard_select_target_radio():
    """Test target radio selection prompt."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    with patch("rich.prompt.IntPrompt.ask", return_value=1):
        selected_id = wizard._select_target_radio()
        assert selected_id is not None
        assert selected_id in {r.id for r in wizard.radio_mgr.list_radios()}
