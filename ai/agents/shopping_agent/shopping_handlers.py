from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backend.schemas.shopping import ShoppingIngredientInput
from app.backend.services.recommendation_service.recipe_detail_service import recipe_detail_service
from app.backend.services.recommendation_service.recipe_search_service import recipe_search_service
from app.backend.services.shopping_service import shopping_service
from ai.agents.shopping_agent.shopping_utils import (
    active_shopping_items,
    confirm_action,
    extract_requested_count,
    extract_ingredient_names,
    find_item_by_name,
    format_price,
    is_remaining_request,
    is_show_all_request,
    shopping_list_action,
    shopping_list_slots,
    summarize_owned_ingredients,
    summarize_shopping_list,
)


def _normalize_title(value: str | None) -> str:
    return (value or "").replace(" ", "").lower()


def _title_matches(query: str, title: str | None) -> bool:
    normalized_query = _normalize_title(query)
    normalized_title = _normalize_title(title)
    return bool(normalized_query and normalized_title and (normalized_query in normalized_title or normalized_title in normalized_query))


def _find_recipe_by_title(db: Session, recipe_title: str) -> dict[str, Any] | None:
    result = recipe_search_service.search_recipes(db=db, query=recipe_title, page=1, page_size=10)
    items = result.get("items") or []
    if not items:
        return None
    normalized_query = _normalize_title(recipe_title)
    exact = [item for item in items if _normalize_title(item.get("title")) == normalized_query]
    contains = [item for item in items if _title_matches(recipe_title, item.get("title"))]
    return (exact or contains or items)[0]


