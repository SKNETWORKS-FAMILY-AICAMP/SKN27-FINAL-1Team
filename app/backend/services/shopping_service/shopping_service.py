import re
from datetime import date
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.backend.db.models import Ingredient, Recipe, ShoppingList, ShoppingListItem
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

        shopping_list = self._get_or_create_active_list(db, user_id=user_id, recipe_id=recipe_id, source=source)
        source_ref = self._build_source_ref(db, source=source, recipe_id=recipe_id)
        self._merge_items_into_list(db, shopping_list, missing_ingredients, source=source, source_ref=source_ref)

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
        if self._backfill_missing_products(shopping_list):
            db.commit()
        return self._map_list(shopping_list, owned_ingredients=recipe_context["owned_ingredients"])

    def get_list(self, db: Session, user_id: int, shopping_list_id: int) -> dict:
        shopping_list = self._get_user_list(db, user_id, shopping_list_id)
        recipe_context = self._sync_recipe_list(db, user_id, shopping_list)
        if recipe_context["changed"]:
            shopping_list = self._get_user_list(db, user_id, shopping_list_id)
        if self._backfill_missing_products(shopping_list):
            db.commit()
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

        # 모든 재료가 입고되면 현재 장보기에서는 빠지고, 지난 내역에는 완료 세션으로 남긴다.
        if shopping_list.status == "completed":
            db.commit()
            return {
                "message": f"{stocked_count}개 재료를 냉장고에 입고하고 장보기를 완료했어요.",
                "stocked_count": stocked_count,
                "shopping_list": None,
            }

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

    def search_products(self, keyword: str, display: int = 5) -> dict:
        query = (keyword or "").strip()
        if not query:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="검색어가 비어 있습니다.")

        products = self.provider.search_products(query, display=display)
        return {
            "keyword": query,
            "items": [self._map_product_candidate(query, product) for product in products],
        }

    def _get_or_create_active_list(
        self,
        db: Session,
        user_id: int,
        recipe_id: int | None,
        source: str,
    ) -> ShoppingList:
        shopping_list = (
            db.query(ShoppingList)
            .options(joinedload(ShoppingList.items), joinedload(ShoppingList.recipe))
            .filter(ShoppingList.user_id == user_id, ShoppingList.status == "active")
            .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
            .first()
        )
        if shopping_list:
            if recipe_id and not shopping_list.recipe_id:
                shopping_list.recipe_id = recipe_id
            if source == "recipe" and shopping_list.source != "recipe":
                shopping_list.source = "recipe"
            return shopping_list

        shopping_list = ShoppingList(user_id=user_id, recipe_id=recipe_id, source=source, status="active")
        db.add(shopping_list)
        db.flush()
        return shopping_list

    def _merge_items_into_list(
        self,
        db: Session,
        shopping_list: ShoppingList,
        raw_items: list[ShoppingIngredientInput],
        source: str,
        source_ref: dict | None,
    ) -> bool:
        active_by_key = {
            self._ingredient_key(item.ingredient_id, item.name): item
            for item in shopping_list.items
            if not item.is_purchased
        }
        active_by_key = {key: item for key, item in active_by_key.items() if key}
        changed = False

        for raw_item in raw_items:
            ingredient = self._resolve_ingredient(db, raw_item.ingredient_id, raw_item.name)
            ingredient_id = ingredient.id if ingredient else raw_item.ingredient_id
            key = self._ingredient_key(ingredient_id, raw_item.name)
            if not key:
                continue

            quantity, unit = self._resolve_quantity_and_unit(raw_item, ingredient)
            existing_item = active_by_key.get(key)
            if existing_item:
                current_refs = self._normalize_source_refs(getattr(existing_item, "source_refs", None))
                next_refs = self._merge_source_ref(existing_item, source_ref)
                if next_refs != current_refs:
                    existing_item.source_refs = next_refs
                    changed = True
                if getattr(existing_item, "source_type", None) != source and source == "recipe":
                    existing_item.source_type = source
                    changed = True

                next_quantity, next_unit = self._merge_quantity(existing_item.required_quantity, existing_item.unit, quantity, unit)
                if existing_item.required_quantity != next_quantity or existing_item.unit != next_unit:
                    existing_item.required_quantity = next_quantity
                    existing_item.unit = next_unit
                    changed = True
                if self._apply_product_snapshot(existing_item, raw_item):
                    changed = True
                if self._backfill_product(existing_item):
                    changed = True
                continue

            product_snapshot = self._product_snapshot_from_input(raw_item)
            product = None if product_snapshot else self.provider.search_best_product(raw_item.name)
            item = ShoppingListItem(
                shopping_list_id=shopping_list.id,
                ingredient_id=ingredient_id,
                name=raw_item.name.strip(),
                required_quantity=quantity,
                unit=unit,
                provider=(product_snapshot or {}).get("provider") or (product.provider if product else self.provider.provider_name),
                product_id=(product_snapshot or {}).get("product_id") or (product.product_id if product else None),
                product_name=(product_snapshot or {}).get("product_name") or (product.product_name if product else None),
                product_link=(product_snapshot or {}).get("product_link") or (self.provider.build_product_link(product) if product else None),
                product_image=(product_snapshot or {}).get("product_image") or (product.product_image if product else None),
                price=(product_snapshot or {}).get("price") if product_snapshot else (product.price if product else None),
                mall_name=(product_snapshot or {}).get("mall_name") or (product.mall_name if product else None),
                is_checked=True,
                source_type=source,
                source_refs=[source_ref] if source_ref else [{"type": source}],
            )
            db.add(item)
            shopping_list.items.append(item)
            active_by_key[key] = item
            changed = True

        return changed

    def _map_product_candidate(self, name: str, product) -> dict:
        return {
            "name": name,
            "provider": product.provider,
            "coupang": None,
            "kurly": None,
            "best_market": product.mall_name,
            "product_id": product.product_id,
            "product_name": product.product_name,
            "product_link": product.product_link,
            "product_image": product.product_image,
            "price": product.price,
            "mall_name": product.mall_name,
        }

    def _product_snapshot_from_input(self, raw_item: ShoppingIngredientInput) -> dict | None:
        if not any([
            raw_item.product_id,
            raw_item.product_name,
            raw_item.product_link,
            raw_item.product_image,
            raw_item.price,
            raw_item.mall_name,
        ]):
            return None
        return {
            "provider": raw_item.provider or self.provider.provider_name,
            "product_id": raw_item.product_id,
            "product_name": raw_item.product_name,
            "product_link": raw_item.product_link,
            "product_image": raw_item.product_image,
            "price": raw_item.price,
            "mall_name": raw_item.mall_name,
        }

    def _apply_product_snapshot(self, item: ShoppingListItem, raw_item: ShoppingIngredientInput) -> bool:
        snapshot = self._product_snapshot_from_input(raw_item)
        if not snapshot:
            return False

        changed = False
        for attr, value in snapshot.items():
            if value is not None and getattr(item, attr) != value:
                setattr(item, attr, value)
                changed = True
        return changed

    def _backfill_missing_products(self, shopping_list: ShoppingList) -> bool:
        changed = False
        for item in shopping_list.items:
            if self._backfill_product(item):
                changed = True
        return changed

    def _backfill_product(self, item: ShoppingListItem) -> bool:
        if item.is_purchased or not self._needs_product_backfill(item):
            return False

        product = self.provider.search_best_product(item.name)
        if not product:
            return False

        snapshot = {
            "provider": product.provider,
            "product_id": product.product_id,
            "product_name": product.product_name,
            "product_link": self.provider.build_product_link(product),
            "product_image": product.product_image,
            "price": product.price,
            "mall_name": product.mall_name,
        }
        changed = False
        for attr, value in snapshot.items():
            if value is not None and getattr(item, attr) != value:
                setattr(item, attr, value)
                changed = True
        return changed

    def _needs_product_backfill(self, item: ShoppingListItem) -> bool:
        return not any(
            [
                item.product_id,
                item.product_name,
                item.product_link,
                item.product_image,
                item.price,
                item.mall_name,
            ]
        )

    def _build_source_ref(self, db: Session, source: str, recipe_id: int | None = None) -> dict:
        if source == "recipe" and recipe_id:
            recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
            return {
                "type": "recipe",
                "recipe_id": recipe_id,
                "recipe_title": recipe.title if recipe else None,
            }
        return {"type": source}

    def _normalize_source_refs(self, refs) -> list[dict]:
        if isinstance(refs, list):
            return [dict(ref) for ref in refs if isinstance(ref, dict)]
        if isinstance(refs, dict):
            return [dict(refs)]
        return []

    def _merge_source_ref(self, item: ShoppingListItem, source_ref: dict | None) -> list[dict]:
        refs = self._normalize_source_refs(getattr(item, "source_refs", None))
        if not source_ref:
            return refs

        ref_type = source_ref.get("type")
        recipe_id = source_ref.get("recipe_id")
        for index, ref in enumerate(refs):
            if ref.get("type") == ref_type and ref.get("recipe_id") == recipe_id:
                if source_ref.get("recipe_title") and not ref.get("recipe_title"):
                    refs[index] = {**ref, "recipe_title": source_ref["recipe_title"]}
                return refs

        return [*refs, source_ref]

    def _merge_quantity(
        self,
        current_quantity: Decimal | None,
        current_unit: str | None,
        next_quantity: Decimal | None,
        next_unit: str | None,
    ) -> tuple[Decimal | None, str | None]:
        if current_quantity is None:
            return next_quantity, next_unit or current_unit
        if next_quantity is None:
            return current_quantity, current_unit or next_unit
        if (current_unit or "") != (next_unit or ""):
            return current_quantity, current_unit
        return max(current_quantity, next_quantity), current_unit or next_unit

    def _recipe_ids_for_list(self, shopping_list: ShoppingList) -> list[int]:
        recipe_ids: list[int] = []
        if shopping_list.recipe_id:
            recipe_ids.append(int(shopping_list.recipe_id))

        for item in shopping_list.items:
            for ref in self._normalize_source_refs(getattr(item, "source_refs", None)):
                recipe_id = ref.get("recipe_id")
                if ref.get("type") == "recipe" and recipe_id:
                    recipe_ids.append(int(recipe_id))

        return list(dict.fromkeys(recipe_ids))

    def _has_recipe_source(self, item: ShoppingListItem, recipe_id: int) -> bool:
        refs = self._normalize_source_refs(getattr(item, "source_refs", None))
        if not refs:
            return False
        return any(ref.get("type") == "recipe" and int(ref.get("recipe_id") or 0) == int(recipe_id) for ref in refs)

    def _remove_recipe_source(self, item: ShoppingListItem, recipe_id: int) -> list[dict]:
        return [
            ref
            for ref in self._normalize_source_refs(getattr(item, "source_refs", None))
            if not (ref.get("type") == "recipe" and int(ref.get("recipe_id") or 0) == int(recipe_id))
        ]

    def _list_source_recipes(self, shopping_list: ShoppingList) -> list[dict]:
        recipes: dict[int, dict] = {}
        if shopping_list.recipe_id:
            recipes[int(shopping_list.recipe_id)] = {
                "type": "recipe",
                "recipe_id": int(shopping_list.recipe_id),
                "recipe_title": shopping_list.recipe.title if shopping_list.recipe else None,
            }

        for item in shopping_list.items:
            for ref in self._normalize_source_refs(getattr(item, "source_refs", None)):
                recipe_id = ref.get("recipe_id")
                if ref.get("type") == "recipe" and recipe_id:
                    recipes[int(recipe_id)] = {
                        "type": "recipe",
                        "recipe_id": int(recipe_id),
                        "recipe_title": ref.get("recipe_title"),
                    }

        return list(recipes.values())

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
        if shopping_list.status != "active":
            return {"changed": False, "owned_ingredients": []}

        recipe_ids = self._recipe_ids_for_list(shopping_list)
        if not recipe_ids:
            return {"changed": False, "owned_ingredients": []}

        changed = False
        owned_ingredients: list[dict] = []

        for recipe_id in recipe_ids:
            recipe_detail = recipe_detail_service.get_recipe_detail(db, recipe_id, user_id)
            owned_ingredients.extend(recipe_detail.get("owned_ingredients", []))
            owned_ingredients.extend(recipe_detail.get("maybe_owned_ingredients", []))
            missing_ingredients = recipe_detail.get("missing_ingredients", [])

            desired_by_key = {
                self._ingredient_key(item.get("ingredient_id"), item.get("name")): item
                for item in missing_ingredients
                if item.get("name")
            }
            desired_by_key = {key: item for key, item in desired_by_key.items() if key}

            for item in list(shopping_list.items):
                item_refs = self._normalize_source_refs(getattr(item, "source_refs", None))
                is_legacy_recipe_item = (
                    not item_refs
                    and shopping_list.source == "recipe"
                    and shopping_list.recipe_id
                    and int(shopping_list.recipe_id) == int(recipe_id)
                )
                if item.is_purchased or not (self._has_recipe_source(item, recipe_id) or is_legacy_recipe_item):
                    continue

                key = self._ingredient_key(item.ingredient_id, item.name)
                if key in desired_by_key:
                    continue

                next_refs = self._remove_recipe_source(item, recipe_id)
                if next_refs:
                    item.source_refs = next_refs
                else:
                    db.delete(item)
                    if item in shopping_list.items:
                        shopping_list.items.remove(item)
                changed = True

            shopping_inputs = [
                ShoppingIngredientInput(
                    ingredient_id=raw_item.get("ingredient_id"),
                    name=raw_item["name"],
                    amount=raw_item.get("amount"),
                )
                for raw_item in desired_by_key.values()
            ]
            source_ref = self._build_source_ref(db, source="recipe", recipe_id=recipe_id)
            if self._merge_items_into_list(db, shopping_list, shopping_inputs, source="recipe", source_ref=source_ref):
                changed = True

        if changed:
            db.commit()

        return {"changed": changed, "owned_ingredients": self._dedupe_owned_ingredients(owned_ingredients)}

    def _map_list(self, shopping_list: ShoppingList, owned_ingredients: list[dict] | None = None) -> dict:
        items = sorted(shopping_list.items, key=lambda item: item.id)
        total_price = sum((item.price or 0) for item in items if item.is_checked and not item.is_purchased)
        source_recipes = self._list_source_recipes(shopping_list)
        return {
            "id": shopping_list.id,
            "user_id": shopping_list.user_id,
            "recipe_id": shopping_list.recipe_id,
            "recipe_title": shopping_list.recipe.title if shopping_list.recipe else None,
            "source_recipes": source_recipes,
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
                    "source_type": getattr(item, "source_type", None) or shopping_list.source,
                    "source_refs": self._normalize_source_refs(getattr(item, "source_refs", None)),
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
