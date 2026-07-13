"""Score scales, interaction targets, review aggregation."""

from __future__ import annotations

import pandas as pd

from config import ExperimentConfig


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
    out["row_product_02"] = out["star_02"] * out["sentiment_02"]
    return out


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
    review_raw: pd.DataFrame, target_mode: str
) -> tuple[pd.DataFrame, str]:
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
        )
        .assign(recipe_id=lambda d: d["recipe_id"].astype(str))
    )
    review_agg["legacy_review_rank"] = (
        review_agg["star_norm_avg"] + review_agg["sentiment_avg"]
    )
    if target_mode == "product_02_row":
        review_agg["review_rank_score"] = review_agg["row_product_avg"]
        formula = "mean(star_02 * sentiment_02) per recipe (B3)"
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
    print("scoring ok")
