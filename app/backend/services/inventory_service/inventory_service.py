from sqlalchemy.orm import Session
from fastapi import HTTPException, status, UploadFile
from typing import List, Optional
from datetime import date, timedelta
from app.backend.db.models import User, Ingredient, FridgeItem, IngredientStorageStandard
from app.backend.schemas.inventory import IngredientCreate, IngredientResponse

class InventoryService:
    def get_recommended_lifespan(self, name: str, category: str, storage_method: str = "냉장") -> int:
        from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service
        try:
            _, days = expiration_ai_service.predict_storage_and_lifespan(name, category, storage_method)
            return days
        except Exception as e:
            return 7

    def _get_or_create_storage_rule(self, db: Session, ingredient: Ingredient, storage_method: Optional[str]) -> tuple[str, int]:
        from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service
        from sqlalchemy.exc import IntegrityError
        
        final_storage = storage_method
        cached_rule = None
        
        if final_storage:
            cached_rule = db.query(IngredientStorageStandard).filter(
                IngredientStorageStandard.ingredient_id == ingredient.id,
                IngredientStorageStandard.storage_location == final_storage
            ).first()
        else:
            cached_rule = db.query(IngredientStorageStandard).filter(
                IngredientStorageStandard.ingredient_id == ingredient.id
            ).first()
            if cached_rule:
                final_storage = cached_rule.storage_location
                
        if cached_rule:
            return final_storage, cached_rule.lifespan_days
            
        pred_storage, pred_days = expiration_ai_service.predict_storage_and_lifespan(
            ingredient.name, ingredient.category, storage_method
        )
        final_storage = final_storage or pred_storage
        lifespan_days = pred_days
        
        try:
            with db.begin_nested():
                new_rule = IngredientStorageStandard(
                    ingredient_id=ingredient.id,
                    storage_location=final_storage,
                    lifespan_days=lifespan_days
                )
                db.add(new_rule)
                db.flush()
        except IntegrityError as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to cache storage rule: {e}")
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Unknown error while caching storage rule: {e}")
            
        return final_storage, lifespan_days

    def _calculate_d_day_and_flags(self, expiry_date: date, purchased_date: date, name: str, category: str, storage_location: str) -> dict:
        """DB의 식재료 객체를 기반으로 유통기한 D-day와 임박 여부를 계산합니다."""
        import logging
        logger = logging.getLogger(__name__)
        today = date.today()
        
        try:
            if expiry_date:
                if isinstance(expiry_date, str):
                    from datetime import datetime
                    target_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
                else:
                    target_date = expiry_date
            else:
                lifespan_days = self.get_recommended_lifespan(name, category, storage_location)
                
                p_date = purchased_date or today
                if isinstance(p_date, str):
                    from datetime import datetime
                    p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
                    
                target_date = p_date + timedelta(days=lifespan_days)
                
            d_day_delta = (target_date - today).days
            is_expiring_soon = True if d_day_delta <= 3 else False
            
            return {
                "d_day": d_day_delta,
                "is_expiring_soon": is_expiring_soon,
                "calculated_expiration_date": target_date
            }
        except Exception as e:
            logger.error(f"D-day 계산 중 치명적 오류: {e}")
            fallback_date = today + timedelta(days=7)
            return {
                "d_day": 7,
                "is_expiring_soon": False,
                "calculated_expiration_date": fallback_date
            }

    def _map_to_response(self, item: FridgeItem, ingredient: Ingredient) -> dict:
        """FridgeItem과 Ingredient를 프론트엔드가 요구하는 IngredientResponse 스키마 형태로 매핑합니다."""
        calc_info = self._calculate_d_day_and_flags(
            expiry_date=item.expiry_date,
            purchased_date=item.purchased_date,
            name=ingredient.name,
            category=ingredient.category,
            storage_location=item.storage_location or "냉장"
        )
        
        final_expiry = item.expiry_date or calc_info.get("calculated_expiration_date")
        
        return {
            "id": item.id,
            "fridge_id": 1, # 프론트엔드 호환성을 위한 더미 데이터
            "name": item.display_name or ingredient.name,
            "category": ingredient.category,
            "quantity": float(item.quantity) if item.quantity else 1.0,
            "unit": item.unit or ingredient.default_unit or "개",
            "storage_method": item.storage_location or "냉장",
            "purchase_date": item.purchased_date or date.today(),
            "expiration_date": final_expiry,
            "created_at": item.created_at,
            "updated_at": item.created_at,
            "d_day": calc_info.get("d_day"),
            "is_expiring_soon": calc_info.get("is_expiring_soon")
        }

    def add_ingredient(self, db: Session, user_id: int, data: IngredientCreate):
        # 1. 마스터 테이블 확인
        normalized = data.name.strip().replace(" ", "").lower()
        ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
        
        if not ingredient:
            try:
                from sqlalchemy.exc import IntegrityError
                with db.begin_nested():
                    ingredient = Ingredient(
                        name=data.name,
                        normalized_name=normalized,
                        category=data.category,
                        default_unit=data.unit
                    )
                    db.add(ingredient)
                    db.flush()
            except IntegrityError:
                # 동시성 문제 등으로 이미 같은 이름이 등록된 경우
                ingredient = db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()
            
        # 2. 보관 방법 및 유통기한 자동 계산 (캐시 활용)
        final_storage = data.storage_method
        final_expiry = data.expiration_date
        
        if not final_expiry:
            final_storage, lifespan_days = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
            p_date = data.purchase_date or date.today()
            if isinstance(p_date, str):
                from datetime import datetime
                p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
            final_expiry = p_date + timedelta(days=lifespan_days)
        else:
            final_storage = final_storage or "냉장"

        # 3. FridgeItem 추가
        fridge_item = FridgeItem(
            user_id=user_id,
            ingredient_id=ingredient.id,
            display_name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            storage_location=final_storage,
            purchased_date=data.purchase_date or date.today(),
            expiry_date=final_expiry,
            status="normal"
        )
        db.add(fridge_item)
        db.commit()
        db.refresh(fridge_item)
        
        return self._map_to_response(fridge_item, ingredient)

    def get_ingredients(self, db: Session, user_id: int):
        items = db.query(FridgeItem, Ingredient).join(
            Ingredient, FridgeItem.ingredient_id == Ingredient.id
        ).filter(
            FridgeItem.user_id == user_id,
            FridgeItem.status == "normal"
        ).all()
        
        results = []
        for fridge_item, ingredient in items:
            results.append(self._map_to_response(fridge_item, ingredient))
            
        return results

    def delete_ingredient(self, db: Session, user_id: int, ingredient_id: int):
        fridge_item = db.query(FridgeItem).filter(
            FridgeItem.id == ingredient_id, 
            FridgeItem.user_id == user_id
        ).first()
        
        if not fridge_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")
            
        db.delete(fridge_item)
        db.commit()

    def update_ingredient(self, db: Session, user_id: int, ingredient_id: int, data: IngredientCreate):
        fridge_item = db.query(FridgeItem).filter(
            FridgeItem.id == ingredient_id, 
            FridgeItem.user_id == user_id
        ).first()
        
        if not fridge_item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="해당 식재료를 찾을 수 없습니다.")
            
        ingredient = db.query(Ingredient).filter(Ingredient.id == fridge_item.ingredient_id).first()
        
        final_storage = data.storage_method
        final_expiry = data.expiration_date
        
        if not final_expiry:
            final_storage, lifespan_days = self._get_or_create_storage_rule(db, ingredient, data.storage_method)
            p_date = data.purchase_date or date.today()
            if isinstance(p_date, str):
                from datetime import datetime
                p_date = datetime.strptime(p_date, "%Y-%m-%d").date()
            final_expiry = p_date + timedelta(days=lifespan_days)
        else:
            final_storage = final_storage or "냉장"

        fridge_item.display_name = data.name
        fridge_item.quantity = data.quantity
        fridge_item.unit = data.unit
        fridge_item.storage_location = final_storage
        fridge_item.purchased_date = data.purchase_date or date.today()
        fridge_item.expiry_date = final_expiry
            
        db.commit()
        db.refresh(fridge_item)
        
        return self._map_to_response(fridge_item, ingredient)

    def get_inventory_summary(self, db: Session, user_id: int):
        items = db.query(FridgeItem, Ingredient).join(
            Ingredient, FridgeItem.ingredient_id == Ingredient.id
        ).filter(
            FridgeItem.user_id == user_id,
            FridgeItem.status == "normal"
        ).all()
        
        today = date.today()
        
        total = len(items)
        expiring_soon = 0
        today_added = 0
        storage = {"냉장": 0, "냉동": 0, "실온": 0, "기타": 0}
        
        for fridge_item, ingredient in items:
            mapped = self._map_to_response(fridge_item, ingredient)
            
            if mapped.get("is_expiring_soon"):
                expiring_soon += 1
                
            if fridge_item.purchased_date == today:
                today_added += 1
                
            method = fridge_item.storage_location or "기타"
            if method in storage:
                storage[method] += 1
            else:
                storage["기타"] += 1
                
        return {
            "total": total,
            "expiring_soon": expiring_soon,
            "today_added": today_added,
            "storage": storage
        }

inventory_service = InventoryService()
