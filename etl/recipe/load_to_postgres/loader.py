"""레시피 CSV → PostgreSQL 적재."""

from __future__ import annotations

import ast
import json
import logging
import re
from fractions import Fraction
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
    # backend runtime (inventory / recommend)
    "fridge_items": ("is_ai_recommended",),
}

_RECIPE_175_COLUMNS = {
    "recipe_code",
    "recipe_name",
    "menu_category",
    "serving_size",
    "ingredient_names",
    "ingredient_amounts",
    "ingredient_count",
    "total_time_minutes",
    "difficulty",
    "step_count",
    "cooking_steps",
    "step_times",
    "heat_levels",
    "main_ingredients",
    "main_image_url",
    "step_image_urls",
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
_AMOUNT_HINT = r"(?:적당량|적당히|넉넉하게|넉넉히|원하는만큼|약간|톡톡|넉넉|솔솔|조금|듬뿍)"
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
    "약간 톡톡 조금 적당량 적당히 넉넉 넉넉히 넉넉하게 솔솔 원하는만큼 듬뿍".split()
)
# ponytail: 정규화 규칙은 이 파일에서만 관리한다.
# 단순 오타·표기 흔들림은 clean_ingredient_name()에서 순차 적용한다.
_TYPO_REWRITES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"크린베리"), "크랜베리"),
    (re.compile(r"고은"), "고운"),
    (re.compile(r"그라노파다노"), "그라나파다노"),
    (re.compile(r"줄거리"), "줄기"),
    (re.compile(r"핫케익"), "핫케이크"),
    (re.compile(r"파인애풀"), "파인애플"),
    (re.compile(r"고추가루"), "고춧가루"),
    (re.compile(r"청양고추가루"), "청양고춧가루"),
    (re.compile(r"계핏가루"), "계피가루"),
    (re.compile(r"들깻가루"), "들깨가루"),
    (re.compile(r"쇠고기"), "소고기"),
)

_PREFIX_PATTERNS = (
    r"^다진\s+",
    r"^다진(?=[가-힣])",
    r"^손질한\s*",
    r"^손질\s+",
    r"^냉동\s*",
)

_STATE_SUFFIX_PATTERNS = (
    r"\s+손질\s*후$",
    r"\s+데치기용$",
    r"\s+간것$",
    r"\s+간\s*것$",
    r"\s+크게$",
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
    (re.compile(r"^파마산\s*치즈(?:\s*가루)?$"), "파마산치즈"),
    (re.compile(r"^참치\s*(?:캔|통조림)$"), "참치"),
    (re.compile(r"^캔\s*참치$"), "참치"),
    (re.compile(r"^고추참치\s*캔$"), "고추참치"),
    (re.compile(r"^옥수수\s*캔$"), "옥수수"),
    (re.compile(r"^캔\s*옥수수$"), "옥수수"),
    (re.compile(r"^통조림\s*옥수수$"), "옥수수"),
    (re.compile(r"^고등어\s*통조림$"), "고등어"),
    (re.compile(r"^꽁치\s*통조림$"), "꽁치"),
    (re.compile(r"^파인애플\s*통조림$"), "파인애플"),
    (re.compile(r"^토마토\s*캔$"), "토마토"),
    (re.compile(r"^홀\s*토마토\s*캔$"), "홀토마토"),
    (re.compile(r"^건\s*표고(?:\s*버섯)?(?:\s*슬라이스)?$"), "건표고버섯"),
    (re.compile(r"^슬라이스\s*건\s*표고$"), "건표고버섯"),
    (re.compile(r"^채\s*썬\s*건\s*표고버섯$"), "건표고버섯"),
    (re.compile(r"^고춧가루\s*스프$"), "고춧가루"),
    (re.compile(r"^청양\s*고춧가루$"), "청양고춧가루"),
    (re.compile(r"^핫케이크\s*가루$"), "핫케이크가루"),
    (re.compile(r"^중력\s*밀가루$"), "밀가루 중력분"),
    (re.compile(r"^파\s*$"), "대파"),
    (re.compile(r"^대파\s*or\s*쪽파$"), "대파"),
)
# ponytail: 이름 필드에 붙은 분량만 제거. 영문+숫자+한글 브랜드명(A1스테이크소스)은 유지.
_EMBEDDED_QUANTITY = re.compile(r"(?:\s+\d|(?<=[가-힣])\d)")


