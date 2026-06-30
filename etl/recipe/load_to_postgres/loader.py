"""레시피 CSV → PostgreSQL 적재."""

from __future__ import annotations

import ast
import json
import logging
import re
from fractions import Fraction
from collections.abc import Callable
from typing import Any

import pandas as pd
import psycopg
from tqdm import tqdm

from .connection import PostgreDB
from . import query

logger = logging.getLogger(__name__)

_VARCHAR_LIMITS = {
    "title": 255,
    "category": 100,
    "difficulty": 50,
    "image_url": 500,
    "source_url": 500,
    "raw_ingredient_name": 255,
    "unit": 30,
    "name": 100,
    "normalized_name": 100,
}

_REQUIRED_TABLES = ("recipes", "recipe_ingredients", "ingredients")
_REQUIRED_COLUMNS = {
    "ingredients": ("name", "normalized_name"),
    "recipes": ("id", "title", "recipe_steps"),
    "recipe_ingredients": ("recipe_id", "ingredient_id"),
}


def _clip(value: str | None, max_len: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:max_len]


_SIZE_STEM = r"(?:중간사이즈|중간크기|중사이즈|중간|중자|작은|큰)"
_CJK_SIZE = r"[小大中]"
_AMOUNT_HINT = r"(?:적당량|적당히|넉넉하게|넉넉히|원하는만큼|약간|톡톡|넉넉|솔솔|조금)"
_MODIFIER_SUFFIX_PATTERNS = (
    rf"\s+{_SIZE_STEM}\s*(?:거|것|캔|크기|사이즈)?$",
    rf"^{_SIZE_STEM}\s*(?:거|것|캔|크기|사이즈)?\s+",
    r"\s+중\s*사이즈$",  # ponytail: 고구마 중 사이즈
    r"\s+중$",  # ponytail: 고구마 중 등 단독 '중'
    rf"\s+{_CJK_SIZE}$",
    rf"(?<=\S){_CJK_SIZE}$",  # ponytail: 붙어 쓴 한자 크기(小·大·中)
    rf"\s+{_AMOUNT_HINT}$",
    rf"^{_AMOUNT_HINT}\s+",
    rf"(?<=\S){_AMOUNT_HINT}$",  # ponytail: 후추약간 등 붙어 쓴 분량 표현
)
_PREP_SUFFIX_PATTERNS = (
    r"\s+다진\s*(?:것|거)$",
    r"(?<=\S)다진(?:것|거)$",
)
_AMOUNT_ONLY = frozenset(
    "약간 톡톡 조금 적당량 적당히 넉넉 넉넉히 넉넉하게 솔솔 원하는만큼".split()
)
# ponytail: 크롤 표기 흔들림 → 표시·dedup 통일 (필요 시 항목 추가)
_CANONICAL_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^갈아만든\s*배(?:음료)?$"), "갈아만든배"),
    (re.compile(r"^건\s*크랜베리$"), "건크랜베리"),
    (re.compile(r"^고구마\s*줄기$"), "고구마줄기"),
    (re.compile(r"^고형\s*고체\s*카레$"), "고형 카레"),
    (re.compile(r"^고형\s*카레(?:\s*큐브)?$"), "고형 카레"),
    (re.compile(r"^고체\s*카레$"), "고형 카레"),
    (re.compile(r"^골뱅이(?:\s*통조림|캔)$"), "골뱅이"),
    (re.compile(r"^그라나파다노(?:\s*치즈)?$"), "그라나파다노치즈"),
)


def clean_ingredient_name(name: str) -> str | None:
    """크롤 artifact(?), 이름 내 분량(숫자·크기 수식어) 제거 후 표시용 재료명."""
    text = str(name).strip()
    if not text:
        return None
    text = re.sub(r"^[\s?]+", "", text)
    text = re.sub(r"[\s?]+$", "", text)
    if not text or text == "?":
        return None
    text = re.split(r"\d", text, maxsplit=1)[0].strip()
    if not text:
        return None
    changed = True
    while changed:
        changed = False
        for pattern in _MODIFIER_SUFFIX_PATTERNS:
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True
    changed = True
    while changed:
        changed = False
        for pattern in _PREP_SUFFIX_PATTERNS:
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True
    text = re.sub(r"크린베리", "크랜베리", text)
    text = re.sub(r"고은", "고운", text)
    text = re.sub(r"그라노파다노", "그라나파다노", text)
    text = re.sub(r"줄거리", "줄기", text)
    for pattern, canonical in _CANONICAL_REWRITES:
        if pattern.fullmatch(text):
            text = canonical
            break
    text = re.sub(r"전분\s*가루", "전분", text).strip()
    if text in _AMOUNT_ONLY:
        return None
    if not text or re.fullmatch(r"[\?\s]+", text):
        return None
    return text


