"""End-to-End tests for RecipeRunner with YAML test fixtures."""

from pathlib import Path

import pytest

from core.config.recipe import RadioPlannerRecipe
from core.runner import RecipeRunner

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "configurations"


def test_recipe_runner_corridor(tmp_path: Path):
    """Test executing route corridor YAML recipe end-to-end."""
    recipe_file = FIXTURES_DIR / "route_corridor_tx_la_ms.yaml"
    recipe = RadioPlannerRecipe.from_yaml_file(recipe_file)

    runner = RecipeRunner()
    codeplug, out_file = runner.run(recipe, base_output_dir=tmp_path)

    assert codeplug.total_channels > 0
    assert out_file.is_file()
    assert out_file.name == "test_tyler_jackson_corridor.csv"
    assert out_file.stat().st_size > 0


def test_recipe_runner_proximity(tmp_path: Path):
    """Test executing proximity search YAML recipe end-to-end."""
    recipe_file = FIXTURES_DIR / "proximity_dallas_50mi.yaml"
    recipe = RadioPlannerRecipe.from_yaml_file(recipe_file)

    runner = RecipeRunner()
    codeplug, out_file = runner.run(recipe, base_output_dir=tmp_path)

    assert codeplug.total_channels > 0
    assert out_file.is_file()
    assert out_file.name == "test_dallas_proximity_50mi.csv"


def test_recipe_runner_aviation(tmp_path: Path):
    """Test executing aviation planner YAML recipe end-to-end."""
    recipe_file = FIXTURES_DIR / "aviation_tyler_regional.yaml"
    recipe = RadioPlannerRecipe.from_yaml_file(recipe_file)

    runner = RecipeRunner()
    codeplug, out_file = runner.run(recipe, base_output_dir=tmp_path)

    assert codeplug.total_channels > 0
    assert out_file.is_file()
    assert out_file.name == "test_tyler_aviation.csv"


def test_recipe_runner_invalid_recipe():
    """Test invalid recipe validation before execution."""
    bad_recipe = RadioPlannerRecipe(mode="ROUTE_CORRIDOR", name="Bad")
    runner = RecipeRunner()
    with pytest.raises(ValueError, match="Recipe validation failed"):
        runner.run(bad_recipe)
