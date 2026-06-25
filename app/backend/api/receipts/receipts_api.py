from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.backend.api.calendar.calendar_api import _create_event_once, _get_access_token, _get_google_integration
from app.backend.api.deps import get_current_user_required
from app.backend.db.session import get_db
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.receipts import (
    ReceiptConfirmRequest,
    ReceiptHistoryResponse,
    ReceiptUploadResponse,
)
from app.backend.services.receipt_ocr_service import (
    receipt_confirm_service,
    receipt_history_service,
    receipt_ocr_service,
)


router = APIRouter(prefix="/receipts", tags=["Receipts (OCR)"])


@router.get("/history", response_model=ReceiptHistoryResponse)
def get_receipt_history(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return the user's most recently registered receipts with their items."""
    receipts = receipt_history_service.get_recent_receipts(db=db, user_id=current_user_id)
    return {"receipts": receipts}


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Upload a receipt image and return OCR item candidates."""
    return await receipt_ocr_service.analyze_upload(db=db, file=file, user_id=current_user_id)


@router.post("/confirm", response_model=MessageResponse)
async def confirm_receipt_items(
    request_data: ReceiptConfirmRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Confirm edited OCR results and prepare them for stock-in."""
    saved_item_count = receipt_confirm_service.save_confirmed_items(
        db=db,
        user_id=current_user_id,
        request_data=request_data,
    )
    total_price = sum(item.item_amount or 0 for item in request_data.items)

    if request_data.calendar_cost_enabled and total_price > 0:
        try:
            integration = _get_google_integration(db, current_user_id)
            access_token = await _get_access_token(integration, db)
            now = datetime.now(timezone(timedelta(hours=9)))
            event_key = f"receipt-cost-{current_user_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
            event = {
                "summary": f"식재료 사용비용 {total_price:,}원",
                "description": f"OCR 입고 {len(request_data.items)}개 항목 기준 사용비용입니다.",
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

    return {"message": f"성공적으로 {saved_item_count}개 품목을 저장했습니다."}