def normalize_ingredient_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip().lower())


def resolve_ingredient_name(raw_name: str) -> tuple[str, str] | None:
    """(표시명, normalized_name) 또는 파싱 불가 시 None."""
    cleaned = clean_ingredient_name(raw_name)
    if not cleaned:
        return None
    normalized = normalize_ingredient_name(cleaned)
    if not normalized:
        return None
    return cleaned, normalized


def parse_quantity(value: Any) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        total = 0.0
        for part in text.split("+"):
            part = part.strip()
            if not part:
                continue
            if "/" in part:
                total += float(Fraction(part))
            else:
                total += float(part)
        return round(total, 2)
    except (ValueError, ZeroDivisionError):
        return None


def parse_serving_size(text: Any) -> int | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    value = str(text).strip()
    if not value or value == "확인필요":
        return None
    match = re.search(r"(\d+)", value)
    return int(match.group(1)) if match else None


def parse_cooking_time_minutes(text: Any) -> int | None:
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    value = str(text).strip()
    if not value or value == "확인필요":
        return None
    match = re.search(r"(\d+)", value)
    if not match:
        return None
    amount = int(match.group(1))
    if "시간" in value:
        return amount * 60
    if "분" in value:
        return amount
    return amount


def _parse_recipe_data(recipe_data_json: Any) -> dict[str, Any]:
    if recipe_data_json is None or (isinstance(recipe_data_json, float) and pd.isna(recipe_data_json)):
        return {}
    try:
        return json.loads(recipe_data_json)
    except (json.JSONDecodeError, TypeError):
        return {}


def build_recipe_steps(recipe_data_json: Any) -> list[dict[str, Any]] | None:
    """mock recipeSteps 형식(title, text) + step_no, image_url 조리단계 배열을 만든다."""
    data = _parse_recipe_data(recipe_data_json)
    if not data:
        return None

    steps: dict[int, dict[str, Any]] = {}

    for key, value in data.items():
        if not isinstance(value, dict):
            continue

        if key.startswith("recipe_step_img_"):
            step_no = int(value.get("step") or 0)
            if step_no <= 0:
                continue
            step = steps.setdefault(
                step_no,
                {"step_no": step_no, "title": f"{step_no}단계", "text": None, "image_url": None},
            )
            step["image_url"] = _clip(value.get("image"), _VARCHAR_LIMITS["image_url"])
            continue

        if not key.startswith("recipe_step_"):
            continue

        step_no = int(value.get("step") or 0)
        description = value.get("description")
        if step_no <= 0 or not description:
            continue

        step = steps.setdefault(
            step_no,
            {"step_no": step_no, "title": f"{step_no}단계", "text": None, "image_url": None},
        )
        step["text"] = str(description)

    if not steps:
        return None

    ordered = [steps[step_no] for step_no in sorted(steps) if steps[step_no].get("text")]
    return ordered or None


def serialize_recipe_steps(steps: list[dict[str, Any]] | None) -> str | None:
    if not steps:
        return None
    return json.dumps(steps, ensure_ascii=False)


def extract_image_url(recipe_data_json: Any) -> str | None:
    data = _parse_recipe_data(recipe_data_json)
    return _clip(data.get("recipe_main_thumbs"), _VARCHAR_LIMITS["image_url"])


def parse_ingredient_rows(raw_value: Any) -> list[list[str]]:
    if raw_value is None or (isinstance(raw_value, float) and pd.isna(raw_value)):
        return []
    if isinstance(raw_value, list):
        return [list(item)[:3] for item in raw_value if item]
    text = str(raw_value).strip()
    if not text:
        return []
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [list(item)[:3] for item in parsed if item]


def validate_schema(db: PostgreDB) -> None:
    """schema.sql 기준 필수 테이블·컬럼 존재 여부를 확인한다."""
    missing_tables: list[str] = []
    for table_name in _REQUIRED_TABLES:
        row = db.fetch_one(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = %(table_name)s
            """,
            {"table_name": table_name},
        )
        if row is None:
            missing_tables.append(table_name)

    if missing_tables:
        raise RuntimeError(
            "필수 테이블이 없습니다: "
            f"{', '.join(missing_tables)}. "
            "docker-compose Postgres 초기화 후 app/backend/schemas/schema.sql을 적용하세요."
        )

    missing_columns: list[str] = []
    for table_name, columns in _REQUIRED_COLUMNS.items():
        for column_name in columns:
            row = db.fetch_one(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %(table_name)s
                  AND column_name = %(column_name)s
                """,
                {"table_name": table_name, "column_name": column_name},
            )
            if row is None:
                missing_columns.append(f"{table_name}.{column_name}")

    if missing_columns:
        raise RuntimeError(
            "스키마 컬럼이 schema.sql과 일치하지 않습니다: "
            f"{', '.join(missing_columns)}. "
            "기존 DB와 충돌 시 docs/kickstarter.md의 Postgres 초기화 절차를 참고하세요."
        )


