"""Subset x bar metrics for Track B decompose plots."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PLOT_DIR = Path(__file__).resolve().parent
_EXPERIMENTS_ROOT = _PLOT_DIR.parent
if str(_EXPERIMENTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_EXPERIMENTS_ROOT))

from catalog_eval import decomposed_track_b_metrics  # noqa: E402

SUBSET_LABELS = {
    "all": "ALL warm",
    "ceiling": "star_norm >= 0.99",
    "star_varies": "star_norm < 1.0",
    "low_tail": "review_rank_score < 1.5",
}

BAR_LABELS = ("star_norm_avg", "sentiment_avg", "review_rank_score")


def warm_frame(df: pd.DataFrame) -> pd.DataFrame:
    warm = df.dropna(subset=["review_rank_score"]).copy()
    if warm.empty:
        raise ValueError("no warm rows")
    if "sentiment_avg" not in warm.columns:
        warm["sentiment_avg"] = (
            pd.to_numeric(warm["positive_avg"], errors="coerce")
            - pd.to_numeric(warm["negative_avg"], errors="coerce")
        )
    return warm


def subset_masks(warm: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "all": pd.Series(True, index=warm.index),
        "ceiling": warm["star_norm_avg"] >= 0.99,
        "star_varies": warm["star_norm_avg"] < 1.0,
        "low_tail": warm["review_rank_score"] < 1.5,
    }


def decomposed_metrics_from_csv(csv_path: Path) -> list[dict]:
    warm = warm_frame(pd.read_csv(csv_path))
    return decomposed_track_b_metrics(
        warm["y_hat"].to_numpy(dtype=float),
        warm["review_rank_score"].to_numpy(dtype=float),
        warm["star_norm_avg"].to_numpy(dtype=float),
        warm["sentiment_avg"].to_numpy(dtype=float),
    )


def format_metrics_txt(title: str, rows: list[dict], warm_n: int) -> str:
    by_subset: dict[str, list[dict]] = {}
    for row in rows:
        by_subset.setdefault(str(row["subset"]), []).append(row)

    lines = [title, f"total warm n = {warm_n}", ""]
    for subset_key, label in SUBSET_LABELS.items():
        subset_rows = by_subset.get(subset_key, [])
        n = next((r["n"] for r in subset_rows if r["bar"] == "review_rank_score"), 0)
        lines.append(f"[{label}] n={n}")
        if int(n) < 2:
            lines.append("  (too few for correlation)")
            lines.append("")
            continue
        for bar in BAR_LABELS:
            match = next((r for r in subset_rows if r["bar"] == bar), None)
            if match is None:
                continue
            rho = match["spearman"]
            if rho == "n/a":
                lines.append(f"  Spearman(y_hat, {bar}) = n/a (constant)")
            else:
                lines.append(f"  Spearman(y_hat, {bar}) = {float(rho):.4f}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
