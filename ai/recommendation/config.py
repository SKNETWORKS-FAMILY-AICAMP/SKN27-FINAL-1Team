"""Experiment runtime: paths, env, seeds, model persistence."""

from __future__ import annotations

import os
import pickle
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


MODEL_DIR_NAME = "model"
MODEL_FILENAME = "lightfm_model.pkl"
ITEM_FEATURES_FILENAME = "item_features.pkl"
ID_MAPS_FILENAME = "id_maps.pkl"


@dataclass
class ExperimentConfig:
    project_root: Path
    data_dir: Path
    outputs_dir: Path
    model_dir: Path
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
    model_dir = project_root / MODEL_DIR_NAME
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
        model_dir=model_dir,
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


def save_model(cfg: ExperimentConfig, *, model, item_features, dataset) -> dict[str, Path]:
    """학습된 모델·features·ID mappings를 model/ 폴더에 저장."""
    cfg.model_dir.mkdir(parents=True, exist_ok=True)

    model_path = cfg.model_dir / MODEL_FILENAME
    features_path = cfg.model_dir / ITEM_FEATURES_FILENAME
    maps_path = cfg.model_dir / ID_MAPS_FILENAME

    with open(model_path, "wb") as f:
        pickle.dump(model, f)

    with open(features_path, "wb") as f:
        pickle.dump(item_features, f)

    user_id_map, user_feature_map, item_id_map, item_feature_map = dataset.mapping()
    with open(maps_path, "wb") as f:
        pickle.dump({
            "user_id_map": user_id_map,
            "item_id_map": item_id_map,
        }, f)

    return {"model": model_path, "item_features": features_path, "id_maps": maps_path}


def load_model(cfg: ExperimentConfig):
    """저장된 모델·features·ID mappings 로드. 추론 서비스용."""
    model_path = cfg.model_dir / MODEL_FILENAME
    features_path = cfg.model_dir / ITEM_FEATURES_FILENAME
    maps_path = cfg.model_dir / ID_MAPS_FILENAME

    with open(model_path, "rb") as f:
        model = pickle.load(f)
    with open(features_path, "rb") as f:
        item_features = pickle.load(f)
    with open(maps_path, "rb") as f:
        id_maps = pickle.load(f)

    return model, item_features, id_maps


if __name__ == "__main__":
    os.environ.setdefault("PROJECT_ROOT", str(Path(__file__).resolve().parent))
    os.environ.setdefault("LIGHTFM_RUNTIME", "linux-docker")
    cfg = load_experiment_config()
    assert cfg.positive_mode == "prefer_n_star5_ge2"
    assert cfg.data_files["review"].name == "review_by_llm.csv"
    assert cfg.model_dir.name == MODEL_DIR_NAME
    print("config ok", cfg.seed, cfg.excluded_recipe_columns, cfg.model_dir)