def load_dataframes(recipe_csv: str, cooking_steps_csv: str) -> pd.DataFrame:
    """레시피·조리단계 CSV를 병합한 데이터프레임을 반환한다."""
    df_recipe = pd.read_csv(recipe_csv)
    df_steps = pd.read_csv(cooking_steps_csv)

    logger.info("레시피 CSV 로드: %s (%d행)", recipe_csv, len(df_recipe))
    logger.info("조리단계 CSV 로드: %s (%d행)", cooking_steps_csv, len(df_steps))

    return df_recipe.merge(
        df_steps[["RCP_SNO", "RECIPE_URL", "RECIPE_DATA"]],
        on="RCP_SNO",
        how="left",
    )


def drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    """적재 전 데이터 검사 — 조건에 맞지 않는 행을 제외한다."""

    def _missing_cooking_steps(row: pd.Series) -> bool:
        """조리단계(RECIPE_DATA) 결측 또는 유효 단계 없음."""
        return not bool(build_recipe_steps(row.get("RECIPE_DATA")))

    # ponytail: 드랍 조건 추가 시 (사유, row→드랍 여부) 튜플을 append
    drop_checks: list[tuple[str, Callable[[pd.Series], bool]]] = [
        ("missing_cooking_steps", _missing_cooking_steps),
    ]

    before = len(df)
    drop_mask = pd.Series(False, index=df.index)

    for reason, should_drop in drop_checks:
        mask = df.apply(should_drop, axis=1)
        if not mask.any():
            continue
        for _, row in df.loc[mask].iterrows():
            logger.warning(
                "적재 제외 [%s] RCP_SNO=%s title=%s",
                reason,
                row["RCP_SNO"],
                row.get("CKG_NM", ""),
            )
        drop_mask |= mask

    kept = df.loc[~drop_mask].reset_index(drop=True)
    logger.info("적재 대상 필터: %d → %d (제외 %d건)", before, len(kept), before - len(kept))
    return kept


def clear_recipe_tables(db: PostgreDB) -> None:
    """기존 레시피 관련 데이터를 삭제한다."""
    for sql in (
        query.DELETE_RECOMMENDATION_RESULTS,
        query.DELETE_RECIPE_INGREDIENTS,
        query.DELETE_RECIPES,
    ):
        try:
            db.execute(sql)
        except psycopg.errors.UndefinedTable:
            table_name = sql.strip().split()[-1].rstrip(";")
            logger.warning("테이블 없음 — 삭제 건너뜀: %s", table_name)
    logger.info("기존 recipes / recipe_ingredients 데이터 삭제 완료")


def collect_unique_ingredients(df: pd.DataFrame) -> dict[str, str]:
    """normalized_name → 표시명 매핑을 수집한다."""
    unique: dict[str, str] = {}
    for raw_value in df["CKG_MTRL_CN"]:
        for ingredient in parse_ingredient_rows(raw_value):
            if not ingredient:
                continue
            raw_name = str(ingredient[0])
            resolved = resolve_ingredient_name(raw_name)
            if not resolved:
                continue
            display_name = _clip(resolved[0], _VARCHAR_LIMITS["name"])
            normalized_name = _clip(resolved[1], _VARCHAR_LIMITS["normalized_name"])
            if not display_name or not normalized_name:
                continue
            unique.setdefault(normalized_name, display_name)
    return unique


def upsert_ingredients(db: PostgreDB, unique_ingredients: dict[str, str]) -> dict[str, int]:
    """ingredients 마스터를 upsert하고 normalized_name → id 캐시를 반환한다."""
    cache: dict[str, int] = {}
    for normalized_name, display_name in tqdm(
        unique_ingredients.items(),
        desc="ingredients upsert",
    ):
        row = db.fetch_one(
            query.UPSERT_INGREDIENT,
            {"name": display_name, "normalized_name": normalized_name},
        )
        cache[normalized_name] = int(row[0])
    return cache


