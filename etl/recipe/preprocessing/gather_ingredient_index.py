"""recipe_fix.csv 재료 집계 → ingredient_recipe_index.csv (역링크 포함)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from etl.recipe.load_to_postgres.loader import (
    clean_ingredient_name,
    parse_ingredient_rows,
    resolve_ingredient_name,
)
from etl.recipe.preprocessing.recipe_processing import load_recipe_data, save_recipe_data

RECIPE_FIX_CSV = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
OUTPUT_CSV = ROOT / "storage" / "processed" / "recipe" / "ingredient_recipe_index.csv"


def collect_ingredient_index(df: pd.DataFrame) -> dict[str, dict]:
    """normalized_name → {name, recipe_ids} 집계."""
    index: dict[str, dict] = {}
    for _, row in df.iterrows():
        recipe_id = int(row["RCP_SNO"])
        for item in parse_ingredient_rows(row["CKG_MTRL_CN"]):
            raw_name = str(item[0]).strip()
            resolved = resolve_ingredient_name(raw_name)
            if not resolved:
                continue
            cleaned_name, norm = resolved
            bucket = index.setdefault(norm, {"name": cleaned_name, "recipe_ids": set()})
            bucket["recipe_ids"].add(recipe_id)
    return index


def build_index_dataframe(index: dict[str, dict]) -> pd.DataFrame:
    """ingredient_id 순 정렬 DataFrame 생성."""
    rows: list[dict] = []
    for ingredient_id, norm in enumerate(sorted(index), start=1):
        data = index[norm]
        recipe_ids = sorted(data["recipe_ids"])
        rows.append(
            {
                "ingredient_id": ingredient_id,
                "name": data["name"],
                "normalized_name": norm,
                "recipe_ids": json.dumps(recipe_ids, ensure_ascii=False),
                "recipe_count": len(recipe_ids),
            }
        )
    return pd.DataFrame(rows)


def gather_ingredient_index(
    input_path: Path | str = RECIPE_FIX_CSV,
    output_path: Path | str = OUTPUT_CSV,
) -> pd.DataFrame:
    df = load_recipe_data(input_path)
    if "RCP_SNO" not in df.columns or "CKG_MTRL_CN" not in df.columns:
        raise ValueError("필수 컬럼 누락: RCP_SNO, CKG_MTRL_CN")

    index = collect_ingredient_index(df)
    result = build_index_dataframe(index)
    save_recipe_data(result, output_path)
    print(f"고유 재료 수: {len(result)}")
    return result


def _self_check() -> None:
    assert clean_ingredient_name("?") is None
    assert clean_ingredient_name("?식빵") == "식빵"
    assert clean_ingredient_name("통깨 2숟갈") == "통깨"
    assert clean_ingredient_name("고구마 중") == "고구마"
    assert clean_ingredient_name("무 작은거") == "무"
    assert clean_ingredient_name("참치 작은캔") == "참치"
    assert clean_ingredient_name("후추 톡톡") == "후추"
    assert clean_ingredient_name("바질잎 조금") == "바질잎"
    assert clean_ingredient_name("세발나물 넉넉히") == "세발나물"
    assert clean_ingredient_name("코코아가루 적당량") == "코코아가루"
    assert clean_ingredient_name("약간") is None
    assert clean_ingredient_name("후추약간") == "후추"
    assert clean_ingredient_name("감자 小") == "감자"
    assert clean_ingredient_name("감자 작은 것") == "감자"
    assert clean_ingredient_name("감자 작은것") == "감자"
    assert clean_ingredient_name("양파 大") == "양파"
    assert clean_ingredient_name("감자 중간 크기") == "감자"
    assert clean_ingredient_name("감자 중간크기") == "감자"
    assert clean_ingredient_name("감자 큰 거") == "감자"
    assert clean_ingredient_name("당근 큰거") == "당근"
    assert clean_ingredient_name("갈아만든배") == "갈아만든배"
    assert clean_ingredient_name("갈아만든 배") == "갈아만든배"
    assert clean_ingredient_name("갈아만든 배음료") == "갈아만든배"
    assert clean_ingredient_name("감자전분") == "감자전분"
    assert clean_ingredient_name("감자전분가루") == "감자전분"
    assert clean_ingredient_name("전분가루") == "전분"
    assert clean_ingredient_name("타피오카 전분가루") == "타피오카 전분"
    assert clean_ingredient_name("건크랜베리") == "건크랜베리"
    assert clean_ingredient_name("건 크린베리") == "건크랜베리"
    assert clean_ingredient_name("건고추") == "건고추"
    assert clean_ingredient_name("건고추 다진것") == "건고추"
    assert clean_ingredient_name("대파 다진것") == "대파"
    assert clean_ingredient_name("양파 다진 것") == "양파"
    assert clean_ingredient_name("고구마줄기") == "고구마줄기"
    assert clean_ingredient_name("고구마 줄거리") == "고구마줄기"
    assert clean_ingredient_name("고구마 줄기") == "고구마줄기"
    assert clean_ingredient_name("고구마 중 사이즈") == "고구마"
    assert clean_ingredient_name("고구마 중사이즈") == "고구마"
    assert clean_ingredient_name("고운 고춧가루") == "고운 고춧가루"
    assert clean_ingredient_name("고은 고춧가루") == "고운 고춧가루"
    assert clean_ingredient_name("고형 카레") == "고형 카레"
    assert clean_ingredient_name("고형 고체 카레") == "고형 카레"
    assert clean_ingredient_name("고형 카레 큐브") == "고형 카레"
    assert clean_ingredient_name("고체카레") == "고형 카레"
    assert clean_ingredient_name("골뱅이") == "골뱅이"
    assert clean_ingredient_name("골뱅이캔") == "골뱅이"
    assert clean_ingredient_name("골뱅이 통조림") == "골뱅이"
    assert clean_ingredient_name("그라나파다노") == "그라나파다노치즈"
    assert clean_ingredient_name("그라나파다노치즈") == "그라나파다노치즈"
    assert clean_ingredient_name("그라노파다노 치즈") == "그라나파다노치즈"

    sample = pd.DataFrame(
        {
            "RCP_SNO": [1, 2, 3],
            "CKG_MTRL_CN": [
                "[['양파', '1', '개'], ['간장', '2', 't']]",
                "[[' 양파', '1/2', '개'], ['설탕', '1', 't']]",
                "[[' ?', '', ''], ['?식빵', '2', '장'], ['통깨 2숟갈', '2', '숟갈']]",
            ],
        }
    )
    index = collect_ingredient_index(sample)
    assert len(index) == 5
    assert "?" not in index
    assert index["식빵"]["name"] == "식빵"
    assert index["통깨"]["name"] == "통깨"
    assert len(index["양파"]["recipe_ids"]) == 2
    assert index["양파"]["recipe_ids"] == {1, 2}

    result = build_index_dataframe(index)
    assert list(result["ingredient_id"]) == [1, 2, 3, 4, 5]
    assert result["recipe_count"].sum() == 6
    onion_row = result.loc[result["normalized_name"] == "양파"].iloc[0]
    assert json.loads(onion_row["recipe_ids"]) == [1, 2]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="recipe_fix 재료 집계·역링크 CSV 생성")
    parser.add_argument("--input", default=str(RECIPE_FIX_CSV), help="입력 recipe_fix.csv")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="출력 ingredient_recipe_index.csv")
    return parser.parse_args()


if __name__ == "__main__":
    _self_check()
    args = _parse_args()
    gather_ingredient_index(args.input, args.output)
