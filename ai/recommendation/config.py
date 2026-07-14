"""Experiment runtime: paths, env, seeds."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ALLOWED_POSITIVE_MODES = (
    "prefer_n_star5_ge2",
    "prefer_n_star5_ge2_five_star_rows",
    "five_star_reviews_only",
)

CATALOG_USER_ID = "__catalog__"


@dataclass
class ExperimentConfig:
    project_root: Path
    data_dir: Path
    outputs_dir: Path
    data_files: dict[str, Path]
    seed: int = 42
    epochs: int = 30
    num_threads: int = 2
    excluded_recipe_columns: list[str] = field(default_factory=lambda: ["ingredients"])
    model_mode: str = "hybrid"
    positive_mode: str = "prefer_n_star5_ge2"


def require_docker_runtime() -> None:
    if os.environ.get("LIGHTFM_RUNTIME", "local") != "linux-docker":
        raise RuntimeError(
            "공식 실행 환경이 아닙니다. ai/experiments 에서 "
            "'docker compose up' 후 JupyterLab에서 실행하세요."
        )


def resolve_project_root(root: Path | None = None) -> Path:
    if root is not None:
        return root
    return Path(os.environ["PROJECT_ROOT"])


def load_experiment_config(root: Path | None = None) -> ExperimentConfig:
    project_root = resolve_project_root(root)
    data_dir = project_root / "data"
    outputs_dir = project_root / "outputs"
    data_files = {
        "review": data_dir / "review_by_llm.csv",
        "recipe": data_dir / "recipe_fix.csv",
        "ingredient_alias": data_dir / "recipe_ingredient_alias.csv",
    }

    if "EXCLUDED_RECIPE_COLUMNS" in os.environ:
        excluded = [c for c in os.environ["EXCLUDED_RECIPE_COLUMNS"].split(",") if c]
    else:
        excluded = ["ingredients"]

    positive_mode = os.environ.get("POSITIVE_MODE", "prefer_n_star5_ge2")
    if positive_mode not in ALLOWED_POSITIVE_MODES:
        raise ValueError(f"POSITIVE_MODE must be one of {ALLOWED_POSITIVE_MODES}")

    return ExperimentConfig(
        project_root=project_root,
        data_dir=data_dir,
        outputs_dir=outputs_dir,
        data_files=data_files,
        seed=int(os.environ.get("SEED", "42")),
        epochs=int(os.environ.get("EPOCHS", "30")),
        num_threads=int(os.environ.get("NUM_THREADS", "2")),
        excluded_recipe_columns=excluded,
        positive_mode=positive_mode,
    )


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


if __name__ == "__main__":
    os.environ.setdefault("PROJECT_ROOT", str(Path(__file__).resolve().parent))
    os.environ.setdefault("LIGHTFM_RUNTIME", "linux-docker")
    cfg = load_experiment_config()
    assert cfg.positive_mode == "prefer_n_star5_ge2"
    assert cfg.data_files["review"].name == "review_by_llm.csv"
    print("config ok", cfg.seed, cfg.excluded_recipe_columns)
