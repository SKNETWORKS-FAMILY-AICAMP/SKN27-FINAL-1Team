import base64
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from openai import OpenAI
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.backend.core.config import settings
from app.backend.db.models import Receipt
from app.backend.services.ingredient_match_service import ingredient_name_matcher


PROJECT_ROOT = Path(__file__).resolve().parents[4]
KST = timezone(timedelta(hours=9))
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_UNITS = {"개", "kg"}


class ReceiptOcrService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def analyze_upload(self, *, db: Session, file: UploadFile, user_id: int) -> Dict[str, Any]:
        image_bytes = await file.read()
        self._validate_upload(file, image_bytes)

        original_file_path = self._save_original_image(
            user_id=user_id,
            original_file_name=file.filename or "receipt",
            image_bytes=image_bytes,
        )

        try:
            image_id = Path(file.filename or original_file_path).stem
            ocr_result = await run_in_threadpool(
                self._call_openai_vision,
                image_bytes=image_bytes,
                filename=file.filename or "receipt.jpg",
                image_id=image_id,
            )
            normalized = self._normalize_ocr_result(ocr_result, image_id=image_id, db=db)

            receipt = Receipt(
                user_id=user_id,
                original_file_name=file.filename,
                original_file_path=original_file_path,
                store_name=normalized.get("store_name"),
                purchased_at=self._parse_purchase_datetime(normalized.get("purchase_datetime")),
                total_price=normalized.get("total_amount"),
            )
            db.add(receipt)
            db.commit()
            db.refresh(receipt)
        except Exception:
            db.rollback()
            self._delete_saved_file(original_file_path)
            raise

        return {
            "receipt_id": receipt.id,
            "original_file_name": receipt.original_file_name,
            "original_file_path": receipt.original_file_path,
            "store_name": normalized.get("store_name"),
            "purchase_datetime": normalized.get("purchase_datetime"),
            "items": normalized.get("items", []),
            "total_item_count": normalized.get("total_item_count"),
            "total_amount": normalized.get("total_amount"),
            "currency": normalized.get("currency", "KRW"),
            "confidence_note": normalized.get("confidence_note"),
        }

    def _validate_upload(self, file: UploadFile, image_bytes: bytes) -> None:
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="업로드된 파일이 비어 있습니다.")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(image_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"파일 크기는 {settings.MAX_UPLOAD_SIZE_MB}MB 이하만 허용됩니다.",
            )

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="지원하지 않는 이미지 형식입니다. jpg, jpeg, png, webp만 업로드할 수 있습니다.",
            )

    def _save_original_image(self, *, user_id: int, original_file_name: str, image_bytes: bytes) -> str:
        suffix = Path(original_file_name).suffix.lower() or ".jpg"
        today = datetime.now(KST).strftime("%Y%m%d")
        safe_stem = self._safe_filename(Path(original_file_name).stem or "receipt")
        stored_name = f"{today}_{uuid4().hex[:12]}_{safe_stem}{suffix}"

        upload_root = self._resolve_storage_root(settings.OCR_UPLOAD_DIR)
        user_dir = upload_root / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        stored_path = user_dir / stored_name
        stored_path.write_bytes(image_bytes)
        return self._to_project_relative_path(stored_path)

    def _call_openai_vision(self, *, image_bytes: bytes, filename: str, image_id: str) -> Dict[str, Any]:
        if settings.OCR_ENGINE != "openai_vision":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="지원하지 않는 OCR_ENGINE 설정입니다.")
        if not self.client:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

        mime_type = self._guess_mime_type(filename)
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        prompt = self._build_prompt(image_id)

        try:
            response = self.client.chat.completions.create(
                model=settings.OCR_MODEL,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OCR 모델 호출에 실패했습니다: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OCR 모델 응답이 비어 있습니다.")

        try:
            return self._parse_json_object(content)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    def _normalize_ocr_result(self, result: Dict[str, Any], *, image_id: str, db: Session) -> Dict[str, Any]:
        items = []
        for item in result.get("items") or []:
            raw_name = self._nullable_str(item.get("raw_name"))
            if not raw_name:
                continue

            unit = self._nullable_str(item.get("unit"))
            matched_ingredient = ingredient_name_matcher.find_best_ingredient(db, raw_name)
            items.append(
                {
                    "raw_name": raw_name,
                    "normalized_name": matched_ingredient.name if matched_ingredient else raw_name,
                    "quantity": self._nullable_number(item.get("quantity")),
                    "unit": unit if unit in ALLOWED_UNITS else "개",
                    "item_amount": self._nullable_int(item.get("item_amount")),
                }
            )

        return {
            "image_id": self._nullable_str(result.get("image_id")) or image_id,
            "store_name": self._nullable_str(result.get("store_name")),
            "purchase_datetime": self._nullable_str(result.get("purchase_datetime")),
            "items": items,
            "total_item_count": self._nullable_number(result.get("total_item_count")),
            "total_amount": self._nullable_int(result.get("total_amount")),
            "currency": "KRW",
            "confidence_note": self._nullable_str(result.get("confidence_note")),
        }

    def _build_prompt(self, image_id: str) -> str:
        return f"""
너는 한국어 영수증 OCR 및 구조화 데이터 추출 도우미다.

입력 이미지에서 아래 정보를 추출해라.
- 상호명
- 구매일시
- 품목명
- 품목별 수량
- 품목별 단위: "개" 또는 "kg"
- 품목별 라인 금액
- 총 상품 개수
- 최종 결제 총액

반드시 JSON 객체만 반환해라. 설명, Markdown, 코드블록, 주석은 출력하지 마라.

출력 스키마:
{{
  "image_id": "{image_id}",
  "store_name": "string|null",
  "purchase_datetime": "YYYY-MM-DD HH:mm:ss|null",
  "items": [
    {{
      "raw_name": "string",
      "quantity": "number|null",
      "unit": "개|kg|null",
      "item_amount": "number|null"
    }}
  ],
  "total_item_count": "number|null",
  "total_amount": "number|null",
  "currency": "KRW",
  "confidence_note": "string|null"
}}

규칙:
1. image_id는 "{image_id}"를 그대로 사용한다.
2. 실제 구매 품목 또는 메뉴만 items에 넣는다.
3. 합계, 부가세, 결제수단, 카드번호, 승인번호, 안내문구는 품목에서 제외한다.
4. 할인 라인과 0원 옵션 라인은 품목에서 제외한다.
5. 품목 리스트가 없는 카드전표/전자영수증은 items를 빈 배열로 반환한다.
6. quantity는 숫자로 반환하고, 정수와 소수를 모두 허용한다. 모르면 null로 둔다.
7. unit은 "개", "kg", null 중 하나만 사용한다. g 단위 판매 품목은 kg로 변환할 수 있으면 변환한다.
8. ml, L 같은 용량 정보는 unit에 넣지 말고 raw_name에 유지한다.
9. item_amount는 단가가 아니라 해당 품목 라인의 금액이다.
10. total_amount는 참고값이다. 불확실하면 null로 둔다.
11. 불확실한 품목명, 잘림, 흐림, 추정값은 confidence_note에 짧게 적는다.
""".strip()

    def _parse_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        candidate = fenced.group(1).strip() if fenced else text
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise ValueError("OCR 모델 응답에서 JSON 객체를 찾지 못했습니다.")
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"OCR 모델 응답 JSON 파싱에 실패했습니다: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("OCR 모델 응답이 JSON 객체가 아닙니다.")
        return parsed

    def _parse_purchase_datetime(self, value: Optional[str]) -> Optional[datetime]:
        if not value:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(value, fmt).replace(tzinfo=KST)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=KST)

    def _resolve_storage_root(self, path_value: str) -> Path:
        path = Path(path_value)
        return path if path.is_absolute() else PROJECT_ROOT / path

    def _to_project_relative_path(self, path: Path) -> str:
        try:
            return path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            return path.as_posix()

    def _delete_saved_file(self, relative_or_absolute_path: str) -> None:
        path = Path(relative_or_absolute_path)
        target = path if path.is_absolute() else PROJECT_ROOT / path
        try:
            if target.is_file():
                target.unlink()
        except OSError:
            pass

    def _safe_filename(self, value: str) -> str:
        safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", value).strip("._")
        return safe[:80] or "receipt"

    def _guess_mime_type(self, filename: str) -> str:
        suffix = Path(filename).suffix.lower()
        if suffix in {".jpg", ".jpeg"}:
            return "image/jpeg"
        if suffix == ".png":
            return "image/png"
        if suffix == ".webp":
            return "image/webp"
        return "application/octet-stream"

    def _nullable_str(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() == "null":
            return None
        return text

    def _nullable_number(self, value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _nullable_int(self, value: Any) -> Optional[int]:
        number = self._nullable_number(value)
        if number is None:
            return None
        return int(round(number))


receipt_ocr_service = ReceiptOcrService()
