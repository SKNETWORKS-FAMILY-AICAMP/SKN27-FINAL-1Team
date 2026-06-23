import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.db.session import SessionLocal
from app.backend.schemas.inventory import IngredientCreate
from app.backend.services.inventory_service.inventory_service import inventory_service

def debug_add_ingredient():
    db = SessionLocal()
    try:
        user_id = 1 # 임의의 사용자 ID
        data = IngredientCreate(
            name="디버깅 대파",
            category="채소",
            quantity=1.0,
            unit="단",
            storage_method="실온",
            expiration_date=None
        )
        print("1. 데이터 준비 완료")
        
        result = inventory_service.add_ingredient(db=db, user_id=user_id, data=data)
        
        print("2. 결과:", result)
        print("-> expiration_date:", result.get("expiration_date"))
        
    except Exception as e:
        print("!!! 에러 발생 !!!", str(e))
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    debug_add_ingredient()
