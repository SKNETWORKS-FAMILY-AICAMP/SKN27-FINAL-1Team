import logging
from decimal import Decimal
from datetime import date, datetime, timedelta
from typing import Optional, List
from fastapi import HTTPException, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient, IngredientAlias, IngredientStorageStandard
from app.backend.schemas.inventory import IngredientCreate

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = "냉장"
DEFAULT_CATEGORY = "기타"
STORAGE_KEYS = ("냉장", "냉동", "실온")
ACTIVE_STATUSES = ("normal", "expiring", "expired")


def _object_particle(word: str) -> str:
    """한국어 단어의 받침 여부에 맞는 목적격 조사를 반환합니다."""
    last = (word or "").strip()[-1:]
    if not last:
        return "를"
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3 and (code - 0xAC00) % 28:
        return "을"
    return "를"


class InventoryService:
    """냉장고 식재료 등록, 조회, 수정, 삭제와 소비기한 계산을 담당하는 서비스입니다."""

    def _parse_date(self, value: Optional[date]) -> Optional[date]:
        """문자열 또는 date 값을 date 타입으로 정규화합니다."""
        if value is None or isinstance(value, date):
            return value
        return datetime.strptime(value, "%Y-%m-%d").date()

    def _normalize_storage(self, storage_method: Optional[str]) -> str:
        """프론트 입력값을 DB에 저장할 보관 위치 값으로 정규화합니다."""
        if storage_method in STORAGE_KEYS:
            return storage_method
        return DEFAULT_STORAGE

    def _normalize_ingredient_name(self, name: str) -> str:
        """식재료 중복 등록을 줄이기 위해 이름을 비교용 문자열로 정규화합니다."""
        return name.strip().replace(" ", "").lower()


    def _validate_ingredient_name(self, name: str) -> None:
        """식재료가 아닌 입력은 DB 저장 전에 차단합니다."""
        from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

        if not expiration_ai_service.is_valid_ingredient_name(name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="올바른 식재료 이름을 입력해주세요.")

    def _resolve_known_ingredient_name(self, db: Session, name: str) -> Optional[str]:
        """챗봇 등록 전 마스터/별칭 기준으로 식재료명을 확인합니다."""
        raw_name = (name or "").strip()
        normalized = self._normalize_ingredient_name(raw_name)
        if not normalized:
            return None

        ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
        if ingredient:
            return ingredient.name

        for alias in db.query(IngredientAlias).all():
            if self._normalize_ingredient_name(alias.alias_name) == normalized:
                return alias.ingredient.name if alias.ingredient else raw_name

        return None

    def _get_status_from_d_day(self, d_day: Optional[int]) -> str:
        """D-day 값을 냉장고 항목 상태값으로 변환합니다."""
        if d_day is None:
            return "normal"
        if d_day < 0:
            return "expired"
        if d_day <= 3:
            return "expiring"
        return "normal"

    def search_ingredient_suggestions(self, db: Session, keyword: str, limit: int = 6) -> list[str]:
        """입력한 키워드가 포함된 식재료 마스터명을 반환합니다."""
        normalized = self._normalize_ingredient_name(keyword)
        if not normalized:
            return []

        rows = (
            db.query(Ingredient.name)
            .filter(
                or_(
                    Ingredient.name.ilike(f"%{keyword.strip()}%"),
                    Ingredient.normalized_name.ilike(f"%{normalized}%"),
                )
            )
            .order_by(Ingredient.name.asc())
            .limit(limit)
            .all()
        )
        return [name for (name,) in rows]

    def get_recommended_lifespan(self, name: str, category: Optional[str], storage_method: str = DEFAULT_STORAGE) -> int:
        """AI 서비스에서 권장 보관 가능 일수를 가져오고 실패하면 기본 7일을 반환합니다."""
        try:
            from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

            _, days = expiration_ai_service.predict_storage_and_lifespan(name, category or "기타", storage_method)
            return max(int(days), 1)
        except Exception as exc:
            logger.warning("권장 보관 기간 계산 실패, 기본값을 사용합니다: %s", exc)
            return 7

    def _get_or_create_storage_rule(
        self,
        db: Session,
        ingredient: Ingredient,
        storage_method: Optional[str],
    ) -> tuple[str, int]:
        """식재료와 보관 위치 기준 보관 기간 캐시를 조회하거나 새로 생성합니다."""
        requested_storage = storage_method if storage_method in STORAGE_KEYS else None
        preferred_storage = requested_storage
        cached_rule = None

        if not preferred_storage:
            try:
                from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

                override = expiration_ai_service.get_ingredient_override_lifespan(ingredient.name, None)
                if override:
                    preferred_storage = override[0]
            except Exception as exc:
                logger.warning("권장 보관 위치 확인 실패: %s", exc)

        if preferred_storage:
            cached_rule = (
                db.query(IngredientStorageStandard)
                .filter(
                    IngredientStorageStandard.ingredient_id == ingredient.id,
                    IngredientStorageStandard.storage_location == preferred_storage,
                )
                .first()
            )
        else:
            cached_rule = (
                db.query(IngredientStorageStandard)
                .filter(IngredientStorageStandard.ingredient_id == ingredient.id)
                .first()
            )

        if cached_rule:
            try:
                from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

                override = expiration_ai_service.get_ingredient_override_lifespan(
                    ingredient.name,
                    cached_rule.storage_location,
                )
                if override and override[1] > cached_rule.lifespan_days:
                    cached_rule.lifespan_days = override[1]
                    db.flush()
                    return cached_rule.storage_location, cached_rule.lifespan_days
            except Exception as exc:
                logger.warning("보관 기간 캐시 보정 실패: %s", exc)
            return cached_rule.storage_location, cached_rule.lifespan_days

        try:
            from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

            predicted_storage, predicted_days = expiration_ai_service.predict_storage_and_lifespan(
                ingredient.name,
                ingredient.category or "기타",
                requested_storage,
            )
            final_storage = requested_storage or self._normalize_storage(predicted_storage)
            lifespan_days = max(int(predicted_days), 1)
        except Exception as exc:
            logger.warning("AI 보관 기간 예측 실패, 기본값을 사용합니다: %s", exc)
            final_storage = requested_storage or DEFAULT_STORAGE
            lifespan_days = 7

        try:
            with db.begin_nested():
                db.add(
                    IngredientStorageStandard(
                        ingredient_id=ingredient.id,
                        storage_location=final_storage,
                        lifespan_days=lifespan_days,
                    )
                )
                db.flush()
        except IntegrityError:
            existing_rule = (
                db.query(IngredientStorageStandard)
                .filter(
                    IngredientStorageStandard.ingredient_id == ingredient.id,
                    IngredientStorageStandard.storage_location == final_storage,
                )
                .first()
            )
            if existing_rule:
                return existing_rule.storage_location, existing_rule.lifespan_days
        except Exception as exc:
            logger.warning("보관 기간 캐시 저장 실패: %s", exc)

        return final_storage, lifespan_days

    def _calculate_expiration_info(
        self,
        expiry_date: Optional[date],
        purchased_date: Optional[date],
        ingredient: Ingredient,
        storage_location: Optional[str],
    ) -> dict:
        """소비기한 날짜, D-day, 임박/만료 여부를 계산합니다."""
        today = date.today()
        parsed_expiry = self._parse_date(expiry_date)
        parsed_purchase = self._parse_date(purchased_date) or today

        if parsed_expiry:
            target_date = parsed_expiry
        else:
            lifespan_days = self.get_recommended_lifespan(
                ingredient.name,
                ingredient.category,
                self._normalize_storage(storage_location),
            )
            target_date = parsed_purchase + timedelta(days=lifespan_days)

        d_day = (target_date - today).days
        return {
            "expiration_date": target_date,
            "d_day": d_day,
            "is_expired": d_day < 0,
            "is_expiring_soon": 0 <= d_day <= 3,
            "status": self._get_status_from_d_day(d_day),
        }

    def _sync_status(self, item: FridgeItem, calculated_status: str) -> bool:
        """계산된 상태와 DB 상태가 다르면 메모리 객체에 반영하고 변경 여부를 반환합니다."""
        if item.status != calculated_status:
            item.status = calculated_status
            return True
        return False

    def _map_to_response(self, item: FridgeItem, ingredient: Ingredient, is_ai_recommended: bool = False) -> dict:
        """FridgeItem과 Ingredient를 프론트엔드 응답 스키마로 변환합니다."""
        calc_info = self._calculate_expiration_info(
            expiry_date=item.expiry_date,
            purchased_date=item.purchased_date,
            ingredient=ingredient,
            storage_location=item.storage_location,
        )
        # DB 컬럼이 있으면 우선 사용, 없으면 파라미터 값 사용 (하위 호환성)
        ai_flag = getattr(item, 'is_ai_recommended', None)
        if ai_flag is None:
            ai_flag = is_ai_recommended
        return {
            "id": item.id,
            "fridge_id": item.id,
            "ingredient_id": getattr(ingredient, "id", 0),
            "receipt_item_id": getattr(item, "receipt_item_id", None),
            "name": item.display_name or ingredient.name,
            "category": ingredient.category or DEFAULT_CATEGORY,
            "quantity": float(item.quantity) if item.quantity is not None else 1.0,
            "unit": item.unit or ingredient.default_unit or "개",
            "storage_method": item.storage_location or DEFAULT_STORAGE,
            "purchase_date": item.purchased_date or date.today(),
            "expiration_date": item.expiry_date or calc_info["expiration_date"],
            "created_at": item.created_at,
            "updated_at": item.created_at,
            "d_day": calc_info["d_day"],
            "is_expiring_soon": calc_info["is_expiring_soon"],
            "is_expired": calc_info["is_expired"],
            "status": calc_info["status"],
            "is_ai_recommended": bool(ai_flag),
        }

    def _get_or_create_ingredient(self, db: Session, data: IngredientCreate) -> Ingredient:
        """식재료 마스터를 조회하고 없으면 새로 생성합니다."""
        self._validate_ingredient_name(data.name)
        normalized = self._normalize_ingredient_name(data.name)
        ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
        incoming_category = data.category if data.category and data.category != DEFAULT_CATEGORY else None
        if ingredient:
            # 기본값 기타는 식재료 마스터의 기존 카테고리를 덮어쓰지 않습니다.
            if incoming_category and ingredient.category != incoming_category:
                ingredient.category = incoming_category
                db.flush()
            return ingredient

        try:
            with db.begin_nested():
                ingredient = Ingredient(
                    name=data.name.strip(),
                    normalized_name=normalized,
                    category=incoming_category or data.category,
                    default_unit=data.unit,
                )
                db.add(ingredient)
                db.flush()
                return ingredient
        except IntegrityError:
            ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
            if ingredient:
                return ingredient
            raise

    def _resolve_item_dates_and_storage(self, db: Session, ingredient: Ingredient, data: IngredientCreate) -> tuple[str, date, bool]:
        """요청값과 AI/캐시 기준으로 보관 위치와 소비기한을 확정합니다.
        반환값: (storage_location, expiration_date, is_ai_recommended)
        """
        purchase_date = self._parse_date(data.purchase_date) or date.today()
        expiration_date = self._parse_date(data.expiration_date)

        if expiration_date:
            storage_location, _ = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
            return storage_location, expiration_date, False

        storage_location, lifespan_days = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
        return storage_location, purchase_date + timedelta(days=lifespan_days), True

    def add_ingredient(self, db: Session, user_id: int, data: IngredientCreate, *, commit: bool = True):
        """사용자 냉장고에 식재료를 추가합니다."""
        ingredient = self._get_or_create_ingredient(db, data)
        storage_location, expiration_date, is_ai_recommended = self._resolve_item_dates_and_storage(db, ingredient, data)
        purchase_date = self._parse_date(data.purchase_date) or date.today()
        d_day = (expiration_date - date.today()).days

        fridge_item = FridgeItem(
            user_id=user_id,
            ingredient_id=ingredient.id,
            display_name=data.name.strip(),
            quantity=data.quantity,
            unit=data.unit,
            storage_location=storage_location,
            purchased_date=purchase_date,
            expiry_date=expiration_date,
            status=self._get_status_from_d_day(d_day),
            is_ai_recommended=is_ai_recommended,
        )
        db.add(fridge_item)
        if commit:
            db.commit()
        else:
            db.flush()
        db.refresh(fridge_item)
        return self._map_to_response(fridge_item, ingredient)

    def get_ingredients(self, db: Session, user_id: int):
        """사용자 냉장고의 활성 식재료 목록을 조회합니다."""
        items = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(FridgeItem.user_id == user_id, FridgeItem.status.in_(ACTIVE_STATUSES))
            .all()
        )

        results = []
        status_changed = False
        for fridge_item, ingredient in items:
            mapped = self._map_to_response(fridge_item, ingredient)
            status_changed = self._sync_status(fridge_item, mapped["status"]) or status_changed
            results.append(mapped)

        if status_changed:
            db.commit()

        return results

    def delete_ingredient(self, db: Session, user_id: int, ingredient_id: int):
        """사용자 냉장고에서 식재료를 삭제합니다."""
        fridge_item = (
            db.query(FridgeItem)
            .filter(FridgeItem.id == ingredient_id, FridgeItem.user_id == user_id)
            .first()
        )
        if not fridge_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")

        fridge_item.status = "used"
        db.commit()

    def delete_ingredients_bulk(self, db: Session, user_id: int, ingredient_ids: List[int]):
        """사용자 냉장고에서 여러 식재료를 한 번에 삭제(폐기)합니다."""
        if not ingredient_ids:
            return

        fridge_items = (
            db.query(FridgeItem)
            .filter(FridgeItem.id.in_(ingredient_ids), FridgeItem.user_id == user_id)
            .all()
        )

        for item in fridge_items:
            item.status = "used"
        
        db.commit()


    def update_ingredient(self, db: Session, user_id: int, ingredient_id: int, data: IngredientCreate):
        """사용자 냉장고 식재료 정보를 수정합니다."""
        fridge_item = (
            db.query(FridgeItem)
            .filter(FridgeItem.id == ingredient_id, FridgeItem.user_id == user_id)
            .first()
        )
        if not fridge_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")

        # 이름이 변경되었는데 프론트엔드에서 보낸 날짜가 기존 날짜와 동일하다면 (수동 변경이 아니라면) 새 재료 기준으로 자동 재계산하도록 유도합니다.
        if fridge_item.display_name != data.name.strip() and self._parse_date(data.expiration_date) == fridge_item.expiry_date:
            data.expiration_date = None

        # 수정된 재료명 기준으로 식재료 마스터를 다시 매핑합니다.
        ingredient = self._get_or_create_ingredient(db, data)
        storage_location, expiration_date, is_ai_recommended = self._resolve_item_dates_and_storage(db, ingredient, data)
        purchase_date = self._parse_date(data.purchase_date) or date.today()
        d_day = (expiration_date - date.today()).days

        fridge_item.ingredient_id = ingredient.id
        fridge_item.display_name = data.name.strip()
        fridge_item.quantity = data.quantity
        fridge_item.unit = data.unit
        fridge_item.storage_location = storage_location
        fridge_item.purchased_date = purchase_date
        fridge_item.expiry_date = expiration_date
        fridge_item.status = self._get_status_from_d_day(d_day)
        fridge_item.is_ai_recommended = is_ai_recommended

        db.commit()
        db.refresh(fridge_item)
        return self._map_to_response(fridge_item, ingredient)

    def get_inventory_summary(self, db: Session, user_id: int):
        """사용자 냉장고의 개수, 임박/만료, 보관 위치 요약을 계산합니다."""
        items = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(FridgeItem.user_id == user_id, FridgeItem.status.in_(ACTIVE_STATUSES))
            .all()
        )

        today = date.today()
        summary = {
            "total": len(items),
            "expiring_soon": 0,
            "expired": 0,
            "today_added": 0,
            "storage": {"냉장": 0, "냉동": 0, "실온": 0, "기타": 0},
        }

        status_changed = False
        for fridge_item, ingredient in items:
            mapped = self._map_to_response(fridge_item, ingredient)
            status_changed = self._sync_status(fridge_item, mapped["status"]) or status_changed

            if mapped["is_expired"]:
                summary["expired"] += 1
            elif mapped["is_expiring_soon"]:
                summary["expiring_soon"] += 1

            if fridge_item.purchased_date == today:
                summary["today_added"] += 1

            storage_key = fridge_item.storage_location if fridge_item.storage_location in STORAGE_KEYS else "기타"
            summary["storage"][storage_key] += 1

        if status_changed:
            db.commit()

        return summary
        
    def add_ingredient_by_name(self, db: Session, user_id: int, ingredient_name: str, quantity: float, storage_method: Optional[str] = None, *, commit: bool = True) -> str:
        """챗봇 Tool에서 받은 식재료 이름과 수량으로 실제 냉장고에 재료를 추가합니다."""
        resolved_name = self._resolve_known_ingredient_name(db, ingredient_name)
        if not resolved_name:
            return "올바른 식재료명을 입력해주세요."

        data = IngredientCreate(
            name=resolved_name,
            category=None,
            quantity=quantity or 1.0,
            unit="개",
            storage_method=storage_method,
        )
        item = self.add_ingredient(db, user_id, data, commit=commit)
        display_quantity = int(item["quantity"]) if float(item["quantity"]).is_integer() else item["quantity"]
        return f"{item['name']}{_object_particle(item['name'])} {display_quantity}{item['unit']} {item['storage_method']}에 추가했어요."

    def add_ingredient_unchecked_by_name(self, db: Session, user_id: int, ingredient_name: str, quantity: float, storage_method: Optional[str] = None, *, commit: bool = True) -> str:
        """사용자가 확인한 마스터 미등록 식재료를 냉장고에 추가합니다."""
        data = IngredientCreate(
            name=ingredient_name.strip(),
            category=None,
            quantity=quantity or 1.0,
            unit="개",
            storage_method=storage_method,
        )
        item = self.add_ingredient(db, user_id, data, commit=commit)
        display_quantity = int(item["quantity"]) if float(item["quantity"]).is_integer() else item["quantity"]
        return f"{item['name']}{_object_particle(item['name'])} {display_quantity}{item['unit']} {item['storage_method']}에 추가했어요."

    def _find_items_by_name(self, items, ingredient_name: str):
        """챗봇 쓰기 작업에서 식재료명이 정확히 일치하는 활성 항목만 반환합니다."""
        target = self._normalize_ingredient_name(ingredient_name)
        matches = []
        for fridge_item, ingredient in items:
            names = [fridge_item.display_name, ingredient.name, ingredient.normalized_name]
            normalized_names = [self._normalize_ingredient_name(name) for name in names if name]
            if target in normalized_names:
                matches.append(fridge_item)
        return matches

    def _find_item_by_name(self, items, ingredient_name: str):
        """챗봇에서 받은 이름과 가장 먼저 일치하는 냉장고 항목을 반환합니다."""
        matches = self._find_items_by_name(items, ingredient_name)
        return matches[0] if matches else None
    def get_total_quantity_by_name(self, db: Session, user_id: int, ingredient_name: str) -> float:

        """사용자의 활성 냉장고 항목에서 동일 식재료의 총수량을 반환합니다."""
        items = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(FridgeItem.user_id == user_id, FridgeItem.status.in_(ACTIVE_STATUSES))
            .all()
        )
        matches = self._find_items_by_name(items, ingredient_name)
        if not matches:
            resolved_name = self._resolve_known_ingredient_name(db, ingredient_name)
            matches = self._find_items_by_name(items, resolved_name) if resolved_name else []
        total = sum(
            (Decimal(str(item.quantity or 1)) for item in matches),
            Decimal("0"),
        )
        return float(total)


    def delete_ingredient_by_name(self, db: Session, user_id: int, ingredient_name: str) -> str:
        """챗봇에서 식재료 이름을 받아 냉장고 항목을 폐기 처리합니다."""
        # ponytail: 사용자별 재고 전체를 잠급니다. 동시 쓰기량이 커지면 대상 식재료 행만 잠그도록 좁힙니다.
        items = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(FridgeItem.user_id == user_id, FridgeItem.status.in_(ACTIVE_STATUSES))
            .order_by(FridgeItem.id)
            .with_for_update(of=FridgeItem)
            .all()
        )
        target_item = self._find_item_by_name(items, ingredient_name)
        if not target_item:
            resolved_name = self._resolve_known_ingredient_name(db, ingredient_name)
            target_item = self._find_item_by_name(items, resolved_name) if resolved_name else None
        if not target_item:
            return f"냉장고에서 {ingredient_name}{_object_particle(ingredient_name)} 찾을 수 없어요. 이미 다 쓰셨거나 등록되지 않았을 수 있습니다."
        target_item.status = "used"
        db.commit()
        return f"{ingredient_name}{_object_particle(ingredient_name)} 폐기 처리했어요."

    def discard_ingredient_by_name(self, db: Session, user_id: int, ingredient_name: str, quantity: float) -> str:
        """동일 재료에서 요청 수량만큼 폐기하고 폐기 결과 문구를 반환합니다."""
        reply = self.consume_ingredient_by_name(db, user_id, ingredient_name, quantity)
        return reply.replace("소비 처리", "폐기 처리")


    def consume_ingredient_by_name(self, db: Session, user_id: int, ingredient_name: str, quantity: float) -> str:
        """동일 재료의 여러 입고 건에서 요청 수량만큼 소비 처리합니다."""
        # ponytail: 사용자별 재고 전체를 잠급니다. 동시 쓰기량이 커지면 대상 식재료 행만 잠그도록 좁힙니다.
        items = (
            db.query(FridgeItem, Ingredient)
            .join(Ingredient, FridgeItem.ingredient_id == Ingredient.id)
            .filter(FridgeItem.user_id == user_id, FridgeItem.status.in_(ACTIVE_STATUSES))
            .order_by(FridgeItem.id)
            .with_for_update(of=FridgeItem)
            .all()
        )
        target_items = self._find_items_by_name(items, ingredient_name)
        if not target_items:
            resolved_name = self._resolve_known_ingredient_name(db, ingredient_name)
            target_items = self._find_items_by_name(items, resolved_name) if resolved_name else []
        if not target_items:
            return f"냉장고에서 {ingredient_name}{_object_particle(ingredient_name)} 찾을 수 없어요. 이미 다 쓰셨거나 등록되지 않았을 수 있습니다."

        consume_qty = Decimal(str(quantity or 1))
        if consume_qty <= 0:
            return "소비 수량은 0보다 크게 입력해주세요."

        # 소비기한이 가까운 입고 건부터 차감합니다.
        target_items.sort(key=lambda item: (getattr(item, "expiry_date", None) is None, getattr(item, "expiry_date", None) or date.max))
        total_quantity = sum((Decimal(str(item.quantity or 1)) for item in target_items), Decimal("0"))
        remaining_to_consume = min(consume_qty, total_quantity)
        actual_consumed = remaining_to_consume

        for target_item in target_items:
            if remaining_to_consume <= 0:
                break
            current_qty = Decimal(str(target_item.quantity or 1))
            if remaining_to_consume >= current_qty:
                target_item.status = "used"
                remaining_to_consume -= current_qty
            else:
                target_item.quantity = current_qty - remaining_to_consume
                remaining_to_consume = Decimal("0")

        db.commit()
        remaining_total = total_quantity - actual_consumed
        display_consumed = int(actual_consumed) if actual_consumed == actual_consumed.to_integral() else actual_consumed
        display_remaining = int(remaining_total) if remaining_total == remaining_total.to_integral() else remaining_total

        if consume_qty > total_quantity:
            display_total = int(total_quantity) if total_quantity == total_quantity.to_integral() else total_quantity
            return f"냉장고에 남은 {ingredient_name} 수량이 {display_total}개라 모두 소비 처리했어요."
        if remaining_total == 0:
            return f"{ingredient_name}{_object_particle(ingredient_name)} {display_consumed}개 소비 처리했어요. 남은 수량은 없어요."
        return f"{ingredient_name}{_object_particle(ingredient_name)} {display_consumed}개 소비 처리했어요. (남은 총수량: {display_remaining})"


inventory_service = InventoryService()
