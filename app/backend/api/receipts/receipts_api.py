import json
from datetime import datetime, timedelta, timezone
from pathlib import Path as FsPath
from typing import List, Optional

import httpx

from fastapi import APIRouter, Depends, File, Form, Path, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.backend.api.calendar.calendar_api import (
    _create_event_once,
    _delete_event_once,
    _get_access_token,
    _get_google_integration,
)
from app.backend.api.deps import get_current_user_required
from app.backend.core.config import settings
from app.backend.db.models import Receipt
from app.backend.db.session import get_db
from app.backend.schemas.common import MessageResponse
from app.backend.schemas.receipts import (
    ReceiptConfirmRequest,
    ReceiptHistoryEntry,
    ReceiptHistoryResponse,
    ReceiptUpdateRequest,
    ReceiptUploadResponse,
)
from app.backend.services.receipt_ocr_service import (
    receipt_confirm_service,
    receipt_history_service,
    receipt_ocr_service,
)


router = APIRouter(prefix="/receipts", tags=["Receipts (OCR)"])
KST = timezone(timedelta(hours=9))
PROJECT_ROOT = FsPath(__file__).resolve().parents[4]
OLD_RECEIPT_WARNING_DAYS = 30


def _format_sse_event(payload: dict) -> str:
    event_name = payload.get("type", "message")
    return f"event: {event_name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


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


def _get_receipt_age_in_days(value: str | None, *, now: datetime | None = None) -> int | None:
    purchase_datetime = _parse_receipt_calendar_datetime(value)
    if purchase_datetime is None:
        return None

    current_datetime = now or datetime.now(KST)
    if current_datetime.tzinfo is None:
        current_datetime = current_datetime.replace(tzinfo=KST)

    purchase_date = purchase_datetime.astimezone(KST).date()
    current_date = current_datetime.astimezone(KST).date()
    return (current_date - purchase_date).days


@router.get("/history", response_model=ReceiptHistoryResponse)
def get_receipt_history(
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    limit: int = Query(default=10, ge=1, le=100),
):
    """Return the user's most recently registered receipts with their items."""
    receipts = receipt_history_service.get_recent_receipts(db=db, user_id=current_user_id, limit=limit)
    return {"receipts": receipts}


@router.patch("/{receipt_id}", response_model=ReceiptHistoryEntry)
def update_receipt(
    request_data: ReceiptUpdateRequest,
    receipt_id: int = Path(..., ge=1),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Update a receipt's store name (title)."""
    return receipt_history_service.update_store_name(
        db=db,
        user_id=current_user_id,
        receipt_id=receipt_id,
        store_name=request_data.store_name,
    )


@router.delete("/{receipt_id}", response_model=MessageResponse)
def delete_receipt(
    receipt_id: int = Path(..., ge=1),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Delete a receipt and its items. Stocked fridge items are preserved."""
    receipt_history_service.delete_receipt(db=db, user_id=current_user_id, receipt_id=receipt_id)
    return {"message": "영수증 내역을 삭제했어요."}


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    crop_mode: str = Form("auto"),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """영수증 이미지를 OCR 분석하고, 사용자가 확인할 품목 후보를 반환한다."""
    return await receipt_ocr_service.analyze_upload(
        db=db,
        files=files,
        file=file,
        user_id=current_user_id,
        crop_mode=crop_mode,
    )


@router.post("/upload/stream")
async def upload_receipt_stream(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    crop_mode: str = Form("auto"),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Stream receipt OCR LangGraph stages and final upload result as SSE."""
    event_stream = await receipt_ocr_service.create_upload_event_stream(
        db=db,
        files=files,
        file=file,
        user_id=current_user_id,
        crop_mode=crop_mode,
    )

    async def sse_stream():
        async for payload in event_stream:
            yield _format_sse_event(payload)

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{receipt_id}/image")
def get_receipt_image(
    receipt_id: int = Path(..., ge=1),
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return the final receipt image used for OCR preview."""
    receipt = (
        db.query(Receipt)
        .filter(
            Receipt.id == receipt_id,
            Receipt.user_id == current_user_id,
        )
        .first()
    )
    if not receipt or not receipt.original_file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt image not found.")

    upload_root = (PROJECT_ROOT / settings.OCR_UPLOAD_DIR).resolve()
    image_path = (PROJECT_ROOT / receipt.original_file_path).resolve()
    if upload_root not in image_path.parents:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid receipt image path.")
    if not image_path.exists() or not image_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt image file not found.")

    media_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(image_path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        image_path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/confirm", response_model=MessageResponse)
async def confirm_receipt_items(
    request_data: ReceiptConfirmRequest,
    current_user_id: int = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """사용자가 확정한 OCR 품목을 냉장고에 입고하고, 사용비용 캘린더 이벤트를 선택 등록한다."""
    receipt_age_in_days = _get_receipt_age_in_days(request_data.purchase_datetime)
    if (
        receipt_age_in_days is not None
        and receipt_age_in_days > OLD_RECEIPT_WARNING_DAYS
        and not request_data.old_receipt_confirmed
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="구매일로부터 30일이 지난 영수증입니다. 소비기한 경고를 확인한 뒤 다시 입고해주세요.",
        )

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
