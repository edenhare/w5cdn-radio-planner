"""Tests for interactive wizard helper methods, radio selector, and waypoint editor."""

import io
from pathlib import Path
from unittest.mock import patch

from rich.console import Console

from cli.wizard.interactive import InteractiveWizard
from cli.wizard.radio_selector import select_target_radio_hierarchical
from cli.wizard.waypoint_editor import validate_and_edit_route
from core.managers.preferences_manager import PreferencesManager
from core.managers.radio_manager import RadioManager
from core.managers.template_manager import TemplateManager
from core.providers.geocoding import GeocodingProvider


def test_wizard_select_target_radio():
    """Test hierarchical target radio selection prompt (Brand choice -> Model choice)."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    # First ask: select brand "1", second ask: select model "1"
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "1"]):
        selected_id = wizard._select_target_radio()
        assert selected_id is not None
        assert selected_id in {r.id for r in wizard.radio_mgr.list_radios()}
        assert "RadioPlanner -- Radio Configuration" in out.getvalue()


def test_hierarchical_radio_selector_quit():
    """Test cancelling radio selector at brand level with Q."""
    out = io.StringIO()
    console = Console(file=out)
    radio_mgr = RadioManager()

    with patch("rich.prompt.Prompt.ask", side_effect=["Q"]):
        selected = select_target_radio_hierarchical(console, radio_mgr)
        assert selected is None


def test_hierarchical_radio_selector_back_and_select():
    """Test navigating back from model selection to brand selection, then picking another."""
    out = io.StringIO()
    console = Console(file=out)
    radio_mgr = RadioManager()

    # Brand 1 -> Model 'B' (back) -> Brand 1 -> Model 1
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "B", "1", "1"]):
        selected = select_target_radio_hierarchical(console, radio_mgr)
        assert selected is not None


def test_validate_and_edit_route_confirm():
    """Test route validation and immediate confirmation."""
    out = io.StringIO()
    console = Console(file=out)
    geocoder = GeocodingProvider()

    waypoints = ["Tyler, TX", "Shreveport, LA"]
    with patch("rich.prompt.Prompt.ask", side_effect=["C"]):
        result = validate_and_edit_route(console, waypoints, geocoder)
        assert result == ["Tyler, TX", "Shreveport, LA"]


def test_validate_and_edit_route_edit_typo_and_confirm():
    """Test correcting a misspelled waypoint in editor using action [E]."""
    out = io.StringIO()
    console = Console(file=out)
    geocoder = GeocodingProvider()

    # Stop 2 has typo "Shrevepoort, LA" -> Action E (edit) -> stop 2 -> "Shreveport, LA" -> Action C (confirm)
    waypoints = ["Tyler, TX", "Shrevepoort, LA"]
    with patch("rich.prompt.Prompt.ask", side_effect=["E", "Shreveport, LA", "C"]):
        with patch("rich.prompt.IntPrompt.ask", return_value=2):
            result = validate_and_edit_route(console, waypoints, geocoder)
            assert result == ["Tyler, TX", "Shreveport, LA"]


def test_validate_and_edit_route_reverse():
    """Test reversing route direction using action [V]."""
    out = io.StringIO()
    console = Console(file=out)
    geocoder = GeocodingProvider()

    waypoints = ["Tyler, TX", "Shreveport, LA", "Jackson, MS"]
    # Action V (reverse) -> Action C (confirm)
    with patch("rich.prompt.Prompt.ask", side_effect=["V", "C"]):
        result = validate_and_edit_route(console, waypoints, geocoder)
        assert result == ["Jackson, MS", "Shreveport, LA", "Tyler, TX"]


def test_validate_and_edit_route_new_route_wizard():
    """Test entering a route from scratch with [N]."""
    out = io.StringIO()
    console = Console(file=out)
    geocoder = GeocodingProvider()

    initial = ["Tyler, TX"]
    # Action N -> Start "Austin, TX" -> Dest "Houston, TX" -> intermediate "" (done) -> Action C
    with patch("rich.prompt.Prompt.ask", side_effect=["N", "Austin, TX", "Houston, TX", "", "C"]):
        result = validate_and_edit_route(console, initial, geocoder)
        assert result == ["Austin, TX", "Houston, TX"]


def test_validate_and_edit_route_kill_and_add():
    """Test killing/clearing waypoints with [K], then adding with [A]."""
    out = io.StringIO()
    console = Console(file=out)
    geocoder = GeocodingProvider()

    initial = ["Tyler, TX", "Shreveport, LA"]
    # Action K (confirm clear) -> Action A "Dallas, TX" -> Action A "Fort Worth, TX" -> Action C
    with patch("rich.prompt.Prompt.ask", side_effect=["K", "A", "Dallas, TX", "A", "Fort Worth, TX", "E", "C"]):
        with patch("rich.prompt.Confirm.ask", return_value=True):
            result = validate_and_edit_route(console, initial, geocoder)
            assert result == ["Dallas, TX", "Fort Worth, TX"]


def test_wizard_flow_preferences_callsign(tmp_path: Path):
    """Test numbered preferences selection and editing item 1 (Callsign), then Q to return."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # First ask: select option "1", prompt for callsign returns "w5test" (lowercase to test auto-uppercase), then Q
    with patch("rich.prompt.Prompt.ask", side_effect=["1", "w5test", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.callsign == "W5TEST"
    assert "RadioPlanner -- User Preferences" in out.getvalue()
    assert "User Preferences & Settings:" in out.getvalue()
    assert "[1] Amateur Callsign:" in out.getvalue()


def test_wizard_flow_preferences_distance_units_single_letter(tmp_path: Path):
    """Test editing distance unit using single letter 'k' for kilometers."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # Option "4", input "k", then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["4", "k", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.distanceUnit == "KILOMETERS"


def test_wizard_flow_preferences_default_radio_clear(tmp_path: Path):
    """Test clearing default target radio to None using 0."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # First set a default radio
    wizard.prefs_mgr.save_preferences(
        wizard.prefs_mgr.preferences.update_settings(defaultRadioId="baofeng_5rm")
    )
    assert wizard.prefs_mgr.preferences.defaultRadioId == "baofeng_5rm"

    # Option "5", select "0" to clear, then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["5", "0", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.defaultRadioId is None


def test_wizard_flow_preferences_language_number_list(tmp_path: Path):
    """Test selecting language via numbered list."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # Option "6" (Language), select "2" (Spanish), then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["6", "2", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.language == "SPANISH"


def test_wizard_flow_preferences_color_theme(tmp_path: Path):
    """Test selecting color theme via numbered list item 7."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # Option "7" (UI Color Theme), select "2" (LIGHT), then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["7", "2", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.preferences.colorTheme == "LIGHT"


def test_wizard_flow_route_corridor_with_band_selection():
    """Verify Mode 1 Route Corridor flow prompts for radio bands and repeater access and generates rich codeplug."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    with patch("cli.wizard.interactive.validate_and_edit_route", return_value=["Tyler, TX", "Shreveport, LA", "Jackson, MS"]), \
         patch("cli.wizard.interactive.select_and_sequence_blocks", return_value=["TEMPLATE:calling_channels", "ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"]), \
         patch.object(wizard, "_select_target_radio", return_value="btech_dmr6x2"), \
         patch("cli.wizard.interactive.select_bands_for_radio", return_value=["2m", "70cm", "WX"]), \
         patch("cli.wizard.interactive.select_repeater_access", return_value=["OPEN"]), \
         patch("cli.wizard.interactive.select_channel_naming_format", return_value="CALLSIGN_FREQ"), \
         patch("rich.prompt.Prompt.ask", side_effect=["25.0"]), \
         patch("rich.prompt.Confirm.ask", side_effect=[True, True]), \
         patch.object(wizard, "_channel_review_and_export_loop") as mock_review:
        wizard._flow_route_corridor()
        assert mock_review.called
        args, _ = mock_review.call_args
        codeplug, recipe, radio_spec = args
        # Verify that more than 20 channels were found along the 320mi route
        assert codeplug.total_channels > 20
        assert radio_spec.id == "btech_dmr6x2"
        assert recipe.radio_target.bands == ["2m", "70cm", "WX"]
        assert recipe.radio_target.repeater_access == ["OPEN"]
        assert recipe.radio_target.naming_format == "CALLSIGN_FREQ"
        assert "RadioPlanner -- Route Corridor Configuration Review" in out.getvalue()


def test_wizard_flow_preferences_repeaterbook_key_entry(tmp_path: Path):
    """Test entering RepeaterBook API key through User Preferences window updates token and provider."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)

    # Option "8" (RepeaterBook API Key), enter "test_key_12345", then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["8", "test_key_12345", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.tokens.repeaterBookApiKey == "test_key_12345"
    assert wizard.repeater_provider.api_key == "test_key_12345"
    assert wizard.repeater_provider.has_api_key() is True
    assert "RepeaterBook API Key saved" in out.getvalue()


def test_wizard_flow_preferences_repeaterbook_key_clear(tmp_path: Path):
    """Test clearing RepeaterBook API key through User Preferences window."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    prefs_file = tmp_path / "preferences.yaml"
    tokens_file = tmp_path / "tokens"
    wizard.prefs_mgr = PreferencesManager(prefs_path=prefs_file, tokens_path=tokens_file)
    wizard.prefs_mgr.tokens = wizard.prefs_mgr.tokens.model_copy(update={"repeaterBookApiKey": "existing_key"})
    wizard.repeater_provider.api_key = "existing_key"

    # Option "8" (RepeaterBook API Key), enter empty string "", then "Q"
    with patch("rich.prompt.Prompt.ask", side_effect=["8", "", "Q"]):
        wizard._flow_preferences()

    assert wizard.prefs_mgr.tokens.repeaterBookApiKey is None
    assert wizard.repeater_provider.api_key is None
    assert wizard.repeater_provider.has_api_key() is False
    assert "RepeaterBook API Key cleared" in out.getvalue()


def test_wizard_flow_preset_templates_customize_direct_copy(tmp_path: Path):
    """Test customizing a template directly copies YAML to user directory without questions."""
    out = io.StringIO()
    console = Console(file=out)
    wizard = InteractiveWizard(console=console)

    user_tpl_dir = tmp_path / "templates"
    wizard.template_mgr = TemplateManager(custom_templates_dir=user_tpl_dir)

    # Action "D", choose template 1, then "B" to exit
    with patch("rich.prompt.Prompt.ask", side_effect=["D", "B"]), \
         patch("rich.prompt.IntPrompt.ask", side_effect=[1]):
        wizard._flow_templates_manager()

    assert "copied to your config directory" in out.getvalue()
    templates = wizard.template_mgr.list_templates()
    copied_file = user_tpl_dir / f"{templates[0].id}.yaml"
    assert copied_file.is_file()


def test_wizard_flow_aviation_with_template_selection():
    """Verify Mode 3 Aviation flow allows template selection and shows distance to airfield (no Waypoints)."""
    out = io.StringIO()
    console = Console(file=out, width=120)
    wizard = InteractiveWizard(console=console)

    with patch("cli.wizard.interactive.select_and_sequence_blocks", return_value=["AVIATION_BLOCK", "TEMPLATE:noaa_wx_channels"]), \
         patch.object(wizard, "_select_target_radio", return_value="alinco_dr735t"), \
         patch("rich.prompt.Prompt.ask", side_effect=["Tyler, TX", "35.0"]), \
         patch("rich.prompt.Confirm.ask", side_effect=[True]), \
         patch.object(wizard, "_channel_review_and_export_loop") as mock_review:
        wizard._flow_aviation()
        assert mock_review.called
        args, _ = mock_review.call_args
        codeplug, recipe, radio_spec = args
        assert radio_spec.id == "alinco_dr735t"
        assert radio_spec.maxNameLength == 6
        assert "TEMPLATE:noaa_wx_channels" in recipe.sequence_order
        # Verify both Airband and WX template channels are present and condensed to <= 6 chars
        bands = {ch.band for ch in codeplug.channels}
        assert "Airband" in bands
        assert "WX" in bands
        for ch in codeplug.channels:
            assert len(ch.name) <= 6

        rendered = out.getvalue()
        assert "Airfields Within Range" in rendered
        assert "Distance to Airfield" in rendered
        assert "Airfields" in rendered
        assert "Waypoints" not in rendered


def test_wizard_replay_recipe_interactive_verification_and_radio_change(tmp_path: Path):
    """Verify loading a saved recipe steps through the interactive wizard with loaded values and allows changing radio."""
    from core.config.recipe import CorridorConfig, RadioPlannerRecipe, RadioTargetConfig

    recipe_file = tmp_path / "saved_corridor.yaml"
    saved_recipe = RadioPlannerRecipe(
        mode="ROUTE_CORRIDOR",
        name="East_Texas_Run",
        corridor=CorridorConfig(waypoints=["Tyler, TX", "Shreveport, LA"], corridor_width_miles=30.0),
        radio_target=RadioTargetConfig(
            radio_id="baofeng_5rm",
            programmer_format="RT_SYSTEMS",
            include_simplex=False,
            bands=["2m"],
            modes=["FM"],
            repeater_access=["OPEN"],
        ),
        sequence_order=["ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"],
    )
    saved_recipe.to_yaml_file(recipe_file)

    out = io.StringIO()
    console = Console(file=out, width=120)
    wizard = InteractiveWizard(console=console)

    # Mock get_recipes_dir to point to tmp_path
    # User selects recipe "1", confirms "Continue to review & verify recipe settings?",
    # then in _flow_route_corridor:
    # - validate_and_edit_route receives default_waypoints == ["Tyler, TX", "Shreveport, LA"]
    # - Prompt.ask for corridor width defaults to "30.0" (we return "30.0")
    # - Confirm.ask for simplex defaults to False (we return False), then True for "Proceed with route calculation?"
    # - _select_target_radio receives default_id="baofeng_5rm", user changes to "anytone_at778uv"
    with patch("cli.wizard.interactive.get_recipes_dir", return_value=tmp_path), \
         patch("cli.wizard.interactive.validate_and_edit_route", side_effect=lambda c, wp, g: wp) as mock_wp, \
         patch("cli.wizard.interactive.select_and_sequence_blocks", side_effect=lambda c, tm, primary_block_key, primary_block_title, initial_sequence=None: initial_sequence) as mock_seq, \
         patch.object(wizard, "_select_target_radio", return_value="anytone_at778uv") as mock_radio, \
         patch("cli.wizard.interactive.select_bands_for_radio", side_effect=lambda c, spec, default_bands, mode_name: default_bands) as mock_bands, \
         patch("cli.wizard.interactive.select_repeater_access", side_effect=lambda c, default_access: default_access) as mock_access, \
         patch("cli.wizard.interactive.select_channel_naming_format", return_value="CALLSIGN") as mock_naming, \
         patch("rich.prompt.Prompt.ask", side_effect=["1", "30.0"]), \
         patch("rich.prompt.Confirm.ask", side_effect=[True, False, True]), \
         patch.object(wizard, "_channel_review_and_export_loop") as mock_review:
        wizard._flow_replay_recipe()

        # Verify initial_recipe values were passed into every step for user verification
        assert mock_wp.call_args[0][1] == ["Tyler, TX", "Shreveport, LA"]
        assert mock_seq.call_args[1]["initial_sequence"] == ["ROUTE_PLAN", "TEMPLATE:noaa_wx_channels"]
        mock_radio.assert_called_once_with(None)
        assert mock_bands.call_args[1]["default_bands"] == ["2m"]
        assert mock_access.call_args[1]["default_access"] == ["OPEN"]
        assert mock_naming.call_args[1]["default_format"] == "CITY_FREQ"

        # Verify final assembled codeplug and recipe reflect verified/updated radio selection (AnyTone AT-778UV) and CALLSIGN naming
        assert mock_review.called
        codeplug, updated_recipe, final_spec = mock_review.call_args[0]
        assert final_spec.id == "anytone_at778uv"
        assert updated_recipe.radio_target.radio_id == "anytone_at778uv"
        assert updated_recipe.radio_target.programmer_format == "CHIRP"
        assert updated_recipe.radio_target.naming_format == "CALLSIGN"
        assert updated_recipe.name == "East_Texas_Run"
        for ch in codeplug.channels:
            assert len(ch.name) <= 5


