"""Paths for plot scripts (data + figures live in ai/experiments/)."""

from pathlib import Path

EXPERIMENTS_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = EXPERIMENTS_ROOT / "figures"
RECIPE_LIGHTFM_CSV = EXPERIMENTS_ROOT / "recipe_lightfm.csv"
