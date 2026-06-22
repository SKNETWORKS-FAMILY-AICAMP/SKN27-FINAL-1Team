# FastAPI 백엔드 작성 가이드

이 문서는 `밥벌이(Bobbeori)` API 정의서를 FastAPI 코드로 옮길 때 따르는 기본 규칙입니다. API 정의서가 변경될 수 있으므로, 초반에는 라우터와 스키마로 계약을 먼저 맞추고 내부 구현은 mock, service, DB 순서로 채웁니다.

## 기본 구조

```text
app/backend/
  main.py
  core/
    config.py
    security.py
  db/
    base.py
    session.py
    models.py
  api/
    deps.py
    auth/auth_api.py
    onboarding/onboarding_api.py
    inventory/inventory_api.py
    receipts/receipts_api.py
    guide/guide_api.py
    recipes/recipes_api.py
    shopping/shopping_api.py
    notifications/notifications_api.py
  schemas/
    auth.py
    onboarding.py
    inventory.py
    receipts.py
    guide.py
    recipes.py
    shopping.py
    notifications.py
    common.py
  services/
    {domain}_service/
      {domain}_service.py
```

현재 구현되어 있는 service 디렉터리는 `auth_service`, `onboarding_service`, `inventory_service`, `receipt_ocr_service`, `guide_service`, `recommendation_service`입니다. `shopping`과 `notifications`는 2차 기능 또는 담당자 구현 시점에 service 디렉터리를 추가합니다.

## 작성 순서

1. API 정의서에서 담당 도메인과 path를 확인합니다.
2. `schemas/{domain}.py`에 Request/Response 모델을 먼저 작성합니다.
3. `api/{domain}/{domain}_api.py`에 `APIRouter`를 작성합니다.
4. 복잡한 로직은 `services/{domain}_service/`로 분리합니다.
5. DB 접근이 필요하면 `db/models.py` 모델과 `Depends(get_db)`를 사용합니다.
6. 새 라우터는 `main.py`에 `app.include_router(..., prefix="/api/v1")`로 등록합니다.

## 라우터 규칙

- 라우터 파일 이름은 `{domain}_api.py`를 사용합니다.
- 라우터 내부 prefix는 도메인 단위로 둡니다.
- `main.py`에서 공통 prefix `/api/v1`을 붙입니다.
- 소셜 로그인과 개발용 로그인 외 API는 기본적으로 `get_current_user_required`를 사용합니다.
- 아직 실제 로직이 준비되지 않은 API는 정의서의 응답 형태에 맞춰 임시 응답을 반환하고, docstring에 임시 응답임을 표시합니다.

```python
from fastapi import APIRouter, Depends

from app.backend.api.deps import get_current_user_required

router = APIRouter(prefix="/inventory", tags=["Inventory (나의 냉장고)"])


@router.get("")
def get_inventory(current_user_id: int = Depends(get_current_user_required)):
    return []
```

## 스키마 규칙

- 요청 모델은 `Request`, 생성 모델은 `Create`, 응답 모델은 `Response` suffix를 사용합니다.
- 프론트와 맞춰야 하는 필드는 스키마에 먼저 반영합니다.
- DB ORM 객체를 바로 응답할 모델에는 `from_attributes = True`를 설정합니다.

```python
from pydantic import BaseModel, Field


class IngredientCreate(BaseModel):
    name: str = Field(..., description="식재료 이름")
    quantity: float = Field(default=1, description="수량")


class IngredientResponse(IngredientCreate):
    id: int

    class Config:
        from_attributes = True
```

## 서비스 규칙

API 함수는 HTTP 요청/응답만 담당하고, 실제 계산과 DB 처리는 service에 둡니다.

```python
class InventoryService:
    def add_ingredient(self, db, user_id, data):
        # 식재료 생성, 소비기한 계산, DB 저장을 처리합니다.
        pass


inventory_service = InventoryService()
```

## 인증 규칙

- 인증이 필요한 API는 다음 의존성을 추가합니다.
- Swagger UI에서는 우측 상단 Authorize 버튼에 `Bearer` 토큰을 넣고 테스트합니다.
- 로컬 개발 중에는 `POST /api/v1/auth/dev-login`으로 테스트용 access token을 발급받을 수 있습니다.

```python
current_user_id: int = Depends(get_current_user_required)
```

## 현재 API 도메인

| 도메인 | Router | Prefix |
|:---|:---|:---|
| Auth | `auth_api.py` | `/api/v1/auth` |
| Onboarding | `onboarding_api.py` | `/api/v1/onboarding` |
| Inventory | `inventory_api.py` | `/api/v1/inventory` |
| Receipts | `receipts_api.py` | `/api/v1/receipts` |
| Guide | `guide_api.py` | `/api/v1/guide` |
| Recipes | `recipes_api.py` | `/api/v1/recipes` |
| Shopping List | `shopping_api.py` | `/api/v1/shopping-list` |
| Notifications | `notifications_api.py` | `/api/v1/notifications` |

## 현재 구현 상태

| 도메인 | 상태 |
|:---|:---|
| Auth | 기존 구현 유지 |
| Onboarding | 기존 구현 유지 |
| Inventory | 기존 구현 유지 |
| Receipts | API 정의서 기준 stub |
| Guide | API 정의서 기준 stub |
| Recipes | API 정의서 기준 stub |
| Shopping List | API 정의서 기준 stub |
| Notifications | API 정의서 기준 stub |

stub API는 프론트 연동과 Swagger 계약 확인을 위한 임시 구현입니다. 담당자가 실제 기능을 구현할 때는 라우터의 응답 형태를 유지하면서 service 호출로 교체합니다.

## 로컬 실행

프로젝트 루트에서 실행합니다.

```bash
uvicorn app.backend.main:app --reload
```

DB가 준비되지 않은 로컬 개발에서는 `.env`의 `DB_ENGINE=sqlite`를 사용하면 빠르게 확인할 수 있습니다. PowerShell에서 임시로 SQLite를 사용할 때는 다음처럼 실행합니다.

```powershell
$env:DB_ENGINE="sqlite"
uvicorn app.backend.main:app --reload
```

## 확인 방법

```bash
python -m compileall app ai etl test
```

```bash
cd app/frontend
npm.cmd run build
```

백엔드 smoke test 예시는 다음과 같습니다.

```powershell
$env:DB_ENGINE="sqlite"
python -c "from fastapi.testclient import TestClient; from app.backend.main import app; c=TestClient(app); print(c.get('/').status_code)"
```

Swagger 문서는 서버 실행 후 `http://localhost:8000/docs`에서 확인합니다.
