"""Runtime config, data I/O, model persistence."""

from __future__ import annotations

import json
import os
import pickle
import random
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

CATALOG_USER_ID = "__catalog__"
POSITIVE_MODE = "prefer_n_star5_ge2"

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


def require_docker_runtime() -> None:
    if os.environ.get("LIGHTFM_RUNTIME", "local") != "linux-docker":
        raise RuntimeError(
            "공식 실행 환경이 아닙니다. etl/ml_lightfm 에서 "
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
    )


def seed_all(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)


# --- Model persistence ---


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

    user_id_map, _, item_id_map, _ = dataset.mapping()
    with open(maps_path, "wb") as f:
        pickle.dump({"user_id_map": user_id_map, "item_id_map": item_id_map}, f)

    return {"model": model_path, "item_features": features_path, "id_maps": maps_path}


def load_model(cfg: ExperimentConfig):
    """저장된 모델·features·ID mappings 로드. 추론 서비스용."""
    with open(cfg.model_dir / MODEL_FILENAME, "rb") as f:
        model = pickle.load(f)
    with open(cfg.model_dir / ITEM_FEATURES_FILENAME, "rb") as f:
        item_features = pickle.load(f)
    with open(cfg.model_dir / ID_MAPS_FILENAME, "rb") as f:
        id_maps = pickle.load(f)
    return model, item_features, id_maps


# --- Data I/O (absorbed from data_io.py) ---

RECIPE_COLS = [
    "RCP_SNO", "CKG_NM", "INQ_CNT", "SRAP_CNT",
    "CKG_MTH_ACTO_NM", "CKG_STA_ACTO_NM", "CKG_MTRL_ACTO_NM",
    "CKG_KND_ACTO_NM", "CKG_INBUN_NM", "CKG_DODF_NM", "CKG_TIME_NM",
]
ALIAS_COLS = [
    "RCP_SNO", "CKG_NM", "ingredients_raw", "aliases_matched",
    "ingredients_normalized", "others_count", "others_items",
    "basic_count", "basic_items",
]
REVIEW_COLS = [
    "recipe_id", "group_id", "star_count", "content",
    "positive", "negative", "star_norm",
]
EXPORT_COLS = [
    "recipe_id", "recipe_name", "positive_avg", "negative_avg",
    "star_count_avg", "star_norm_avg", "y_hat", "s_pref",
    "t_star", "prefer_hat", "y_prefer", "prefer_rank", "n_star5", "is_warm",
]


def load_track_b_tables(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    review_df = pd.read_csv(data_dir / "review_by_llm.csv")
    recipe_df = pd.read_csv(data_dir / "recipe_fix.csv")
    alias_df = pd.read_csv(data_dir / "recipe_ingredient_alias.csv")
    return review_df[REVIEW_COLS].copy(), recipe_df[RECIPE_COLS].copy(), alias_df[ALIAS_COLS].copy()


def export_recipe_lightfm(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in EXPORT_COLS if c in df.columns]
    df[cols].to_csv(path, index=False, encoding="utf-8-sig")


def write_json_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("PROJECT_ROOT", str(Path(__file__).resolve().parent))
    os.environ.setdefault("LIGHTFM_RUNTIME", "linux-docker")
    cfg = load_experiment_config()
    assert cfg.data_files["review"].name == "review_by_llm.csv"
    assert cfg.model_dir.name == MODEL_DIR_NAME
    print("config ok", cfg.seed, cfg.model_dir)
