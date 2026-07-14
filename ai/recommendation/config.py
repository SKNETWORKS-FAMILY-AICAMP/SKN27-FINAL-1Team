"""Experiment runtime: paths, env, seeds."""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ALLOWED_TARGET_MODES = (
    "star_sentiment_sum",
    "sentiment_only",
    "star_only",
    "ratio_1_2",
    "product_02_row",
)

ALLOWED_SAMPLE_WEIGHT_MODES = ("none", "review_n")

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
    target_mode: str = "product_02_row"
    excluded_recipe_columns: list[str] = field(default_factory=lambda: ["ingredients"])
    star_weight: float = 1.0
    sentiment_weight: float = 1.0
    model_mode: str = "hybrid"
    sample_weight_mode: str = "none"


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

    target_mode = os.environ.get("TARGET_MODE", "product_02_row")
    if target_mode not in ALLOWED_TARGET_MODES:
        raise ValueError(f"TARGET_MODE must be one of {ALLOWED_TARGET_MODES}")

    if "EXCLUDED_RECIPE_COLUMNS" in os.environ:
        excluded = [c for c in os.environ["EXCLUDED_RECIPE_COLUMNS"].split(",") if c]
    else:
        excluded = ["ingredients"]

    if target_mode == "ratio_1_2":
        star_weight = float(os.environ.get("STAR_WEIGHT", "1.0"))
        sentiment_weight = float(os.environ.get("SENTIMENT_WEIGHT", "2.0"))
    else:
        star_weight = float(os.environ.get("STAR_WEIGHT", "1.0"))
        sentiment_weight = float(os.environ.get("SENTIMENT_WEIGHT", "1.0"))

    sample_weight_mode = os.environ.get("SAMPLE_WEIGHT_MODE", "none")
    if sample_weight_mode not in ALLOWED_SAMPLE_WEIGHT_MODES:
        raise ValueError(
            f"SAMPLE_WEIGHT_MODE must be one of {ALLOWED_SAMPLE_WEIGHT_MODES}"
        )

    return ExperimentConfig(
        project_root=project_root,
        data_dir=data_dir,
        outputs_dir=outputs_dir,
        data_files=data_files,
        seed=int(os.environ.get("SEED", "42")),
        epochs=30,
        num_threads=2,
        target_mode=target_mode,
        excluded_recipe_columns=excluded,
        star_weight=star_weight,
        sentiment_weight=sentiment_weight,
        sample_weight_mode=sample_weight_mode,
    )


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


if __name__ == "__main__":
    os.environ.setdefault("PROJECT_ROOT", str(Path(__file__).resolve().parent))
    os.environ.setdefault("LIGHTFM_RUNTIME", "linux-docker")
    cfg = load_experiment_config()
    assert cfg.target_mode == "product_02_row"
    assert cfg.data_files["review"].name == "review_by_llm.csv"
    print("config ok", cfg.seed, cfg.excluded_recipe_columns)
