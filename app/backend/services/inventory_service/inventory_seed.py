import logging

from sqlalchemy.orm import Session

from app.backend.db.models import Ingredient, IngredientStorageStandard
from app.backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 자주 등록되는 식재료는 최초 등록 지연을 줄이기 위해 보관 기준 캐시에 미리 넣어둡니다.
# 데이터가 쌓이고 나중에 수정 예정
COMMON_INGREDIENT_STORAGE_STANDARDS = [
    {"name": "계란", "category": "유제품", "unit": "개", "days": {"냉장": 21, "냉동": 60, "실온": 7}},
    {"name": "달걀", "category": "유제품", "unit": "개", "days": {"냉장": 21, "냉동": 60, "실온": 7}},
    {"name": "우유", "category": "유제품", "unit": "개", "days": {"냉장": 7, "냉동": 30, "실온": 1}},
    {"name": "두부", "category": "가공식품", "unit": "개", "days": {"냉장": 5, "냉동": 30, "실온": 1}},
    {"name": "김치", "category": "발효식품", "unit": "개", "days": {"냉장": 45, "냉동": 180, "실온": 2}},
    {"name": "양파", "category": "채소", "unit": "개", "days": {"냉장": 14, "냉동": 90, "실온": 30}},
    {"name": "대파", "category": "채소", "unit": "개", "days": {"냉장": 7, "냉동": 90, "실온": 2}},
    {"name": "마늘", "category": "채소", "unit": "개", "days": {"냉장": 30, "냉동": 180, "실온": 30}},
    {"name": "감자", "category": "채소", "unit": "개", "days": {"냉장": 14, "냉동": 90, "실온": 30}},
    {"name": "당근", "category": "채소", "unit": "개", "days": {"냉장": 14, "냉동": 90, "실온": 3}},
    {"name": "양배추", "category": "채소", "unit": "개", "days": {"냉장": 14, "냉동": 90, "실온": 3}},
    {"name": "상추", "category": "채소", "unit": "개", "days": {"냉장": 5, "냉동": 30, "실온": 1}},
    {"name": "오이", "category": "채소", "unit": "개", "days": {"냉장": 7, "냉동": 30, "실온": 2}},
    {"name": "애호박", "category": "채소", "unit": "개", "days": {"냉장": 5, "냉동": 90, "실온": 1}},
    {"name": "토마토", "category": "채소", "unit": "개", "days": {"냉장": 7, "냉동": 90, "실온": 3}},
    {"name": "버섯", "category": "채소", "unit": "개", "days": {"냉장": 5, "냉동": 90, "실온": 1}},
    {"name": "팽이버섯", "category": "채소", "unit": "개", "days": {"냉장": 5, "냉동": 90, "실온": 1}},
    {"name": "깻잎", "category": "채소", "unit": "개", "days": {"냉장": 5, "냉동": 30, "실온": 1}},
    {"name": "고추", "category": "채소", "unit": "개", "days": {"냉장": 7, "냉동": 90, "실온": 2}},
    {"name": "사과", "category": "과일", "unit": "개", "days": {"냉장": 30, "냉동": 90, "실온": 7}},
    {"name": "바나나", "category": "과일", "unit": "개", "days": {"냉장": 7, "냉동": 90, "실온": 3}},
    {"name": "치즈", "category": "유제품", "unit": "개", "days": {"냉장": 14, "냉동": 60, "실온": 1}},
    {"name": "고추장", "category": "조미료", "unit": "개", "days": {"냉장": 180, "냉동": 365, "실온": 60}},
    {"name": "된장", "category": "조미료", "unit": "개", "days": {"냉장": 180, "냉동": 365, "실온": 60}},
    {"name": "간장", "category": "조미료", "unit": "개", "days": {"냉장": 180, "냉동": 365, "실온": 60}},
    {"name": "소고기", "category": "육류", "unit": "kg", "days": {"냉장": 3, "냉동": 180, "실온": 1}},
    {"name": "돼지고기", "category": "육류", "unit": "kg", "days": {"냉장": 3, "냉동": 180, "실온": 1}},
    {"name": "닭고기", "category": "육류", "unit": "kg", "days": {"냉장": 2, "냉동": 180, "실온": 1}},
    {"name": "삼겹살", "category": "육류", "unit": "kg", "days": {"냉장": 3, "냉동": 180, "실온": 1}},
    {"name": "고등어", "category": "수산물", "unit": "개", "days": {"냉장": 2, "냉동": 90, "실온": 1}},
    {"name": "새우", "category": "수산물", "unit": "kg", "days": {"냉장": 2, "냉동": 90, "실온": 1}},
    {"name": "오징어", "category": "수산물", "unit": "개", "days": {"냉장": 2, "냉동": 90, "실온": 1}},
    {"name": "멸치", "category": "수산물", "unit": "kg", "days": {"냉장": 180, "냉동": 365, "실온": 90}},
    {"name": "쌀", "category": "곡류", "unit": "kg", "days": {"냉장": 180, "냉동": 365, "실온": 180}},
    {"name": "참치캔", "category": "가공식품", "unit": "개", "days": {"냉장": 365, "냉동": 365, "실온": 730}},
    {"name": "얼음", "category": "기타", "unit": "개", "days": {"냉장": 730, "냉동": 730, "실온": 730}},
]


def _normalize_ingredient_name(name: str) -> str:
    """식재료명 중복 생성을 막기 위해 공백과 대소문자를 정규화합니다."""
    return name.strip().replace(" ", "").lower()


def _get_or_create_seed_ingredient(db: Session, seed: dict) -> tuple[Ingredient, bool]:
    """시드 식재료를 조회하고 없으면 새로 생성합니다."""
    normalized_name = _normalize_ingredient_name(seed["name"])
    ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized_name).first()
    if ingredient:
        # 기존 값이 비어 있거나 기본값 기타면 시드의 대표 카테고리로 보정합니다.
        if not ingredient.category or (ingredient.category == "기타" and seed["category"] != "기타"):
            ingredient.category = seed["category"]
        if not ingredient.default_unit:
            ingredient.default_unit = seed["unit"]
        return ingredient, False

    ingredient = Ingredient(
        name=seed["name"],
        normalized_name=normalized_name,
        category=seed["category"],
        default_unit=seed["unit"],
    )
    db.add(ingredient)
    db.flush()
    return ingredient, True


def seed_common_inventory_standards() -> tuple[int, int]:
    """자주 쓰는 식재료의 보관 기준 캐시를 없을 때만 미리 생성합니다."""
    db = SessionLocal()
    created_ingredients = 0
    created_standards = 0

    try:
        for seed in COMMON_INGREDIENT_STORAGE_STANDARDS:
            ingredient, was_created = _get_or_create_seed_ingredient(db, seed)
            created_ingredients += int(was_created)

            for storage_location, lifespan_days in seed["days"].items():
                exists = (
                    db.query(IngredientStorageStandard)
                    .filter(
                        IngredientStorageStandard.ingredient_id == ingredient.id,
                        IngredientStorageStandard.storage_location == storage_location,
                    )
                    .first()
                )
                if exists:
                    continue

                db.add(
                    IngredientStorageStandard(
                        ingredient_id=ingredient.id,
                        storage_location=storage_location,
                        lifespan_days=lifespan_days,
                    )
                )
                created_standards += 1

        db.commit()
        return created_ingredients, created_standards
    except Exception:
        db.rollback()
        logger.exception("자주 쓰는 식재료 보관 기준 시드 생성 실패")
        raise
    finally:
        db.close()
