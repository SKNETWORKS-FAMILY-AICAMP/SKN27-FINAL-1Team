import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.backend.db.models import FridgeItem, Ingredient, IngredientStorageStandard
from app.backend.schemas.inventory import IngredientCreate

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = "냉장"
STORAGE_KEYS = ("냉장", "냉동", "실온")
ACTIVE_STATUSES = ("normal", "expiring", "expired")


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

    def _get_status_from_d_day(self, d_day: Optional[int]) -> str:
        """D-day 값을 냉장고 항목 상태값으로 변환합니다."""
        if d_day is None:
            return "normal"
        if d_day < 0:
            return "expired"
        if d_day <= 3:
            return "expiring"
        return "normal"

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
        cached_rule = None

        if requested_storage:
            cached_rule = (
                db.query(IngredientStorageStandard)
                .filter(
                    IngredientStorageStandard.ingredient_id == ingredient.id,
                    IngredientStorageStandard.storage_location == requested_storage,
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

    def _map_to_response(self, item: FridgeItem, ingredient: Ingredient) -> dict:
        """FridgeItem과 Ingredient를 프론트엔드 응답 스키마로 변환합니다."""
        calc_info = self._calculate_expiration_info(
            expiry_date=item.expiry_date,
            purchased_date=item.purchased_date,
            ingredient=ingredient,
            storage_location=item.storage_location,
        )
        return {
            "id": item.id,
            "fridge_id": item.id,
            "name": item.display_name or ingredient.name,
            "category": ingredient.category,
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
        }

    def _get_or_create_ingredient(self, db: Session, data: IngredientCreate) -> Ingredient:
        """식재료 마스터를 조회하고 없으면 새로 생성합니다."""
        self._validate_ingredient_name(data.name)
        normalized = self._normalize_ingredient_name(data.name)
        ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
        if ingredient:
            return ingredient

        try:
            with db.begin_nested():
                ingredient = Ingredient(
                    name=data.name.strip(),
                    normalized_name=normalized,
                    category=data.category,
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

    def _resolve_item_dates_and_storage(self, db: Session, ingredient: Ingredient, data: IngredientCreate) -> tuple[str, date]:
        """요청값과 AI/캐시 기준으로 보관 위치와 소비기한을 확정합니다."""
        purchase_date = self._parse_date(data.purchase_date) or date.today()
        expiration_date = self._parse_date(data.expiration_date)

        if expiration_date:
            storage_location, _ = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
            return storage_location, expiration_date

        storage_location, lifespan_days = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
        return storage_location, purchase_date + timedelta(days=lifespan_days)

    def add_ingredient(self, db: Session, user_id: int, data: IngredientCreate):
        """사용자 냉장고에 식재료를 추가합니다."""
        ingredient = self._get_or_create_ingredient(db, data)
        storage_location, expiration_date = self._resolve_item_dates_and_storage(db, ingredient, data)
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
        )
        db.add(fridge_item)
        db.commit()
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

        db.delete(fridge_item)
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

        ingredient = db.query(Ingredient).filter(Ingredient.id == fridge_item.ingredient_id).first()
        if not ingredient:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="식재료 마스터 정보를 찾을 수 없습니다.")

        storage_location, expiration_date = self._resolve_item_dates_and_storage(db, ingredient, data)
        purchase_date = self._parse_date(data.purchase_date) or date.today()
        d_day = (expiration_date - date.today()).days

        fridge_item.display_name = data.name.strip()
        fridge_item.quantity = data.quantity
        fridge_item.unit = data.unit
        fridge_item.storage_location = storage_location
        fridge_item.purchased_date = purchase_date
        fridge_item.expiry_date = expiration_date
        fridge_item.status = self._get_status_from_d_day(d_day)

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


inventory_service = InventoryService()
