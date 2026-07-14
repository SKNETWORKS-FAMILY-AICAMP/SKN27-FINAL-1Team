"""CSV load/save for Track B."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RECIPE_COLS = [
    "RCP_SNO",
    "CKG_NM",
    "INQ_CNT",
    "SRAP_CNT",
    "CKG_MTH_ACTO_NM",
    "CKG_STA_ACTO_NM",
    "CKG_MTRL_ACTO_NM",
    "CKG_KND_ACTO_NM",
    "CKG_INBUN_NM",
    "CKG_DODF_NM",
    "CKG_TIME_NM",
]
ALIAS_COLS = [
    "RCP_SNO",
    "CKG_NM",
    "ingredients_raw",
    "aliases_matched",
    "ingredients_normalized",
    "others_count",
    "others_items",
    "basic_count",
    "basic_items",
]
REVIEW_COLS = [
    "recipe_id",
    "group_id",
    "star_count",
    "content",
    "positive",
    "negative",
    "star_norm",
]

EXPORT_COLS = [
    "recipe_id",
    "recipe_name",
    "positive_avg",
    "negative_avg",
    "star_count_avg",
    "star_norm_avg",
    "y_hat",
    "y_hat_linear",
    "review_rank_score",
]
EXPORT_COLS_OPTIONAL = [
    "s_pref",
    "t_star",
    "prefer_hat",
    "y_prefer",
    "prefer_rank",
    "n_star5",
    "is_warm",
]


def _validate_columns(name: str, frame: pd.DataFrame, cols: list[str]) -> None:
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns in {name}: {missing}")


def load_track_b_tables(
    data_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    review_df = pd.read_csv(data_dir / "review_by_llm.csv")
    recipe_df = pd.read_csv(data_dir / "recipe_fix.csv")
    alias_df = pd.read_csv(data_dir / "recipe_ingredient_alias.csv")

    _validate_columns("recipe_fix.csv", recipe_df, RECIPE_COLS)
    _validate_columns("recipe_ingredient_alias.csv", alias_df, ALIAS_COLS)
    _validate_columns("review_by_llm.csv", review_df, REVIEW_COLS)

    return (
        review_df[REVIEW_COLS].copy(),
        recipe_df[RECIPE_COLS].copy(),
        alias_df[ALIAS_COLS].copy(),
    )


def export_recipe_lightfm(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = [c for c in EXPORT_COLS if c in df.columns]
    cols += [c for c in EXPORT_COLS_OPTIONAL if c in df.columns and c not in cols]
    df[cols].to_csv(path, index=False, encoding="utf-8-sig")


def write_json_report(report: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    import tempfile

    toy = pd.DataFrame(
        {
            "recipe_id": ["1"],
            "recipe_name": ["a"],
            "positive_avg": [0.1],
            "negative_avg": [0.2],
            "star_count_avg": [3.0],
            "star_norm_avg": [0.0],
            "y_hat": [0.5],
            "y_hat_linear": [0.6],
            "review_rank_score": [0.7],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        csv_path = Path(tmp) / "out.csv"
        json_path = Path(tmp) / "out.json"
        export_recipe_lightfm(toy, csv_path)
        write_json_report({"ok": True}, json_path)
        assert csv_path.exists() and json_path.exists()
    print("data_io ok")
