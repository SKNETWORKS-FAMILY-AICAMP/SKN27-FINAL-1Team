from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.backend.api.deps import get_current_user_required
from app.backend.api.calendar.calendar_api import _create_event_once, _get_access_token, _get_google_integration
from app.backend.db.session import get_db
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.receipts import ReceiptConfirmRequest, ReceiptUploadResponse


router = APIRouter(prefix="/receipts", tags=["Receipts (영수증 OCR)"])


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_required),
):
    """
    영수증 이미지를 업로드하고 OCR 파싱 후보를 반환합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {
        "items": [
            {"name": "우유", "qty": 1, "price": 2500},
            {"name": "계란", "qty": 1, "price": 6900},
        ]
    }


@router.post("/confirm", response_model=MessageResponse)
async def confirm_receipt_items(
    request_data: ReceiptConfirmRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    사용자가 검수한 OCR 결과를 냉장고에 일괄 입고합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    total_price = sum(item.price or 0 for item in request_data.items)

    if request_data.calendar_cost_enabled and total_price > 0:
        try:
            integration = _get_google_integration(db, current_user_id)
            access_token = await _get_access_token(integration, db)
            now = datetime.now(timezone(timedelta(hours=9)))
            event_key = f"receipt-cost-{current_user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            event = {
                "summary": f"식재료 사용비용 {total_price:,}원",
                "description": f"OCR 입고 {len(request_data.items)}개 품목 기준 사용비용입니다.",
                "start": {"dateTime": now.isoformat()},
                "end": {"dateTime": (now + timedelta(minutes=10)).isoformat()},
                "colorId": "6",
            }
            async with httpx.AsyncClient(timeout=10.0) as client:
                await _create_event_once(
                    client,
                    integration.calendar_id,
                    access_token,
                    event_key,
                    event,
                    db,
                    current_user_id,
                    "receipt",
                )
        except Exception as exc:
            print(f"[ReceiptCalendar] user_id={current_user_id} failed: {exc}")

    return {"message": "성공적으로 입고되었습니다."}
