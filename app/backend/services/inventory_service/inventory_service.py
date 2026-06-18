from sqlalchemy.orm import Session
from datetime import date, timedelta
from app.backend.db.models import Fridge, Ingredient
from app.backend.schemas.inventory import IngredientCreate
from fastapi import HTTPException, status

class InventoryService:
    def get_or_create_fridge(self, db: Session, user_id: int) -> Fridge:
        """사용자의 냉장고를 가져오거나 없으면 새로 생성합니다."""
        fridge = db.query(Fridge).filter(Fridge.user_id == user_id).first()
        if not fridge:
            fridge = Fridge(user_id=user_id, name="나의 냉장고")
            db.add(fridge)
            db.commit()
            db.refresh(fridge)
        return fridge

    def get_recommended_lifespan(self, name: str) -> int:
        """
        [임시] 식재료별 권장 보관 기간을 반환하는 헬퍼 함수
        추후 다른 팀원의 DB/API 연동으로 교체될 예정입니다.
        """
        mock_lifespan_db = {
            "시금치": 15,
            "우유": 10,
            "두부": 7,
            "계란": 30,
            "돼지고기": 5,
            "소고기": 5,
            "양파": 30,
            "마늘": 60,
            "사과": 21,
            "바나나": 7
        }
        # 일치하는 식재료가 있으면 그 값을, 없으면 기본값 7일을 반환
        return mock_lifespan_db.get(name, 7)

    def _calculate_d_day_and_flags(self, ingredient: Ingredient) -> dict:
        """DB의 식재료 객체를 기반으로 유통기한 D-day와 임박 여부를 계산합니다."""
        today = date.today()
        
        # 유통기한이 명시적으로 저장되어 있다면 그것을 기준
        if ingredient.expiration_date:
            target_date = ingredient.expiration_date
        else:
            # 명시된 유통기한이 없다면, 구매일(입고일) + 권장 보관 기간으로 유통기한 유추
            lifespan_days = self.get_recommended_lifespan(ingredient.name)
            target_date = ingredient.purchase_date + timedelta(days=lifespan_days)
            
        d_day_delta = (target_date - today).days
        is_expiring_soon = True if d_day_delta <= 3 and d_day_delta >= 0 else False
        
        return {
            "d_day": d_day_delta,
            "is_expiring_soon": is_expiring_soon
        }

    def add_ingredient(self, db: Session, user_id: int, data: IngredientCreate):
        fridge = self.get_or_create_fridge(db, user_id)
        
        # 구매일이 없으면 오늘 날짜
        purchase_date = data.purchase_date if data.purchase_date else date.today()
        
        ingredient = Ingredient(
            fridge_id=fridge.id,
            name=data.name,
            category=data.category,
            quantity=data.quantity,
            unit=data.unit,
            storage_method=data.storage_method,
            purchase_date=purchase_date,
            expiration_date=data.expiration_date
        )
        
        db.add(ingredient)
        db.commit()
        db.refresh(ingredient)
        
        # Response 구성을 위한 추가 정보 계산
        calc_info = self._calculate_d_day_and_flags(ingredient)
        
        result = ingredient.__dict__.copy()
        result.update(calc_info)
        return result

    def get_ingredients(self, db: Session, user_id: int):
        fridge = self.get_or_create_fridge(db, user_id)
        ingredients = db.query(Ingredient).filter(Ingredient.fridge_id == fridge.id).all()
        
        results = []
        for ing in ingredients:
            calc_info = self._calculate_d_day_and_flags(ing)
            item_dict = ing.__dict__.copy()
            item_dict.update(calc_info)
            results.append(item_dict)
            
        return results

    def delete_ingredient(self, db: Session, user_id: int, ingredient_id: int):
        fridge = self.get_or_create_fridge(db, user_id)
        ingredient = db.query(Ingredient).filter(
            Ingredient.id == ingredient_id,
            Ingredient.fridge_id == fridge.id
        ).first()
        
        if not ingredient:
            raise HTTPException(status_code=404, detail="해당 식재료를 찾을 수 없습니다.")
            
        db.delete(ingredient)
        db.commit()
        return {"detail": "식재료가 성공적으로 삭제되었습니다."}

    def update_ingredient(self, db: Session, user_id: int, ingredient_id: int, data: IngredientCreate):
        fridge = self.get_or_create_fridge(db, user_id)
        ingredient = db.query(Ingredient).filter(
            Ingredient.id == ingredient_id,
            Ingredient.fridge_id == fridge.id
        ).first()
        
        if not ingredient:
            raise HTTPException(status_code=404, detail="해당 식재료를 찾을 수 없습니다.")
            
        # 데이터 업데이트
        ingredient.name = data.name
        ingredient.category = data.category
        ingredient.quantity = data.quantity
        ingredient.unit = data.unit
        ingredient.storage_method = data.storage_method
        if data.purchase_date:
            ingredient.purchase_date = data.purchase_date
        ingredient.expiration_date = data.expiration_date
        
        db.commit()
        db.refresh(ingredient)
        
        calc_info = self._calculate_d_day_and_flags(ingredient)
        result = ingredient.__dict__.copy()
        result.update(calc_info)
        return result

    def get_inventory_summary(self, db: Session, user_id: int):
        fridge = self.get_or_create_fridge(db, user_id)
        ingredients = db.query(Ingredient).filter(Ingredient.fridge_id == fridge.id).all()
        
        today = date.today()
        
        total = len(ingredients)
        expiring_soon = 0
        today_added = 0
        storage = {"냉장": 0, "냉동": 0, "실온": 0, "기타": 0}
        
        for ing in ingredients:
            # 1. 소비 임박 카운트
            calc_info = self._calculate_d_day_and_flags(ing)
            if calc_info["is_expiring_soon"]:
                expiring_soon += 1
                
            # 2. 오늘 입고 카운트
            if ing.purchase_date == today:
                today_added += 1
                
            # 3. 보관 위치별 카운트
            method = ing.storage_method
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
