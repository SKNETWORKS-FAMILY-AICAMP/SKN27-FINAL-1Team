from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.backend.api.calendar.calendar_api import (
    _create_event_once,
    _delete_event_once,
    _get_access_token,
    _get_google_integration,
)
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
KST = timezone(timedelta(hours=9))


def _parse_receipt_calendar_datetime(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(normalized, fmt).replace(tzinfo=KST)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)


@router.get("/history", response_model=ReceiptHistoryResponse)
def get_receipt_history(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Return the user's most recently registered receipts with their items."""
    receipts = receipt_history_service.get_recent_receipts(db=db, user_id=current_user_id, limit=limit)
    return {"receipts": receipts}


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """영수증 이미지를 OCR 분석하고, 사용자가 확인할 품목 후보를 반환한다."""
    return await receipt_ocr_service.analyze_upload(db=db, file=file, user_id=current_user_id)


@router.post("/confirm", response_model=MessageResponse)
async def confirm_receipt_items(
    request_data: ReceiptConfirmRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """사용자가 확정한 OCR 품목을 냉장고에 입고하고, 사용비용 캘린더 이벤트를 선택 등록한다."""
    saved_item_count = receipt_confirm_service.save_confirmed_items(
        db=db,
        user_id=current_user_id,
        request_data=request_data,
    )
    total_price = sum(item.item_amount or 0 for item in request_data.items)
    purchase_datetime = _parse_receipt_calendar_datetime(request_data.purchase_datetime)

    try:
        # 영수증 입고 비용은 스케줄러가 아니라 확정 시점에 바로 캘린더에 남기거나 정리한다.
        integration = _get_google_integration(db, current_user_id)
        access_token = await _get_access_token(integration, db)
        event_key = f"receipt-cost-{current_user_id}-{request_data.receipt_id}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            if request_data.calendar_cost_enabled and total_price > 0 and purchase_datetime:
                event = {
                    "summary": f"식재료 사용비용 {total_price:,}원",
                    "description": f"OCR 입고 {len(request_data.items)}개 항목 기준 사용비용입니다.",
                    "start": {"dateTime": purchase_datetime.isoformat()},
                    "end": {"dateTime": (purchase_datetime + timedelta(minutes=10)).isoformat()},
                    "colorId": "6",
                }
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
            else:
                await _delete_event_once(
                    client,
                    integration.calendar_id,
                    access_token,
                    event_key,
                    db,
                    current_user_id,
                    "receipt",
                )
    except HTTPException as exc:
        if exc.status_code != 404:
            print(f"[ReceiptCalendar] user_id={current_user_id} failed: {exc}")
    except Exception as exc:
        print(f"[ReceiptCalendar] user_id={current_user_id} failed: {exc}")

    return {"message": f"성공적으로 {saved_item_count}개 품목을 저장했습니다."}