def build_recipe_row(row: pd.Series) -> dict[str, Any]:
    """recipes 테이블 INSERT 파라미터를 만든다."""
    recipe_id = int(row["RCP_SNO"])
    recipe_steps = build_recipe_steps(row.get("RECIPE_DATA"))
    return {
        "id": recipe_id,
        "title": _clip(row["CKG_NM"], _VARCHAR_LIMITS["title"]) or "이름없음",
        "description": None,
        "category": _clip(row.get("CKG_KND_ACTO_NM"), _VARCHAR_LIMITS["category"]),
        "serving_size": parse_serving_size(row.get("CKG_INBUN_NM")),
        "cooking_time": parse_cooking_time_minutes(row.get("CKG_TIME_NM")),
        "difficulty": _clip(row.get("CKG_DODF_NM"), _VARCHAR_LIMITS["difficulty"]),
        "image_url": extract_image_url(row.get("RECIPE_DATA")),
        "source_url": _clip(row.get("RECIPE_URL"), _VARCHAR_LIMITS["source_url"]),
        "recipe_steps": serialize_recipe_steps(recipe_steps),
    }


def build_recipe_ingredient_rows(
    row: pd.Series,
    ingredient_cache: dict[str, int],
) -> list[dict[str, Any]]:
    """recipe_ingredients 테이블 INSERT 파라미터 목록을 만든다."""
    recipe_id = int(row["RCP_SNO"])
    ingredient_rows = parse_ingredient_rows(row.get("CKG_MTRL_CN"))
    params: list[dict[str, Any]] = []

    for index, ingredient in enumerate(ingredient_rows):
        if len(ingredient) < 1:
            continue
        raw_name = str(ingredient[0])
        quantity = parse_quantity(ingredient[1]) if len(ingredient) > 1 else None
        unit = _clip(ingredient[2], _VARCHAR_LIMITS["unit"]) if len(ingredient) > 2 else None

        resolved = resolve_ingredient_name(raw_name)
        if not resolved:
            continue
        normalized_name = _clip(resolved[1], _VARCHAR_LIMITS["normalized_name"])
        if not normalized_name:
            continue
        ingredient_id = ingredient_cache.get(normalized_name)
        if ingredient_id is None:
            continue

        params.append(
            {
                "recipe_id": recipe_id,
                "ingredient_id": ingredient_id,
                "raw_ingredient_name": _clip(raw_name.strip(), _VARCHAR_LIMITS["raw_ingredient_name"]),
                "required_quantity": quantity,
                "unit": unit,
                "is_main_ingredient": index == 0,
            }
        )

    return params


def load_recipes_to_postgres(recipe_csv: str, cooking_steps_csv: str) -> None:
    """CSV 데이터를 recipes / recipe_ingredients 테이블에 적재한다."""
    db = PostgreDB()
    validate_schema(db)

    df = load_dataframes(recipe_csv, cooking_steps_csv)
    df = drop_invalid_rows(df)

    clear_recipe_tables(db)

    unique_ingredients = collect_unique_ingredients(df)
    logger.info("고유 재료 수: %d", len(unique_ingredients))
    ingredient_cache = upsert_ingredients(db, unique_ingredients)

    recipe_params: list[dict[str, Any]] = []
    recipe_ingredient_params: list[dict[str, Any]] = []

    for _, row in tqdm(df.iterrows(), total=len(df), desc="레시피 변환"):
        recipe_params.append(build_recipe_row(row))
        recipe_ingredient_params.extend(build_recipe_ingredient_rows(row, ingredient_cache))

    logger.info("recipes 적재 시작: %d건", len(recipe_params))
    for params in tqdm(recipe_params, desc="recipes 적재"):
        db.execute(query.UPSERT_RECIPE, params)

    logger.info("recipe_ingredients 적재 시작: %d건", len(recipe_ingredient_params))
    db.executemany(query.INSERT_RECIPE_INGREDIENT, recipe_ingredient_params)

    db.execute(query.SYNC_RECIPES_ID_SEQUENCE)

    logger.info(
        "적재 완료 — recipes: %d건, recipe_ingredients: %d건, ingredients: %d건",
        len(recipe_params),
        len(recipe_ingredient_params),
        len(ingredient_cache),
    )


if __name__ == "__main__":
    from .config import COOKING_STEPS_CSV, RECIPE_FIX_CSV

    _df = load_dataframes(str(RECIPE_FIX_CSV), str(COOKING_STEPS_CSV))
    _filtered = drop_invalid_rows(_df)
    assert _filtered["RCP_SNO"].isin([7029209, 7035727]).sum() == 0
    assert len(_filtered) == len(_df) - 2