def clean_ingredient_name(name: str) -> str | None:
    """크롤 artifact(?), 이름 내 분량(숫자·크기 수식어) 제거 후 표시용 재료명."""
    text = str(name).strip()
    if not text:
        return None
    text = re.sub(r"^[\s?]+", "", text)
    text = re.sub(r"[\s?]+$", "", text)
    if not text or text == "?":
        return None
    text = _EMBEDDED_QUANTITY.split(text, maxsplit=1)[0].strip()
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
    for pattern, replacement in _TYPO_REWRITES:
        text = pattern.sub(replacement, text)

    changed = True
    while changed:
        changed = False
        for pattern in _PREFIX_PATTERNS:
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True
        for pattern in _STATE_SUFFIX_PATTERNS:
            new = re.sub(pattern, "", text).strip()
            if new != text:
                text = new
                changed = True

    text = re.sub(r"전분\s*가루", "전분", text).strip()
    for pattern, canonical in _CANONICAL_REWRITES:
        if pattern.fullmatch(text):
            text = canonical
            break
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


def parse_json_array(value: Any, column_name: str) -> list[Any]:
    """CSV의 JSON 배열 문자열을 파싱하고 컬럼 오류를 명확히 알린다."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return value
    try:
        parsed = json.loads(str(value))
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"{column_name}은 JSON 배열이어야 합니다: {value!r}") from exc
    if not isinstance(parsed, list):
        raise ValueError(f"{column_name}은 JSON 배열이어야 합니다: {value!r}")
    return parsed


def parse_recipe_id(recipe_code: Any) -> int:
    """R0001 형식의 신규 코드를 기존 BIGINT PK에 사용할 숫자 1로 변환한다."""
    match = re.fullmatch(r"R(\d{4})", str(recipe_code).strip())
    if not match:
        raise ValueError(f"recipe_code 형식이 올바르지 않습니다: {recipe_code!r}")
    recipe_id = int(match.group(1))
    if recipe_id <= 0:
        raise ValueError(f"recipe_code는 1 이상의 ID여야 합니다: {recipe_code!r}")
    return recipe_id


def parse_amount(value: Any) -> tuple[float | None, str | None]:
    """`1개(180g)`, `10ml`, `1/4개`, `약간`에서 대표 수량과 단위를 추출한다."""
    text = str(value).strip()
    if not text:
        return None, None
    match = re.match(r"^(\d+(?:\.\d+)?|\d+/\d+)\s*([a-zA-Z가-힣]+)", text)
    if not match:
        return None, _clip(text, _VARCHAR_LIMITS["unit"])
    quantity = parse_quantity(match.group(1))
    unit = _clip(match.group(2), _VARCHAR_LIMITS["unit"])
    return quantity, unit


def build_recipe_steps_from_row(row: pd.Series) -> list[dict[str, Any]]:
    """recipe_175의 단계·시간·불 세기를 기존 recipe_steps JSON 구조로 합친다."""
    texts = parse_json_array(row.get("cooking_steps"), "cooking_steps")
    times = parse_json_array(row.get("step_times"), "step_times")
    heat_levels = parse_json_array(row.get("heat_levels"), "heat_levels")
    image_urls = parse_json_array(row.get("step_image_urls"), "step_image_urls")
    expected = int(row.get("step_count") or 0)

    if not (len(texts) == len(times) == len(heat_levels) == expected):
        raise ValueError(
            f"{row.get('recipe_code')}: 조리단계 개수 불일치 "
            f"steps={len(texts)}, times={len(times)}, heat={len(heat_levels)}, expected={expected}"
        )

    steps: list[dict[str, Any]] = []
    for index, text in enumerate(texts):
        image_url = image_urls[index] if index < len(image_urls) else None
        steps.append(
            {
                "step_no": index + 1,
                "title": f"{index + 1}단계",
                "text": str(text),
                "time": str(times[index]),
                "heat_level": str(heat_levels[index]),
                "image_url": _clip(image_url, _VARCHAR_LIMITS["image_url"]),
            }
        )
    return steps


def load_dataframe(recipe_csv: str) -> pd.DataFrame:
    """recipe_175 CSV를 읽고 필수 컬럼과 행 단위 구조를 검증한다."""
    df = pd.read_csv(recipe_csv, encoding="utf-8-sig", keep_default_na=False)
    missing = sorted(_RECIPE_175_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"recipe_175 필수 컬럼이 없습니다: {', '.join(missing)}")
    if df.empty:
        raise ValueError("recipe_175 CSV에 적재할 행이 없습니다.")

    ids = df["recipe_code"].map(parse_recipe_id)
    if ids.duplicated().any():
        duplicates = df.loc[ids.duplicated(keep=False), "recipe_code"].tolist()
        raise ValueError(f"recipe_code 숫자 ID가 중복됩니다: {duplicates}")

    for _, row in df.iterrows():
        ingredient_names = parse_json_array(row.get("ingredient_names"), "ingredient_names")
        ingredient_amounts = parse_json_array(row.get("ingredient_amounts"), "ingredient_amounts")
        expected_ingredients = int(row.get("ingredient_count") or 0)
        if len(ingredient_names) != expected_ingredients or len(ingredient_amounts) != expected_ingredients:
            raise ValueError(
                f"{row.get('recipe_code')}: 재료 개수 불일치 "
                f"names={len(ingredient_names)}, amounts={len(ingredient_amounts)}, "
                f"expected={expected_ingredients}"
            )
        build_recipe_steps_from_row(row)

    logger.info("recipe_175 CSV 로드 및 검증: %s (%d행)", recipe_csv, len(df))
    return df.reset_index(drop=True)


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
    for raw_value in df["ingredient_names"]:
        for ingredient in parse_json_array(raw_value, "ingredient_names"):
            raw_name = str(ingredient)
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
    recipe_id = parse_recipe_id(row["recipe_code"])
    recipe_steps = build_recipe_steps_from_row(row)
    return {
        "id": recipe_id,
        "title": _clip(row["recipe_name"], _VARCHAR_LIMITS["title"]) or "이름없음",
        "description": None,
        "category": _clip(row.get("menu_category"), _VARCHAR_LIMITS["category"]),
        "serving_size": int(row["serving_size"]),
        "cooking_time": int(row["total_time_minutes"]),
        "difficulty": _clip(row.get("difficulty"), _VARCHAR_LIMITS["difficulty"]),
        "image_url": _clip(row.get("main_image_url"), _VARCHAR_LIMITS["image_url"]),
        "source_url": None,
        "recipe_steps": serialize_recipe_steps(recipe_steps),
    }


def build_recipe_ingredient_rows(
    row: pd.Series,
    ingredient_cache: dict[str, int],
) -> list[dict[str, Any]]:
    """recipe_ingredients 테이블 INSERT 파라미터 목록을 만든다."""
    recipe_id = parse_recipe_id(row["recipe_code"])
    ingredient_names = parse_json_array(row.get("ingredient_names"), "ingredient_names")
    ingredient_amounts = parse_json_array(row.get("ingredient_amounts"), "ingredient_amounts")
    main_ingredients = {
        normalize_ingredient_name(str(name))
        for name in parse_json_array(row.get("main_ingredients"), "main_ingredients")
    }
    params: list[dict[str, Any]] = []

    for raw_name_value, amount_value in zip(ingredient_names, ingredient_amounts, strict=True):
        raw_name = str(raw_name_value)
        quantity, unit = parse_amount(amount_value)

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
                "is_main_ingredient": normalize_ingredient_name(raw_name) in main_ingredients,
            }
        )

    return params


def load_recipes_to_postgres(recipe_csv: str) -> None:
    """CSV 데이터를 recipes / recipe_ingredients 테이블에 적재한다."""
    db = PostgreDB()
    validate_schema(db)

    df = load_dataframe(recipe_csv)

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
    from .config import RECIPE_175_CSV

    _df = load_dataframe(str(RECIPE_175_CSV))
    assert len(_df) == 175
    assert parse_recipe_id(_df.iloc[0]["recipe_code"]) == 1
    assert parse_recipe_id(_df.iloc[-1]["recipe_code"]) == 175
    assert build_recipe_row(_df.iloc[0])["image_url"] is None
