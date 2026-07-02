import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

# 직접 실행해도 프로젝트 루트 기준 import가 가능하도록 경로를 맞춥니다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.services.inventory_service.inventory_service import _object_particle, inventory_service

def test_map_to_response_defaults_empty_category_to_etc() -> None:
    """마스터 카테고리가 비어 있으면 프론트 응답에서는 기타로 표시합니다."""
    item = SimpleNamespace(
        id=1,
        display_name="호박",
        quantity=1,
        unit="개",
        storage_location="냉장",
        purchased_date=date.today(),
        expiry_date=date.today(),
        created_at=None,
    )
    ingredient = SimpleNamespace(name="호박", category=None, default_unit="개")

    response = inventory_service._map_to_response(item, ingredient)

    assert response["category"] == "기타"

def test_object_particle_matches_final_consonant() -> None:
    """식재료명 받침에 맞춰 을/를 조사를 고릅니다."""
    assert _object_particle("버터") == "를"
    assert _object_particle("김치") == "를"
    assert _object_particle("귤") == "을"
    assert _object_particle("egg") == "를"

if __name__ == "__main__":
    test_map_to_response_defaults_empty_category_to_etc()
    test_object_particle_matches_final_consonant()
    print("inventory service tests ok")
