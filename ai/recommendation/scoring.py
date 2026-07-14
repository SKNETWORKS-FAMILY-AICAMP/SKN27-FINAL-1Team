"""Score scales, interaction targets, review aggregation."""

from __future__ import annotations

import os

import numpy as np
import pandas as pd

from config import ExperimentConfig

BAYESIAN_M_DEFAULT = 3.0
# ponytail: exp21 ablation knob only — T0=0.0, T1=0.5; adopt → fold into formula & delete
MIX_GAMMA = 0.0


def experiment_tag() -> str:
    # ponytail: mix-on → exp21 t1 tag; mix-off keeps adopted baseline label
    if MIX_GAMMA != 0.0:
        return "21_sentiment_t1"
    return "20_bayesian_bar"


def star_02_from_count(star_count: pd.Series) -> pd.Series:
    return (pd.to_numeric(star_count, errors="coerce") - 1.0) / 2.0


def star_02_from_star(star: pd.Series) -> pd.Series:
    return pd.to_numeric(star, errors="coerce") + 1.0


def sentiment_02_from_sentiment(sentiment: pd.Series) -> pd.Series:
    return pd.to_numeric(sentiment, errors="coerce").add(1.0).clip(0.0, 2.0)


def sentiment_02(positive: pd.Series, negative: pd.Series) -> pd.Series:
    sentiment = pd.to_numeric(positive, errors="coerce") - pd.to_numeric(
        negative, errors="coerce"
    )
    return sentiment_02_from_sentiment(sentiment)


def mix_conflict(positive, negative) -> np.ndarray:
    """clip(2 * min(p, n), 0, 1) — high when strong+strong."""
    p = np.asarray(pd.to_numeric(positive, errors="coerce"), dtype=np.float64).ravel()
    n = np.asarray(pd.to_numeric(negative, errors="coerce"), dtype=np.float64).ravel()
    return np.clip(2.0 * np.minimum(p, n), 0.0, 1.0)


def apply_mix_factor(q, positive, negative, gamma: float | None = None):
    """q * (1 - gamma * conflict). gamma=None → module MIX_GAMMA."""
    g = float(MIX_GAMMA if gamma is None else gamma)
    q_arr = np.asarray(pd.to_numeric(q, errors="coerce"), dtype=np.float64)
    if g == 0.0:
        return q_arr
    return q_arr * (1.0 - g * mix_conflict(positive, negative))


def add_row_02_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "star_count" in out.columns:
        out["star_02"] = star_02_from_count(out["star_count"])
    elif "star" in out.columns:
        out["star_02"] = star_02_from_star(out["star"])
    else:
        raise ValueError("need star_count or star for star_02")
    if "sentiment_02" not in out.columns:
        if "sentiment" in out.columns:
            out["sentiment_02"] = sentiment_02_from_sentiment(out["sentiment"])
        elif {"positive", "negative"}.issubset(out.columns):
            out["sentiment_02"] = sentiment_02(out["positive"], out["negative"])
        else:
            raise ValueError("need sentiment or positive/negative for sentiment_02")
    q = out["star_02"] * out["sentiment_02"]
    if {"positive", "negative"}.issubset(out.columns):
        q = apply_mix_factor(q, out["positive"], out["negative"])
    out["row_product_02"] = q
    return out


def bayesian_average(
    R: pd.Series | np.ndarray,
    v: pd.Series | np.ndarray,
    C: float,
    m: float = BAYESIAN_M_DEFAULT,
) -> np.ndarray:
    """IMDb-style WR = v/(v+m)*R + m/(v+m)*C. R and C on the same scale."""
    R = np.asarray(R, dtype=np.float64).ravel()
    v = np.asarray(v, dtype=np.float64).ravel()
    m = float(m)
    if m < 0.0:
        raise ValueError("m must be >= 0")
    denom = v + m
    # ponytail: v=0 → WR=C; avoids 0/0
    w = np.where(denom > 0.0, v / denom, 0.0)
    return w * R + (1.0 - w) * float(C)


def calc_interaction_value(
    star,
    sentiment,
    *,
    target_mode: str,
    star_weight: float = 1.0,
    sentiment_weight: float = 1.0,
    star_02=None,
    sentiment_02=None,
):
    if target_mode == "product_02_row":
        return pd.to_numeric(star_02, errors="coerce").fillna(0.0) * pd.to_numeric(
            sentiment_02, errors="coerce"
        ).fillna(0.0)
    if target_mode == "sentiment_only":
        return sentiment_weight * sentiment
    if target_mode == "star_only":
        return star_weight * star
    if target_mode == "ratio_1_2":
        return star_weight * star + sentiment_weight * sentiment
    return star_weight * star + sentiment_weight * sentiment


