"""0~2 scale for star/sentiment (experiment 15+)."""

from __future__ import annotations

import pandas as pd


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


if __name__ == "__main__":
    toy = pd.DataFrame({"star_count": [1, 5], "positive": [0.2, 0.9], "negative": [0.8, 0.1]})
    out = add_row_02_columns(toy)
    assert float(out.loc[0, "star_02"]) == 0.0
    assert float(out.loc[1, "star_02"]) == 2.0
    print("score_02 ok")
