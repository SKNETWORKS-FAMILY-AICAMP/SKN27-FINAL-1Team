"""recipe_review.csv ← processed 크롤 MD에서 메트릭 컬럼 적재."""

from __future__ import annotations

import pathlib
import re
import sys
from collections.abc import Callable

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from tqdm import tqdm

from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

REVIEW_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_review.csv"
CRAWL_DIR = ROOT / "storage" / "processed" / "crawling_recipes"

_RE_COMMENT = re.compile(r"^댓글\s+(\d+)", re.MULTILINE)
_RE_COOK_REVIEW = re.compile(r"^요리 후기\s+(\d+)", re.MULTILINE)


def load_recipe_review(file_path: pathlib.Path | str = REVIEW_CSV) -> pd.DataFrame:
    return load_recipe_data(file_path)


def save_recipe_review(df: pd.DataFrame, file_path: pathlib.Path | str = REVIEW_CSV) -> None:
    save_recipe_data(df, file_path)


def _read_crawl_md(recipe_id: int) -> str | None:
    path = CRAWL_DIR / f"{recipe_id}.md"
    try:
        return path.read_text(encoding="utf-8-sig")
    except OSError:
        return None


def extract_comment_count(text: str) -> int | None:
    m = _RE_COMMENT.search(text)
    return int(m.group(1)) if m else None


def extract_cook_review_count(text: str) -> int | None:
    m = _RE_COOK_REVIEW.search(text)
    return int(m.group(1)) if m else None


def _ensure_column(df: pd.DataFrame, col: str) -> None:
    if col not in df.columns:
        df[col] = pd.NA


def _fill_column(
    df: pd.DataFrame,
    col: str,
    extract_fn: Callable[[str], int | None],
    *,
    desc: str,
) -> pd.DataFrame:
    # ponytail: 컬럼마다 MD를 다시 읽음. N컬럼이면 N×행 read. upgrade: 행 단위 1회 read 캐시
    _ensure_column(df, col)
    for index, row in tqdm(df.iterrows(), total=len(df), desc=desc):
        try:
            text = _read_crawl_md(int(row["RCP_SNO"]))
            if text is None:
                df.at[index, col] = pd.NA
                continue
            value = extract_fn(text)
            df.at[index, col] = value if value is not None else pd.NA
        except Exception:
            df.at[index, col] = pd.NA
            continue
    return df


def fill_comment_count(df: pd.DataFrame) -> pd.DataFrame:
    return _fill_column(df, "CRAWL_COMMENT_CNT", extract_comment_count, desc="댓글 수")


def fill_cook_review_count(df: pd.DataFrame) -> pd.DataFrame:
    return _fill_column(df, "CRAWL_COOK_REVIEW_CNT", extract_cook_review_count, desc="요리 후기 수")


def _self_check() -> None:
    assert extract_comment_count("<!-- user_reactions -->\n댓글 1\n") == 1
    assert extract_comment_count("댓글 0\n") == 0
    assert extract_cook_review_count("요리 후기 3\n") == 3
    assert extract_cook_review_count("no review section") is None


def main() -> None:
    df = load_recipe_review()
    df = fill_comment_count(df)
    df = fill_cook_review_count(df)
    save_recipe_review(df)


if __name__ == "__main__":
    _self_check()
    main()