def add_interaction_column(review_df: pd.DataFrame, cfg: ExperimentConfig) -> pd.DataFrame:
    out = review_df.copy()
    star_s = pd.to_numeric(out["star"], errors="coerce").fillna(0.0)
    sent_s = pd.to_numeric(out["sentiment"], errors="coerce").fillna(0.0)
    star_02_s = pd.to_numeric(out["star_02"], errors="coerce").fillna(0.0)
    sent_02_s = pd.to_numeric(out["sentiment_02"], errors="coerce").fillna(0.0)
    out["interaction_value"] = calc_interaction_value(
        star_s,
        sent_s,
        target_mode=cfg.target_mode,
        star_weight=cfg.star_weight,
        sentiment_weight=cfg.sentiment_weight,
        star_02=star_02_s,
        sentiment_02=sent_02_s,
    )
    return out


def aggregate_review_for_export(
    review_raw: pd.DataFrame,
    target_mode: str,
    *,
    bar_mode: str | None = None,
    bayesian_m: float = BAYESIAN_M_DEFAULT,
) -> tuple[pd.DataFrame, str]:
    """bar_mode: bayesian (default, exp20) | mean. Override via BAR_MODE env."""
    if bar_mode is None:
        # adopted exp20: Bayesian WR default; BAR_MODE=mean for legacy mean bar
        bar_mode = os.environ.get("BAR_MODE", "bayesian")
    if bar_mode not in ("mean", "bayesian"):
        raise ValueError("bar_mode must be mean or bayesian")

    review_raw = add_row_02_columns(review_raw)
    review_raw = review_raw.copy()
    review_raw["sentiment_row"] = (
        review_raw["positive"].astype(float) - review_raw["negative"].astype(float)
    )
    review_agg = (
        review_raw.groupby("recipe_id", as_index=False)
        .agg(
            positive_avg=("positive", "mean"),
            negative_avg=("negative", "mean"),
            star_count_avg=("star_count", "mean"),
            star_norm_avg=("star_norm", "mean"),
            sentiment_avg=("sentiment_row", "mean"),
            row_product_avg=("row_product_02", "mean"),
            review_n=("recipe_id", "size"),
        )
        .assign(recipe_id=lambda d: d["recipe_id"].astype(str))
    )
    review_agg["legacy_review_rank"] = (
        review_agg["star_norm_avg"] + review_agg["sentiment_avg"]
    )
    if target_mode == "product_02_row":
        R = review_agg["row_product_avg"].to_numpy(dtype=float)
        C = float(np.nanmean(R))
        if bar_mode == "bayesian":
            review_agg["review_rank_score"] = bayesian_average(
                R, review_agg["review_n"].to_numpy(dtype=float), C, m=bayesian_m
            )
            formula = (
                f"Bayesian WR on mean(star_02*sentiment_02*(1-mix*conflict)); "
                f"C={C:.4f}, m={bayesian_m}, mix_gamma={MIX_GAMMA}"
            )
        else:
            review_agg["review_rank_score"] = review_agg["row_product_avg"]
            formula = (
                f"mean(star_02*sentiment_02*(1-mix*conflict)); mix_gamma={MIX_GAMMA}"
            )
    else:
        review_agg["review_rank_score"] = review_agg["legacy_review_rank"]
        formula = "star_norm_avg + sentiment_avg (from review_by_llm)"
    return review_agg, formula


if __name__ == "__main__":
    toy = pd.DataFrame({"star_count": [1, 5], "positive": [0.2, 0.9], "negative": [0.8, 0.1]})
    out = add_row_02_columns(toy)
    assert float(out.loc[0, "star_02"]) == 0.0
    assert float(out.loc[1, "star_02"]) == 2.0
    v = calc_interaction_value(
        pd.Series([0.0]),
        pd.Series([0.0]),
        target_mode="product_02_row",
        star_02=pd.Series([1.0]),
        sentiment_02=pd.Series([2.0]),
    )
    assert float(v.iloc[0]) == 2.0
    # same R=max; larger v → WR closer to R (higher when R > C)
    wr1 = float(bayesian_average([5.0], [1.0], C=4.0, m=3.0)[0])
    wr10 = float(bayesian_average([5.0], [10.0], C=4.0, m=3.0)[0])
    assert wr10 > wr1

    # mix: gamma=0 identical; gamma=0.5 strong-ambivalent q < weak-ambivalent (same star/valence~)
    star = 2.0
    sent_strong = sentiment_02_from_sentiment(pd.Series([0.9 - 0.8])).iloc[0]
    sent_weak = sentiment_02_from_sentiment(pd.Series([0.2 - 0.1])).iloc[0]
    q0_s = float(apply_mix_factor([star * sent_strong], [0.9], [0.8], gamma=0.0)[0])
    q0_w = float(apply_mix_factor([star * sent_weak], [0.2], [0.1], gamma=0.0)[0])
    assert abs(q0_s - star * sent_strong) < 1e-12
    assert abs(q0_w - star * sent_weak) < 1e-12
    q5_s = float(apply_mix_factor([star * sent_strong], [0.9], [0.8], gamma=0.5)[0])
    q5_w = float(apply_mix_factor([star * sent_weak], [0.2], [0.1], gamma=0.5)[0])
    assert q5_s < q5_w
    assert experiment_tag() == "20_bayesian_bar"
    print("scoring ok", wr1, wr10, q5_s, q5_w)
