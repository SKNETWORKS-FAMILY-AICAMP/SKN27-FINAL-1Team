from fastapi import APIRouter, Depends, File, UploadFile

from app.backend.api.deps import get_current_user_required
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
def confirm_receipt_items(
    request_data: ReceiptConfirmRequest,
    current_user_id: int = Depends(get_current_user_required),
):
    """
    사용자가 검수한 OCR 결과를 냉장고에 일괄 입고합니다.
    현재는 API 계약 확인용 임시 응답을 반환합니다.
    """
    return {"message": "성공적으로 입고되었습니다."}
