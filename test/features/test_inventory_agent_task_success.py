"""Inventory Agent의 도구 실행과 최종 DB 상태를 함께 검증합니다."""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from ai.agents.inventory_agent.inventory_agent import execute_inventory_action
from app.backend.db.models import FridgeItem
from app.backend.schemas.inventory import IngredientCreate
from app.backend.services.inventory_service.inventory_service import inventory_service


def _test_db():
    """InventoryService가 사용하는 최소 테이블만 가진 메모리 DB 세션을 만듭니다."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE ingredients ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(100) NOT NULL, normalized_name VARCHAR(100) NOT NULL UNIQUE, "
                "category VARCHAR(100), default_unit VARCHAR(30), "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE ingredient_aliases ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ingredient_id INTEGER NOT NULL, "
                "alias_name VARCHAR(100) NOT NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE ingredient_storage_standards ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, ingredient_id INTEGER NOT NULL, "
                "storage_location VARCHAR(50) NOT NULL, lifespan_days INTEGER NOT NULL, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE fridge_items ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, ingredient_id INTEGER NOT NULL, "
                "receipt_item_id INTEGER, display_name VARCHAR(255), quantity NUMERIC(10, 2), "
                "unit VARCHAR(30), storage_location VARCHAR(50), purchased_date DATE, expiry_date DATE, "
                "status VARCHAR(30) NOT NULL DEFAULT 'normal', is_ai_recommended BOOLEAN NOT NULL DEFAULT 0, "
                "created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL)"
            )
        )
    return sessionmaker(bind=engine)()


def _seed_item(db, *, name: str = "감자", quantity: float = 3, storage: str = "냉장"):
    """테스트 시작 전 수량 검증에 사용할 냉장고 식재료를 실제 서비스로 등록합니다."""
    return inventory_service.add_ingredient(
        db,
        user_id=1,
        data=IngredientCreate(
            name=name,
            category="채소",
            quantity=quantity,
            unit="개",
            storage_method=storage,
        ),
        prepared_rule=(storage, 7),
        validate_name=False,
    )


def _active_quantity(db, name: str) -> Decimal:
    """소비 또는 폐기 후 남아 있는 활성 식재료 수량을 합산합니다."""
    rows = (
        db.query(FridgeItem)
        .filter(FridgeItem.user_id == 1, FridgeItem.display_name == name, FridgeItem.status != "used")
        .all()
    )
    return sum((Decimal(str(row.quantity)) for row in rows), Decimal("0"))


@pytest.mark.parametrize(
    ("initial_quantity", "requested_quantity", "expected_quantity"),
    [
        (1, 1, 0),
        (2, 1, 1),
        (3, 2, 1),
        (5, 5, 0),
        (2, 3, 0),
        (4, 1.5, 2.5),
    ],
)
def test_inventory_consume_action_changes_test_db_state(
    initial_quantity,
    requested_quantity,
    expected_quantity,
):
    """소비 도구는 요청 수량만큼 차감하고 초과 요청은 보유 수량까지만 처리해야 합니다."""
    db = _test_db()
    _seed_item(db, quantity=initial_quantity)

    result = execute_inventory_action(
        "consume_ingredient",
        ["confirm", "consume_ingredient", "감자", str(requested_quantity)],
        db,
        user_id=1,
    )

    assert result["slots"] == {"inventory_pending": None}
    assert _active_quantity(db, "감자") == Decimal(str(expected_quantity))


@pytest.mark.parametrize("requested_quantity", [1, 2, 3])
def test_inventory_discard_action_changes_test_db_state(requested_quantity):
    """폐기 도구도 소비와 동일하게 DB의 수량 또는 활성 상태를 갱신해야 합니다."""
    db = _test_db()
    _seed_item(db, name="양파", quantity=2)

    result = execute_inventory_action(
        "delete_ingredient",
        ["confirm", "delete_ingredient", "양파", str(requested_quantity)],
        db,
        user_id=1,
    )

    assert result["slots"] == {"inventory_pending": None}
    assert _active_quantity(db, "양파") == Decimal(str(max(2 - requested_quantity, 0)))


def test_inventory_tool_rejects_invalid_quantity_without_changing_test_db_state():
    """0 이하 수량은 도구 호출 전에 차단되어 DB 상태가 바뀌지 않아야 합니다."""
    db = _test_db()
    _seed_item(db, quantity=2)

    result = execute_inventory_action(
        "consume_ingredient",
        ["confirm", "consume_ingredient", "감자", "0"],
        db,
        user_id=1,
    )

    assert result["slots"] == {"inventory_pending": None}
    assert _active_quantity(db, "감자") == Decimal("2")


@pytest.mark.parametrize(
    ("name", "quantity", "storage"),
    [
        ("감자", 1, "냉장"),
        ("대파", 2, "냉장"),
        ("새우", 1, "냉동"),
    ],
)
def test_inventory_add_action_creates_item_in_test_db(monkeypatch, name, quantity, storage):
    """등록 도구는 확인된 식재료와 보관 위치로 새 냉장고 행을 생성해야 합니다."""
    db = _test_db()
    db.execute(
        text(
            "INSERT INTO ingredients (name, normalized_name, category, default_unit) "
            "VALUES (:name, :normalized_name, '기타', '개')"
        ),
        {"name": name, "normalized_name": name.replace(" ", "").lower()},
    )
    db.commit()

    # 외부 보관 기간 예측 대신 고정 규칙을 사용해 DB 쓰기 경로만 검증합니다.
    monkeypatch.setattr(
        inventory_service,
        "_predict_storage_rule",
        lambda _name, _category, requested_storage: (requested_storage or "냉장", 7),
    )

    result = execute_inventory_action(
        "add_ingredient",
        ["confirm", "add_ingredient", name, str(quantity), storage],
        db,
        user_id=1,
    )

    assert result["slots"] == {"inventory_pending": None}
    assert _active_quantity(db, name) == Decimal(str(quantity))