def _recipe_refs(shopping_list: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not shopping_list:
        return []

    refs = [ref for ref in shopping_list.get("source_recipes") or [] if isinstance(ref, dict)]
    if shopping_list.get("recipe_id") or shopping_list.get("recipe_title"):
        refs.append(
            {
                "type": "recipe",
                "recipe_id": shopping_list.get("recipe_id"),
                "recipe_title": shopping_list.get("recipe_title"),
            }
        )

    unique_refs: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in refs:
        key = str(ref.get("recipe_id") or _normalize_title(ref.get("recipe_title")))
        if not key or key in seen:
            continue
        seen.add(key)
        unique_refs.append(ref)
    return unique_refs


def _recipe_ref_matches(recipe_title: str, ref: dict[str, Any]) -> bool:
    return _title_matches(recipe_title, ref.get("recipe_title"))


def _item_matches_recipe(item: dict[str, Any], recipe_ref: dict[str, Any], fallback_recipe_id: int | None = None) -> bool:
    recipe_id = recipe_ref.get("recipe_id") or fallback_recipe_id
    recipe_title = recipe_ref.get("recipe_title")
    refs = [ref for ref in item.get("source_refs") or [] if isinstance(ref, dict)]

    if recipe_id and any(ref.get("type") == "recipe" and int(ref.get("recipe_id") or 0) == int(recipe_id) for ref in refs):
        return True
    if recipe_title and any(ref.get("type") == "recipe" and _title_matches(recipe_title, ref.get("recipe_title")) for ref in refs):
        return True
    if recipe_id and item.get("source_type") == "recipe" and not refs:
        return True
    return False


def _filter_list_for_recipe(shopping_list: dict[str, Any], recipe_ref: dict[str, Any], recipe_title: str) -> dict[str, Any]:
    recipe_id = recipe_ref.get("recipe_id") or shopping_list.get("recipe_id")
    filtered_items = [
        item
        for item in shopping_list.get("items") or []
        if _item_matches_recipe(item, recipe_ref, fallback_recipe_id=recipe_id)
    ]
    resolved_title = recipe_ref.get("recipe_title") or recipe_title
    return {
        **shopping_list,
        "recipe_id": recipe_id,
        "recipe_title": resolved_title,
        "source_recipes": [recipe_ref],
        "total_price": sum((item.get("price") or 0) for item in filtered_items if item.get("is_checked") and not item.get("is_purchased")),
        "checked_count": sum(1 for item in filtered_items if item.get("is_checked")),
        "purchased_count": sum(1 for item in filtered_items if item.get("is_purchased")),
        "items": filtered_items,
    }


def _find_existing_recipe_list(db: Session, user_id: int, recipe_title: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    history = shopping_service.get_history(db=db, user_id=user_id, limit=50)
    for shopping_list in history:
        if shopping_list.get("status") != "active":
            continue
        for ref in _recipe_refs(shopping_list):
            if _recipe_ref_matches(recipe_title, ref):
                return shopping_list, ref
    return None


def _missing_to_inputs(items: list[dict[str, Any]]) -> list[ShoppingIngredientInput]:
    return [
        ShoppingIngredientInput(
            name=item["name"],
            ingredient_id=item.get("ingredient_id"),
            amount=item.get("amount"),
        )
        for item in items
        if item.get("name")
    ]


def handle_recipe_current(
    db: Session,
    user_id: int,
    recipe_title: str,
    *,
    start: int = 0,
    max_items: int = 15,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    existing = _find_existing_recipe_list(db, user_id, recipe_title)
    if existing:
        existing_list, recipe_ref = existing
        filtered_list = _filter_list_for_recipe(existing_list, recipe_ref, recipe_title)
        resolved_title = filtered_list.get("recipe_title") or recipe_title
        message = summarize_shopping_list(
            filtered_list,
            max_items=max_items,
            start=start,
            title=f"{resolved_title} 장보기 목록이에요.",
        )
        actions = [shopping_list_action(existing_list.get("id"))]
        shown_count = min(max_items, max(0, len(active_shopping_items(filtered_list)) - start))
        return message, actions, shopping_list_slots(filtered_list, start=start, shown_count=shown_count)

    recipe = _find_recipe_by_title(db, recipe_title)
    if not recipe:
        return f"{recipe_title} 레시피를 찾지 못해서 장보기 목록을 만들 수 없어요.", [], {}

    recipe_id = recipe.get("recipe_id")
    detail = recipe_detail_service.get_recipe_detail(db, recipe_id, user_id)
    missing_inputs = _missing_to_inputs(detail.get("missing_ingredients") or [])
    if not missing_inputs:
        title = detail.get("title") or recipe_title
        return f"{title}은 현재 부족한 재료가 없어요.", [{"label": "레시피 보기", "url": f"/recipes/{recipe_id}"}], {
            "shopping_recipe_id": recipe_id,
            "shopping_recipe_title": title,
            "shopping_total_count": 0,
            "shopping_next_offset": 0,
            "shopping_has_more": False,
        }

    shopping_list = shopping_service.create_list(
        db=db,
        user_id=user_id,
        recipe_id=recipe_id,
        source="recipe",
        missing_ingredients=missing_inputs,
    )
    title = shopping_list.get("recipe_title") or detail.get("title") or recipe_title
    filtered_list = _filter_list_for_recipe(
        shopping_list,
        {"type": "recipe", "recipe_id": recipe_id, "recipe_title": title},
        title,
    )
    message = summarize_shopping_list(
        filtered_list,
        max_items=max_items,
        start=start,
        title=f"{title} 장보기 목록이에요.",
    )
    actions = [shopping_list_action(shopping_list.get("id"))]
    shown_count = min(max_items, max(0, len(active_shopping_items(filtered_list)) - start))
    return message, actions, shopping_list_slots(filtered_list, start=start, shown_count=shown_count)


def handle_current(
    db: Session,
    user_id: int,
    *,
    start: int = 0,
    max_items: int = 15,
    title: str = "현재 장보기 목록이에요.",
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    shopping_list = shopping_service.get_current(db=db, user_id=user_id)
    actions = [shopping_list_action(shopping_list.get("id") if shopping_list else None)]
    message = summarize_shopping_list(shopping_list, max_items=max_items, start=start, title=title)
    shown_count = min(max_items, max(0, len(active_shopping_items(shopping_list)) - start)) if shopping_list else 0
    return message, actions, shopping_list_slots(shopping_list, start=start, shown_count=shown_count)


def handle_recipe_filters(db: Session, user_id: int) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    shopping_list = shopping_service.get_current(db=db, user_id=user_id)
    actions = [shopping_list_action(shopping_list.get("id") if shopping_list else None)]
    refs = _recipe_refs(shopping_list)
    if not refs:
        return "현재 장보기 목록에 연결된 레시피 필터가 없어요.", actions, shopping_list_slots(shopping_list)

    lines = ["현재 장보기 목록에서 볼 수 있는 레시피 필터예요."]
    for index, ref in enumerate(refs, start=1):
        title = ref.get("recipe_title") or f"레시피 {ref.get('recipe_id')}"
        lines.append(f"{index}. {title}")
    return "\n".join(lines), actions, shopping_list_slots(shopping_list)


def handle_current_follow_up(
    db: Session,
    user_id: int,
    text: str,
    slots: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    slots = slots or {}
    if is_show_all_request(text):
        start = 0
        max_items = int(slots.get("shopping_total_count") or 50)
        title = "전체 장보기 목록이에요."
    else:
        start = int(slots.get("shopping_next_offset") or 0)
        max_items = extract_requested_count(text) or 5
        title = "나머지 장보기 재료예요." if is_remaining_request(text) else "현재 장보기 목록이에요."
    return handle_current(db, user_id, start=start, max_items=max_items, title=title)


def handle_price_help() -> tuple[str, list[dict[str, Any]]]:
    return (
        "가격 정보 없음은 조건에 맞는 상품 후보를 찾지 못했거나 판매가를 확인하지 못했다는 뜻이에요. 상품명이나 용량을 더 구체적으로 입력하면 검색 정확도가 좋아질 수 있어요.",
        [],
    )


def handle_owned(db: Session, user_id: int, slots: dict[str, Any] | None = None) -> tuple[str, list[dict[str, Any]]]:
    slots = slots or {}
    shopping_list_id = slots.get("shopping_list_id")
    shopping_list = (
        shopping_service.get_list(db=db, user_id=user_id, shopping_list_id=int(shopping_list_id))
        if shopping_list_id
        else shopping_service.get_current(db=db, user_id=user_id)
    )
    actions = [shopping_list_action(shopping_list.get("id") if shopping_list else None)]
    return summarize_owned_ingredients(shopping_list), actions


def handle_history(db: Session, user_id: int, limit: int = 5) -> tuple[str, list[dict[str, Any]]]:
    history = shopping_service.get_history(db=db, user_id=user_id, limit=limit)
    if not history:
        return "아직 장보기 내역이 없어요.", [shopping_list_action(label="장보기 화면 열기")]

    lines = ["최근 장보기 내역이에요."]
    for index, shopping_list in enumerate(history[:limit], start=1):
        status = "완료" if shopping_list.get("status") == "completed" else "진행 중"
        count = len(shopping_list.get("items") or [])
        title = shopping_list.get("recipe_title") or "직접 만든 목록"
        lines.append(f"{index}. {title} - {status}, {count}개")
    return "\n".join(lines), [shopping_list_action(label="장보기 화면 열기")]


def handle_compare(text: str) -> tuple[str, list[dict[str, Any]]]:
    names = extract_ingredient_names(text)
    if not names:
        return "가격을 비교할 재료를 알려주세요. 예: 두부랑 양파 가격 비교해줘", []

    display = 5 if len(names) == 1 else 3
    rows: list[dict[str, Any]] = []
    missing_names: list[str] = []
    for name in names:
        result = shopping_service.search_products(name, display=display)
        items = result.get("items") or []
        if not items:
            missing_names.append(name)
            continue
        rows.extend(items)

    if not rows:
        return "적절한 상품 후보를 찾지 못했어요. 상품명이나 용량을 더 구체적으로 입력해 주세요.", []

    lines = ["네이버 쇼핑 기준 상품 후보예요."]
    for index, row in enumerate(rows[:5], start=1):
        market = row.get("mall_name") or row.get("best_market") or row.get("provider") or "마켓 정보 없음"
        product_name = row.get("product_name") or row.get("name") or "상품명 없음"
        lines.append(f"{index}. {product_name} - {format_price(row.get('price'))} ({market})")
    if missing_names:
        lines.append(f"{', '.join(missing_names)}은 적절한 상품 후보를 찾지 못했어요.")

    actions = [
        {
            "label": row.get("product_name") or f"{row.get('name')} 상품 보기",
            "url": row.get("product_link") or "",
            "data": {"name": row.get("name"), "price": row.get("price")},
        }
        for row in rows[:5]
        if row.get("product_link")
    ]
    return "\n".join(lines), actions


def handle_selected_product(
    db: Session,
    user_id: int,
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """선택한 외부 상품 스냅샷을 장보기 목록에 반영합니다."""
    ingredient_name = str(candidate.get("name") or "").strip()
    if not ingredient_name:
        raise ValueError("선택 상품의 재료명이 비어 있습니다.")

    shopping_list = shopping_service.create_list(
        db=db,
        user_id=user_id,
        recipe_id=None,
        source="manual",
        missing_ingredients=[
            ShoppingIngredientInput(
                name=ingredient_name,
                provider=candidate.get("provider"),
                product_id=candidate.get("product_id"),
                product_name=candidate.get("product_name"),
                product_link=candidate.get("product_link"),
                product_image=candidate.get("product_image"),
                price=candidate.get("price"),
                mall_name=candidate.get("mall_name"),
            )
        ],
    )

    selected_item = next(
        (
            item
            for item in shopping_list.get("items") or []
            if candidate.get("product_id")
            and str(item.get("product_id") or "") == str(candidate.get("product_id"))
            and not item.get("is_purchased")
        ),
        None,
    )
    if selected_item is None:
        selected_item = find_item_by_name(shopping_list, ingredient_name)
    if selected_item is None:
        raise ValueError("장보기 목록에 반영된 상품을 찾지 못했습니다.")

    return shopping_list, selected_item


def handle_create_request(text: str) -> tuple[str, list[dict[str, Any]]]:
    names = extract_ingredient_names(text)
    if not names:
        return "장보기 목록에 담을 재료를 알려주세요. 예: 두부랑 양파 장보기 목록 만들어줘", []

    summary = ", ".join(names)
    command = "확인:shopping_create:" + "|".join(names)
    is_add_request = any(word in text for word in ("추가", "담아", "넣어", "등록"))
    prompt = f"{summary}를 장보기 목록에 추가할까요?" if is_add_request else f"{summary}로 장보기 목록을 만들까요?"
    return (
        prompt,
        [confirm_action("목록에 추가" if is_add_request else "목록 만들기", command), confirm_action("취소", "취소")],
    )


def handle_create_confirm(db: Session, user_id: int, names: list[str]) -> tuple[str, list[dict[str, Any]]]:
    if not names:
        return "장보기 목록에 담을 재료를 찾지 못했어요.", []

    shopping_list = shopping_service.create_list(
        db=db,
        user_id=user_id,
        recipe_id=None,
        source="manual",
        missing_ingredients=[ShoppingIngredientInput(name=name) for name in names],
    )
    message = summarize_shopping_list(shopping_list)
    return message, [shopping_list_action(shopping_list.get("id"))]


def handle_purchase_request(db: Session, user_id: int, text: str = "") -> tuple[str, list[dict[str, Any]]]:
    shopping_list = shopping_service.get_current(db=db, user_id=user_id)
    if not shopping_list:
        return "구매 완료 처리할 장보기 목록이 없어요.", [shopping_list_action()]

    requested_names = extract_ingredient_names(text)
    if requested_names:
        item = find_item_by_name(shopping_list, text)
        if not item:
            return (
                f"현재 장보기 목록에서 {', '.join(requested_names)} 항목을 찾지 못했어요.",
                [shopping_list_action(shopping_list.get("id"))],
            )
        if item.get("is_purchased"):
            return (
                f"{item.get('name')}은 이미 구매 완료되어 냉장고에 입고된 항목이에요.",
                [shopping_list_action(shopping_list.get("id"))],
            )

        list_id = shopping_list.get("id")
        item_id = item.get("id")
        return (
            f"{item.get('name')} 항목을 구매 완료하고 냉장고에 입고할까요?",
            [
                confirm_action("냉장고에 입고", f"확인:shopping_purchase:{list_id}|{item_id}"),
                confirm_action("취소", "취소"),
            ],
        )

    checked_count = shopping_list.get("checked_count") or 0
    if checked_count == 0:
        return "구매 완료 처리할 체크된 재료가 없어요.", [shopping_list_action(shopping_list.get("id"))]

    list_id = shopping_list.get("id")
    return (
        f"체크된 재료 {checked_count}개를 구매 완료하고 냉장고에 입고할까요?",
        [
            confirm_action("구매 완료", f"확인:shopping_purchase:{list_id}"),
            confirm_action("취소", "취소"),
        ],
    )


def handle_purchase_confirm(
    db: Session,
    user_id: int,
    shopping_list_id: int | None = None,
    item_ids: list[int] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    result = shopping_service.complete_purchase(
        db=db,
        user_id=user_id,
        shopping_list_id=shopping_list_id,
        item_ids=item_ids,
    )
    shopping_list = result.get("shopping_list") or {}
    return result.get("message") or "구매 완료 처리했어요.", [shopping_list_action(shopping_list.get("id"))]


def handle_delete_item_request(db: Session, user_id: int, text: str) -> tuple[str, list[dict[str, Any]]]:
    shopping_list = shopping_service.get_current(db=db, user_id=user_id)
    if not shopping_list:
        return "삭제할 장보기 목록이 없어요.", [shopping_list_action()]

    item = find_item_by_name(shopping_list, text)
    if not item:
        return "어떤 재료를 장보기 목록에서 뺄까요? 재료명을 같이 알려주세요.", [shopping_list_action(shopping_list.get("id"))]

    return (
        f"{item.get('name')}을 장보기 목록에서 뺄까요?",
        [
            confirm_action("빼기", f"확인:shopping_delete_item:{item.get('id')}"),
            confirm_action("취소", "취소"),
        ],
    )


def handle_delete_item_confirm(db: Session, user_id: int, item_id: int) -> tuple[str, list[dict[str, Any]]]:
    shopping_list = shopping_service.delete_item(db=db, user_id=user_id, item_id=item_id)
    return "장보기 목록에서 재료를 뺐어요.", [shopping_list_action(shopping_list.get("id"))]


def handle_check_item(db: Session, user_id: int, text: str) -> tuple[str, list[dict[str, Any]]]:
    shopping_list = shopping_service.get_current(db=db, user_id=user_id)
    if not shopping_list:
        return "체크할 장보기 목록이 없어요.", [shopping_list_action()]

    item = find_item_by_name(shopping_list, text)
    if not item:
        return "어떤 재료를 체크할까요? 재료명을 같이 알려주세요.", [shopping_list_action(shopping_list.get("id"))]

    checked = "해제" not in text and "풀" not in text
    updated = shopping_service.update_item(
        db=db,
        user_id=user_id,
        item_id=item["id"],
        is_checked=checked,
        is_purchased=None,
    )
    state_text = "체크했어요" if checked else "체크를 해제했어요"
    return f"{item.get('name')} {state_text}.", [shopping_list_action(updated.get("id"))]
