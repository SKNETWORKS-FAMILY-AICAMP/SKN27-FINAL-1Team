import re
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.backend.db.models import Ingredient, ShoppingList, ShoppingListItem
from app.backend.schemas.inventory import IngredientCreate
from app.backend.schemas.shopping import ShoppingIngredientInput
from app.backend.services.inventory_service.inventory_service import inventory_service
from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service
from app.backend.services.shopping_service.providers.naver_search import NaverShoppingProvider

AMOUNT_RE = re.compile(r"(?P<quantity>\d+(?:\.\d+)?)\s*(?P<unit>[가-힣a-zA-Z%]+)?")


class ShoppingService:
    """장보기 목록 생성, 조회, 수정, 구매 완료 처리를 담당합니다."""

    def __init__(self, provider=None):
        self.provider = provider or NaverShoppingProvider()

    def create_list(
        self,
        db: Session,
        user_id: int,
        recipe_id: int | None,
        source: str,
        missing_ingredients: list[ShoppingIngredientInput],
    ) -> dict:
        if not missing_ingredients:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="장보기 재료가 비어 있습니다.")

        shopping_list = ShoppingList(user_id=user_id, recipe_id=recipe_id, source=source, status="active")
        db.add(shopping_list)
        db.flush()

        for raw_item in missing_ingredients:
            ingredient = self._resolve_ingredient(db, raw_item.ingredient_id, raw_item.name)
            quantity, unit = self._resolve_quantity_and_unit(raw_item, ingredient)
            product = self.provider.search_best_product(raw_item.name)

            db.add(
                ShoppingListItem(
                    shopping_list_id=shopping_list.id,
                    ingredient_id=ingredient.id if ingredient else raw_item.ingredient_id,
                    name=raw_item.name.strip(),
                    required_quantity=quantity,
                    unit=unit,
                    provider=product.provider if product else self.provider.provider_name,
                    product_id=product.product_id if product else None,
                    product_name=product.product_name if product else None,
                    product_link=self.provider.build_product_link(product) if product else None,
                    product_image=product.product_image if product else None,
                    price=product.price if product else None,
                    mall_name=product.mall_name if product else None,
                    is_checked=True,
                )
            )

        db.commit()
        return self.get_list(db, user_id=user_id, shopping_list_id=shopping_list.id)

    def get_current(self, db: Session, user_id: int) -> dict | None:
        shopping_list = (
            db.query(ShoppingList)
            .options(joinedload(ShoppingList.items), joinedload(ShoppingList.recipe))
            .filter(ShoppingList.user_id == user_id, ShoppingList.status == "active")
            .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
            .first()
        )
        if not shopping_list:
            return None

        recipe_context = self._sync_recipe_list(db, user_id, shopping_list)
        if recipe_context["changed"]:
            shopping_list = self._get_user_list(db, user_id, shopping_list.id)
        return self._map_list(shopping_list, owned_ingredients=recipe_context["owned_ingredients"])

    def get_list(self, db: Session, user_id: int, shopping_list_id: int) -> dict:
        shopping_list = self._get_user_list(db, user_id, shopping_list_id)
        recipe_context = self._sync_recipe_list(db, user_id, shopping_list)
        if recipe_context["changed"]:
            shopping_list = self._get_user_list(db, user_id, shopping_list_id)
        return self._map_list(shopping_list, owned_ingredients=recipe_context["owned_ingredients"])

    def get_history(self, db: Session, user_id: int, limit: int = 20) -> list[dict]:
        normalized_limit = min(max(int(limit or 20), 1), 50)
        shopping_lists = (
            db.query(ShoppingList)
            .options(joinedload(ShoppingList.items), joinedload(ShoppingList.recipe))
            .filter(ShoppingList.user_id == user_id)
            .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
            .limit(normalized_limit)
            .all()
        )
        return [self._map_list(shopping_list) for shopping_list in shopping_lists]

    def update_item(
        self,
        db: Session,
        user_id: int,
        item_id: int,
        is_checked: bool | None = None,
        is_purchased: bool | None = None,
    ) -> dict:
        item = self._get_user_item(db, user_id, item_id)
        if is_checked is not None:
            item.is_checked = is_checked
        if is_purchased is not None:
            item.is_purchased = is_purchased

        self._sync_list_status(item.shopping_list)
        db.commit()
        return self.get_list(db, user_id=user_id, shopping_list_id=item.shopping_list_id)

    def delete_item(self, db: Session, user_id: int, item_id: int) -> dict:
        item = self._get_user_item(db, user_id, item_id)
        shopping_list_id = item.shopping_list_id
        db.delete(item)
        db.commit()
        return self.get_list(db, user_id=user_id, shopping_list_id=shopping_list_id)

    def delete_list(self, db: Session, user_id: int, shopping_list_id: int) -> None:
        shopping_list = self._get_user_list(db, user_id, shopping_list_id)
        db.delete(shopping_list)
        db.commit()

    def complete_purchase(
        self,
        db: Session,
        user_id: int,
        shopping_list_id: int | None = None,
        item_ids: list[int] | None = None,
    ) -> dict:
        shopping_list = (
            self._get_user_list(db, user_id, shopping_list_id)
            if shopping_list_id
            else self._get_latest_required(db, user_id)
        )

        target_items = [
            item
            for item in shopping_list.items
            if not item.is_purchased and (item_ids is None and item.is_checked or item_ids is not None and item.id in item_ids)
        ]

        stocked_count = 0
        for item in target_items:
            inventory_service.add_ingredient(
                db,
                user_id,
                IngredientCreate(
                    name=self._stock_name(db, item),
                    quantity=float(item.required_quantity or Decimal("1")),
                    unit=item.unit or self._stock_unit(db, item),
                    purchase_date=date.today(),
                ),
            )
            item.is_purchased = True
            stocked_count += 1

        self._sync_list_status(shopping_list)
        db.commit()

        return {
            "message": f"{stocked_count}개 재료가 냉장고에 입고되었습니다.",
            "stocked_count": stocked_count,
            "shopping_list": self.get_list(db, user_id=user_id, shopping_list_id=shopping_list.id),
        }

    def compare_products(self, ingredient_names: list[str]) -> dict:
        rows = []
        total_price = 0
        for name in ingredient_names:
            product = self.provider.search_best_product(name)
            price = product.price if product and product.price is not None else None
            if price:
                total_price += price
            rows.append(
                {
                    "name": name,
                    "provider": product.provider if product else self.provider.provider_name,
                    "coupang": None,
                    "kurly": None,
                    "best_market": product.mall_name if product else None,
                    "product_id": product.product_id if product else None,
                    "product_name": product.product_name if product else None,
                    "product_link": product.product_link if product else None,
                    "product_image": product.product_image if product else None,
                    "price": price,
                    "mall_name": product.mall_name if product else None,
                }
            )

        return {
            "total_price": total_price,
            "delivery_saving": 0,
            "market_prices": rows,
            "recommended_market": "네이버 쇼핑",
        }

    def _get_user_list(self, db: Session, user_id: int, shopping_list_id: int) -> ShoppingList:
        shopping_list = (
            db.query(ShoppingList)
            .options(joinedload(ShoppingList.items), joinedload(ShoppingList.recipe))
            .filter(ShoppingList.id == shopping_list_id, ShoppingList.user_id == user_id)
            .first()
        )
        if not shopping_list:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="장보기 목록을 찾을 수 없습니다.")
        return shopping_list

    def _get_latest_required(self, db: Session, user_id: int) -> ShoppingList:
        shopping_list = (
            db.query(ShoppingList)
            .options(joinedload(ShoppingList.items), joinedload(ShoppingList.recipe))
            .filter(ShoppingList.user_id == user_id, ShoppingList.status == "active")
            .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
            .first()
        )
        if not shopping_list:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="진행 중인 장보기 목록이 없습니다.")
        return shopping_list

    def _get_user_item(self, db: Session, user_id: int, item_id: int) -> ShoppingListItem:
        item = (
            db.query(ShoppingListItem)
            .join(ShoppingList, ShoppingListItem.shopping_list_id == ShoppingList.id)
            .options(joinedload(ShoppingListItem.shopping_list).joinedload(ShoppingList.items))
            .filter(ShoppingListItem.id == item_id, ShoppingList.user_id == user_id)
            .first()
        )
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="장보기 재료를 찾을 수 없습니다.")
        return item

    def _resolve_ingredient(self, db: Session, ingredient_id: int | None, name: str) -> Ingredient | None:
        if ingredient_id:
            ingredient = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
            if ingredient:
                return ingredient

        normalized = self._normalize_name(name)
        return db.query(Ingredient).filter(Ingredient.normalized_name == normalized).first()

    def _resolve_quantity_and_unit(
        self,
        item: ShoppingIngredientInput,
        ingredient: Ingredient | None,
    ) -> tuple[Decimal | None, str | None]:
        if item.required_quantity is not None:
            return Decimal(str(item.required_quantity)), item.unit or (ingredient.default_unit if ingredient else None)

        if item.amount:
            match = AMOUNT_RE.search(item.amount)
            if match:
                quantity = Decimal(match.group("quantity"))
                unit = item.unit or match.group("unit") or (ingredient.default_unit if ingredient else None)
                return quantity, unit

        return None, item.unit or (ingredient.default_unit if ingredient else None)

    def _dedupe_owned_ingredients(self, owned_ingredients: list[dict]) -> list[dict]:
        deduped: list[dict] = []
        seen_keys: set[str] = set()

        for item in owned_ingredients:
            name = str(item.get("name") or "").strip().lower()
            key = f"name:{name}" if name else f"id:{item.get('ingredient_id')}"
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)

        return deduped

    def _sync_recipe_list(self, db: Session, user_id: int, shopping_list: ShoppingList) -> dict:
        if shopping_list.source != "recipe" or not shopping_list.recipe_id or shopping_list.status != "active":
            return {"changed": False, "owned_ingredients": []}

        recipe_detail = recipe_detail_service.get_recipe_detail(db, shopping_list.recipe_id, user_id)
        owned_ingredients = self._dedupe_owned_ingredients(
            [
                *recipe_detail.get("owned_ingredients", []),
                *recipe_detail.get("maybe_owned_ingredients", []),
            ]
        )
        missing_ingredients = recipe_detail.get("missing_ingredients", [])

        desired_by_key = {
            self._ingredient_key(item.get("ingredient_id"), item.get("name")): item
            for item in missing_ingredients
            if item.get("name")
        }
        desired_by_key = {key: item for key, item in desired_by_key.items() if key}

        active_items = [item for item in shopping_list.items if not item.is_purchased]
        active_by_key = {
            self._ingredient_key(item.ingredient_id, item.name): item
            for item in active_items
        }
        active_by_key = {key: item for key, item in active_by_key.items() if key}

        changed = False

        for key, item in list(active_by_key.items()):
            if key not in desired_by_key:
                db.delete(item)
                changed = True

        for key, raw_item in desired_by_key.items():
            item = active_by_key.get(key)
            shopping_input = ShoppingIngredientInput(
                ingredient_id=raw_item.get("ingredient_id"),
                name=raw_item["name"],
                amount=raw_item.get("amount"),
            )
            ingredient = self._resolve_ingredient(db, shopping_input.ingredient_id, shopping_input.name)
            quantity, unit = self._resolve_quantity_and_unit(shopping_input, ingredient)

            if item:
                next_ingredient_id = ingredient.id if ingredient else shopping_input.ingredient_id
                if (
                    item.ingredient_id != next_ingredient_id
                    or item.name != shopping_input.name.strip()
                    or item.required_quantity != quantity
                    or item.unit != unit
                ):
                    item.ingredient_id = next_ingredient_id
                    item.name = shopping_input.name.strip()
                    item.required_quantity = quantity
                    item.unit = unit
                    changed = True
                continue

            product = self.provider.search_best_product(shopping_input.name)
            db.add(
                ShoppingListItem(
                    shopping_list_id=shopping_list.id,
                    ingredient_id=ingredient.id if ingredient else shopping_input.ingredient_id,
                    name=shopping_input.name.strip(),
                    required_quantity=quantity,
                    unit=unit,
                    provider=product.provider if product else self.provider.provider_name,
                    product_id=product.product_id if product else None,
                    product_name=product.product_name if product else None,
                    product_link=self.provider.build_product_link(product) if product else None,
                    product_image=product.product_image if product else None,
                    price=product.price if product else None,
                    mall_name=product.mall_name if product else None,
                    is_checked=True,
                )
            )
            changed = True

        if changed:
            db.commit()

        return {"changed": changed, "owned_ingredients": owned_ingredients}

    def _map_list(self, shopping_list: ShoppingList, owned_ingredients: list[dict] | None = None) -> dict:
        items = sorted(shopping_list.items, key=lambda item: item.id)
        total_price = sum((item.price or 0) for item in items if item.is_checked and not item.is_purchased)
        return {
            "id": shopping_list.id,
            "user_id": shopping_list.user_id,
            "recipe_id": shopping_list.recipe_id,
            "recipe_title": shopping_list.recipe.title if shopping_list.recipe else None,
            "source": shopping_list.source,
            "status": shopping_list.status,
            "total_price": total_price,
            "checked_count": sum(1 for item in items if item.is_checked),
            "purchased_count": sum(1 for item in items if item.is_purchased),
            "created_at": shopping_list.created_at,
            "owned_ingredients": owned_ingredients or [],
            "items": [
                {
                    "id": item.id,
                    "ingredient_id": item.ingredient_id,
                    "name": item.name,
                    "required_quantity": float(item.required_quantity) if item.required_quantity is not None else None,
                    "unit": item.unit,
                    "provider": item.provider,
                    "product_id": item.product_id,
                    "product_name": item.product_name,
                    "product_link": item.product_link,
                    "product_image": item.product_image,
                    "price": item.price,
                    "mall_name": item.mall_name,
                    "is_checked": item.is_checked,
                    "is_purchased": item.is_purchased,
                    "created_at": item.created_at,
                }
                for item in items
            ],
        }

    def _sync_list_status(self, shopping_list: ShoppingList) -> None:
        if shopping_list.items and all(item.is_purchased for item in shopping_list.items):
            shopping_list.status = "completed"
        else:
            shopping_list.status = "active"

    def _stock_name(self, db: Session, item: ShoppingListItem) -> str:
        if item.ingredient_id:
            ingredient = db.query(Ingredient).filter(Ingredient.id == item.ingredient_id).first()
            if ingredient:
                return ingredient.name
        return item.name

    def _stock_unit(self, db: Session, item: ShoppingListItem) -> str:
        if item.ingredient_id:
            ingredient = db.query(Ingredient).filter(Ingredient.id == item.ingredient_id).first()
            if ingredient and ingredient.default_unit:
                return ingredient.default_unit
        return "개"

    def _normalize_name(self, name: str) -> str:
        return (name or "").strip().replace(" ", "").lower()

    def _ingredient_key(self, ingredient_id: int | None, name: str | None) -> str:
        if ingredient_id:
            return f"id:{ingredient_id}"
        normalized = self._normalize_name(name or "")
        return f"name:{normalized}" if normalized else ""


shopping_service = ShoppingService()
