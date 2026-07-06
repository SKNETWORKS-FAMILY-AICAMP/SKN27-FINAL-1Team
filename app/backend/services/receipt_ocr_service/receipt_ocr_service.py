import base64
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional, TypedDict
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from langgraph.graph import END, StateGraph
from openai import OpenAI
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.backend.core.config import settings
from app.backend.db.models import Receipt
from app.backend.services.ingredient_match_service import ingredient_name_matcher


PROJECT_ROOT = Path(__file__).resolve().parents[4]
KST = timezone(timedelta(hours=9))
DEFAULT_UNIT = "\uac1c"
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
CANONICAL_EXTENSION_BY_IMAGE_TYPE = {
    "jpeg": ".jpg",
    "png": ".png",
    "webp": ".webp",
}
ALLOWED_UNITS = {DEFAULT_UNIT, "kg"}
OCR_MIN_QUALITY_SCORE = 0.75
OCR_MAX_RETRIES = 1


class ReceiptOcrGraphState(TypedDict, total=False):
    db: Session
    user_id: int
    image_bytes: bytes
    image_id: str
    original_file_name: str
    original_file_path: str
    ocr_result: Dict[str, Any]
    normalized: Dict[str, Any]
    receipt_id: int
    retry_count: int
    max_retries: int
    quality_score: float
    quality_issues: List[str]
    ocr_status: str
    ocr_error_message: Optional[str]
    receipt_validation_issues: List[str]
    stage: str
    response: Dict[str, Any]


class ReceiptOcrService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.graph = self._build_graph()
        self._upload_attempts_by_user: dict[int, List[datetime]] = defaultdict(list)
        self._upload_rate_limit_lock = Lock()

    async def analyze_upload(self, *, db: Session, file: UploadFile, user_id: int) -> Dict[str, Any]:
        initial_state = await self._prepare_upload_state(db=db, file=file, user_id=user_id)
        original_file_path = initial_state["original_file_path"]

        try:
            final_state = await self.graph.ainvoke(initial_state)
        except Exception:
            db.rollback()
            self._delete_saved_file(original_file_path)
            raise

        if final_state["response"].get("needs_reupload"):
            self._delete_saved_file(original_file_path)

        return final_state["response"]

    async def _prepare_upload_state(self, *, db: Session, file: UploadFile, user_id: int) -> ReceiptOcrGraphState:
        self._enforce_upload_rate_limit(user_id)
        image_bytes = await file.read()
        storage_extension = self._validate_upload(file, image_bytes)

        original_file_path = self._save_original_image(
            user_id=user_id,
            image_bytes=image_bytes,
            storage_extension=storage_extension,
        )

        image_id = Path(file.filename or original_file_path).stem
        return {
            "db": db,
            "user_id": user_id,
            "image_bytes": image_bytes,
            "image_id": image_id,
            "original_file_name": file.filename,
            "original_file_path": original_file_path,
            "retry_count": 0,
            "max_retries": OCR_MAX_RETRIES,
            "stage": "image_uploaded",
        }

    async def create_upload_event_stream(self, *, db: Session, file: UploadFile, user_id: int):
        initial_state = await self._prepare_upload_state(db=db, file=file, user_id=user_id)
        original_file_path = initial_state["original_file_path"]

        async def event_stream():
            try:
                yield {
                    "type": "stage",
                    "stage": "image_uploaded",
                    "retry_count": initial_state.get("retry_count", 0),
                    "max_retries": initial_state.get("max_retries", OCR_MAX_RETRIES),
                }

                async for update in self.graph.astream(initial_state, stream_mode="updates"):
                    for node_update in update.values():
                        if not isinstance(node_update, dict):
                            continue

                        stage = node_update.get("stage")
                        if stage:
                            yield {
                                "type": "stage",
                                "stage": stage,
                                "retry_count": node_update.get("retry_count"),
                                "quality_score": node_update.get("quality_score"),
                                "quality_issues": node_update.get("quality_issues", []),
                                "receipt_validation_issues": node_update.get("receipt_validation_issues", []),
                            }

                        response = node_update.get("response")
                        if response:
                            if response.get("needs_reupload"):
                                self._delete_saved_file(original_file_path)
                            yield {"type": "result", "data": response}
            except Exception as exc:
                db.rollback()
                self._delete_saved_file(original_file_path)
                yield {"type": "error", "message": self._format_error_message(exc)}

        return event_stream()

    def _format_error_message(self, exc: Exception) -> str:
        if isinstance(exc, HTTPException):
            return str(exc.detail)
        return str(exc) or "Receipt OCR analysis failed."

    def _build_graph(self):
        workflow = StateGraph(ReceiptOcrGraphState)
        workflow.add_node("extract_ocr", self._extract_ocr_node)
        workflow.add_node("normalize_result", self._normalize_result_node)
        workflow.add_node("validate_receipt_document", self._validate_receipt_document_node)
        workflow.add_node("validate_quality", self._validate_quality_node)
        workflow.add_node("retry_ocr", self._retry_ocr_node)
        workflow.add_node("persist_receipt", self._persist_receipt_node)
        workflow.add_node("build_reupload_response", self._build_reupload_response_node)
        workflow.add_node("build_response", self._build_response_node)

        workflow.set_entry_point("extract_ocr")
        workflow.add_edge("extract_ocr", "normalize_result")
        workflow.add_edge("normalize_result", "validate_receipt_document")
        workflow.add_conditional_edges(
            "validate_receipt_document",
            self._route_after_document_validation,
            {"quality": "validate_quality", "reupload": "build_reupload_response"},
        )
        workflow.add_conditional_edges(
            "validate_quality",
            self._route_after_validation,
            {"retry": "retry_ocr", "persist": "persist_receipt", "reupload": "build_reupload_response"},
        )
        workflow.add_edge("retry_ocr", "extract_ocr")
        workflow.add_edge("persist_receipt", "build_response")
        workflow.add_edge("build_reupload_response", END)
        workflow.add_edge("build_response", END)
        return workflow.compile()

    async def _extract_ocr_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        retry_note = self._build_retry_note(state.get("quality_issues", []))
        ocr_result = await run_in_threadpool(
            self._call_openai_vision,
            image_bytes=state["image_bytes"],
            filename=state.get("original_file_name") or "receipt.jpg",
            image_id=state["image_id"],
            retry_note=retry_note,
        )
        return {"ocr_result": ocr_result, "stage": "ocr_extracted"}

    def _normalize_result_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        normalized = self._normalize_ocr_result(state["ocr_result"], image_id=state["image_id"], db=state["db"])
        return {"normalized": normalized, "stage": "result_normalized"}

    def _validate_quality_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        quality_score, quality_issues = self._score_ocr_quality(state["normalized"])
        return {
            "quality_score": quality_score,
            "quality_issues": quality_issues,
            "stage": "quality_validated",
        }

    def _validate_receipt_document_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        receipt_validation_issues = self._validate_receipt_document(state["normalized"])
        updates: Dict[str, Any] = {
            "receipt_validation_issues": receipt_validation_issues,
            "stage": "receipt_document_validated",
        }
        if receipt_validation_issues:
            updates["quality_score"] = 0.0
            updates["quality_issues"] = receipt_validation_issues
        return updates

    def _route_after_document_validation(self, state: ReceiptOcrGraphState) -> str:
        if state.get("receipt_validation_issues"):
            return "reupload"
        return "quality"

    def _route_after_validation(self, state: ReceiptOcrGraphState) -> str:
        if state.get("quality_score", 0.0) < OCR_MIN_QUALITY_SCORE and state.get("retry_count", 0) < state.get(
            "max_retries", OCR_MAX_RETRIES
        ):
            return "retry"
        if state.get("quality_score", 0.0) < OCR_MIN_QUALITY_SCORE:
            return "reupload"
        return "persist"

    def _retry_ocr_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        return {"retry_count": state.get("retry_count", 0) + 1, "stage": "ocr_retry_requested"}

    async def _persist_receipt_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        normalized = state["normalized"]
        quality_score = state.get("quality_score")
        quality_issues = state.get("quality_issues", [])
        receipt = Receipt(
            user_id=state["user_id"],
            original_file_name=state.get("original_file_name"),
            original_file_path=state["original_file_path"],
            store_name=normalized.get("store_name"),
            purchased_at=self._parse_purchase_datetime(normalized.get("purchase_datetime")),
            total_price=normalized.get("total_amount"),
            ocr_quality_score=quality_score,
            ocr_status=self._build_ocr_status(quality_score=quality_score, quality_issues=quality_issues),
            ocr_error_message=", ".join(quality_issues) if quality_issues else None,
        )
        db = state["db"]
        db.add(receipt)
        db.commit()
        db.refresh(receipt)
        return {"receipt_id": receipt.id, "stage": "receipt_persisted"}

    def _build_response_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        normalized = state["normalized"]
        response = {
            "receipt_id": state["receipt_id"],
            "original_file_name": state.get("original_file_name"),
            "original_file_path": state["original_file_path"],
            "store_name": normalized.get("store_name"),
            "purchase_datetime": normalized.get("purchase_datetime"),
            "items": normalized.get("items", []),
            "total_item_count": normalized.get("total_item_count"),
            "total_amount": normalized.get("total_amount"),
            "currency": normalized.get("currency", "KRW"),
            "confidence_note": normalized.get("confidence_note"),
            "document_type": normalized.get("document_type"),
            "is_receipt_like": normalized.get("is_receipt_like"),
            "quality_score": state.get("quality_score"),
            "quality_issues": state.get("quality_issues", []),
            "ocr_status": self._build_ocr_status(
                quality_score=state.get("quality_score"),
                quality_issues=state.get("quality_issues", []),
            ),
            "ocr_error_message": ", ".join(state.get("quality_issues", [])) if state.get("quality_issues") else None,
            "receipt_validation_issues": state.get("receipt_validation_issues", []),
            "needs_reupload": False,
        }
        return {"response": response, "stage": "response_ready"}

    def _build_reupload_response_node(self, state: ReceiptOcrGraphState) -> Dict[str, Any]:
        normalized = state.get("normalized") or {}
        receipt_validation_issues = state.get("receipt_validation_issues", [])
        reupload_message = (
            "\uc601\uc218\uc99d \uc774\ubbf8\uc9c0\uac00 \uc544\ub2cc \uac83 \uac19\uc544\uc694. "
            "\ub9e4\uc7a5\uba85, \uad6c\ub9e4\uc77c\uc790, \ud488\ubaa9, \uacb0\uc81c \ub0b4\uc5ed \uc911 \ud558\ub098 \uc774\uc0c1\uc774 "
            "\ubcf4\uc774\ub294 \uc601\uc218\uc99d\uc744 \ub2e4\uc2dc \ucca8\ubd80\ud574\uc8fc\uc138\uc694."
            if receipt_validation_issues
            else "\uc601\uc218\uc99d \uc774\ubbf8\uc9c0 \uc778\uc2dd \ud488\uc9c8\uc774 \ub0ae\uc544\uc694. "
            "\uae00\uc790\uc640 \uae08\uc561\uc774 \uc120\uba85\ud558\uac8c \ubcf4\uc774\ub3c4\ub85d \ub2e4\uc2dc \ucd2c\uc601\ud558\uac70\ub098 "
            "\ub2e4\ub978 \uc774\ubbf8\uc9c0\ub97c \ucca8\ubd80\ud574\uc8fc\uc138\uc694."
        )
        response = {
            "receipt_id": None,
            "original_file_name": state.get("original_file_name"),
            "original_file_path": None,
            "store_name": None,
            "purchase_datetime": None,
            "items": [],
            "total_item_count": None,
            "total_amount": None,
            "currency": "KRW",
            "confidence_note": "OCR quality stayed below the operational threshold after retry.",
            "quality_score": state.get("quality_score"),
            "quality_issues": state.get("quality_issues", []),
            "ocr_status": "reupload_required",
            "ocr_error_message": ", ".join(state.get("quality_issues", [])) if state.get("quality_issues") else None,
            "needs_reupload": True,
            "reupload_message": "영수증 이미지 인식 품질이 낮아요. 글자와 금액이 선명하게 보이도록 다시 촬영하거나 다른 이미지를 첨부해주세요.",
        }
        response.update(
            {
                "confidence_note": (
                    "Uploaded image did not contain enough receipt evidence."
                    if receipt_validation_issues
                    else "OCR quality stayed below the operational threshold after retry."
                ),
                "document_type": normalized.get("document_type"),
                "is_receipt_like": normalized.get("is_receipt_like"),
                "receipt_validation_issues": receipt_validation_issues,
                "reupload_message": reupload_message,
            }
        )
        return {"response": response, "stage": "reupload_required"}

    def _validate_upload(self, file: UploadFile, image_bytes: bytes) -> str:
        if not image_bytes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")

        max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
        if len(image_bytes) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size must be {settings.MAX_UPLOAD_SIZE_MB}MB or less.",
            )

        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported image format. Upload jpg, jpeg, png, or webp.",
            )

        expected_mime_type = ALLOWED_MIME_TYPES_BY_EXTENSION[suffix]
        content_type = (file.content_type or "").split(";")[0].strip().lower()
        if content_type != expected_mime_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Uploaded file content type must be {expected_mime_type}.",
            )

        detected_type = self._detect_image_type(image_bytes)
        if detected_type != suffix.lstrip(".").replace("jpg", "jpeg"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file content does not match the file extension.",
            )

        if not self._can_parse_image(image_bytes, detected_type):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded image could not be parsed.",
            )
        return CANONICAL_EXTENSION_BY_IMAGE_TYPE[detected_type]

    def _enforce_upload_rate_limit(self, user_id: int) -> None:
        now = datetime.now(timezone.utc)
        minute_window_start = now - timedelta(minutes=1)
        day_window_start = now - timedelta(days=1)

        with self._upload_rate_limit_lock:
            attempts = [attempt for attempt in self._upload_attempts_by_user[user_id] if attempt >= day_window_start]

            if len([attempt for attempt in attempts if attempt >= minute_window_start]) >= settings.RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE:
                self._upload_attempts_by_user[user_id] = attempts
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Receipt upload is limited to {settings.RECEIPT_UPLOAD_RATE_LIMIT_PER_MINUTE} requests per minute.",
                )

            if len(attempts) >= settings.RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY:
                self._upload_attempts_by_user[user_id] = attempts
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Receipt upload is limited to {settings.RECEIPT_UPLOAD_RATE_LIMIT_PER_DAY} requests per day.",
                )

            attempts.append(now)
            self._upload_attempts_by_user[user_id] = attempts

    def _detect_image_type(self, image_bytes: bytes) -> Optional[str]:
        if image_bytes.startswith(b"\xff\xd8\xff"):
            return "jpeg"
        if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "png"
        if len(image_bytes) >= 12 and image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
            return "webp"
        return None

    def _can_parse_image(self, image_bytes: bytes, image_type: str) -> bool:
        parsers = {
            "jpeg": self._parse_jpeg_dimensions,
            "png": self._parse_png_dimensions,
            "webp": self._parse_webp_dimensions,
        }
        parser = parsers.get(image_type)
        if not parser:
            return False
        try:
            width, height = parser(image_bytes)
        except (IndexError, TypeError, ValueError):
            return False
        return width > 0 and height > 0

    def _parse_png_dimensions(self, image_bytes: bytes) -> tuple[int, int]:
        if len(image_bytes) < 24 or image_bytes[:8] != b"\x89PNG\r\n\x1a\n" or image_bytes[12:16] != b"IHDR":
            raise ValueError("Invalid PNG header.")
        return int.from_bytes(image_bytes[16:20], "big"), int.from_bytes(image_bytes[20:24], "big")

    def _parse_jpeg_dimensions(self, image_bytes: bytes) -> tuple[int, int]:
        if len(image_bytes) < 4 or not image_bytes.startswith(b"\xff\xd8"):
            raise ValueError("Invalid JPEG header.")

        index = 2
        while index < len(image_bytes):
            while index < len(image_bytes) and image_bytes[index] != 0xFF:
                index += 1
            while index < len(image_bytes) and image_bytes[index] == 0xFF:
                index += 1
            if index >= len(image_bytes):
                break

            marker = image_bytes[index]
            index += 1
            if marker in {0xD8, 0xD9}:
                continue
            if index + 2 > len(image_bytes):
                break

            segment_length = int.from_bytes(image_bytes[index : index + 2], "big")
            if segment_length < 2 or index + segment_length > len(image_bytes):
                raise ValueError("Invalid JPEG segment.")

            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                if segment_length < 7:
                    raise ValueError("Invalid JPEG frame.")
                height = int.from_bytes(image_bytes[index + 3 : index + 5], "big")
                width = int.from_bytes(image_bytes[index + 5 : index + 7], "big")
                return width, height

            index += segment_length

        raise ValueError("JPEG dimensions were not found.")

    def _parse_webp_dimensions(self, image_bytes: bytes) -> tuple[int, int]:
        if len(image_bytes) < 30 or image_bytes[:4] != b"RIFF" or image_bytes[8:12] != b"WEBP":
            raise ValueError("Invalid WebP header.")

        chunk_type = image_bytes[12:16]
        if chunk_type == b"VP8X":
            if len(image_bytes) < 30:
                raise ValueError("Invalid VP8X header.")
            width = int.from_bytes(image_bytes[24:27], "little") + 1
            height = int.from_bytes(image_bytes[27:30], "little") + 1
            return width, height

        if chunk_type == b"VP8L":
            if len(image_bytes) < 25 or image_bytes[20] != 0x2F:
                raise ValueError("Invalid VP8L header.")
            bits = int.from_bytes(image_bytes[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return width, height

        if chunk_type == b"VP8 ":
            if len(image_bytes) < 30 or image_bytes[23:26] != b"\x9d\x01\x2a":
                raise ValueError("Invalid VP8 header.")
            width = int.from_bytes(image_bytes[26:28], "little") & 0x3FFF
            height = int.from_bytes(image_bytes[28:30], "little") & 0x3FFF
            return width, height

        raise ValueError("Unsupported WebP chunk.")

    def _save_original_image(self, *, user_id: int, image_bytes: bytes, storage_extension: str) -> str:
        today = datetime.now(KST).strftime("%Y%m%d")
        stored_name = f"{today}_{uuid4().hex}{storage_extension}"

        upload_root = self._resolve_storage_root(settings.OCR_UPLOAD_DIR)
        user_dir = upload_root / str(user_id)
        user_dir.mkdir(parents=True, exist_ok=True)

        stored_path = user_dir / stored_name
        stored_path.write_bytes(image_bytes)
        return self._to_project_relative_path(stored_path)

    def _call_openai_vision(
        self,
        *,
        image_bytes: bytes,
        filename: str,
        image_id: str,
        retry_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        if settings.OCR_ENGINE != "openai_vision":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported OCR_ENGINE.")
        if not self.client:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="OPENAI_API_KEY is not set.")

        mime_type = self._guess_mime_type(filename)
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        prompt = self._build_prompt(image_id, retry_note=retry_note)

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
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"OCR model call failed: {exc}") from exc

        content = response.choices[0].message.content if response.choices else None
        if not content:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="OCR model response is empty.")

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
            standard_name = ingredient_name_matcher.find_best_name(raw_name)
            items.append(
                {
                    "raw_name": raw_name,
                    "normalized_name": standard_name or raw_name,
                    "quantity": self._nullable_number(item.get("quantity")),
                    "unit": unit if unit in ALLOWED_UNITS else DEFAULT_UNIT,
                    "item_amount": self._nullable_int(item.get("item_amount")),
                }
            )

        return {
            "image_id": self._nullable_str(result.get("image_id")) or image_id,
            "document_type": self._normalize_document_type(result.get("document_type")),
            "is_receipt_like": self._nullable_bool(result.get("is_receipt_like")),
            "store_name": self._nullable_str(result.get("store_name")),
            "purchase_datetime": self._nullable_str(result.get("purchase_datetime")),
            "items": items,
            "total_item_count": self._nullable_number(result.get("total_item_count")),
            "total_amount": self._nullable_int(result.get("total_amount")),
            "currency": "KRW",
            "confidence_note": self._nullable_str(result.get("confidence_note")),
        }

    def _validate_receipt_document(self, normalized: Dict[str, Any]) -> List[str]:
        issues: List[str] = []
        document_type = normalized.get("document_type") or "unknown"
        is_receipt_like = normalized.get("is_receipt_like")

        if document_type == "non_receipt" or is_receipt_like is False:
            issues.append("non_receipt_document")

        if not self._has_receipt_evidence(normalized):
            issues.append("receipt_evidence_missing")

        return issues

    def _has_receipt_evidence(self, normalized: Dict[str, Any]) -> bool:
        if normalized.get("items"):
            return True
        if normalized.get("store_name") or normalized.get("purchase_datetime"):
            return True

        total_amount = normalized.get("total_amount")
        if total_amount:
            return True

        confidence_note = (normalized.get("confidence_note") or "").lower()
        if any(
            keyword in confidence_note
            for keyword in (
                "not a receipt",
                "not a purchase receipt",
                "non_receipt",
                "non-receipt",
                "\uc601\uc218\uc99d\uc774 \uc544\ub2d8",
                "\uc601\uc218\uc99d\uc774 \uc544\ub2cc",
            )
        ):
            return False
        return any(
            keyword in confidence_note
            for keyword in (
                "receipt",
                "card approval",
                "card slip",
                "e-receipt",
                "payment",
                "\uc601\uc218\uc99d",
                "\uacb0\uc81c",
                "\uc2b9\uc778",
                "\uce74\ub4dc",
            )
        )

    def _score_ocr_quality(self, normalized: Dict[str, Any]) -> tuple[float, List[str]]:
        score = 1.0
        issues: List[str] = []
        items = normalized.get("items") or []
        total_amount = normalized.get("total_amount")

        if not normalized.get("store_name"):
            score -= 0.05
            issues.append("store_name_missing")
        if not normalized.get("purchase_datetime"):
            score -= 0.05
            issues.append("purchase_datetime_missing")

        confidence_note = (normalized.get("confidence_note") or "").lower()
        if any(keyword in confidence_note for keyword in ("unreadable", "hard-to-read", "illegible", "uncertain")):
            score -= 0.2
            issues.append("text_uncertain")

        item_amounts = [item.get("item_amount") for item in items if item.get("item_amount") is not None]
        if items and len(item_amounts) / len(items) < 0.5:
            score -= 0.2
            issues.append("many_item_amounts_missing")

        if items:
            unclear_item_count = sum(1 for item in items if self._is_unclear_item_name(item.get("raw_name")))
            if unclear_item_count:
                ratio = unclear_item_count / len(items)
                score -= 0.3 if ratio >= 0.5 else 0.15
                issues.append("item_names_unclear")
        elif not normalized.get("total_amount") and not confidence_note:
            score -= 0.15
            issues.append("insufficient_receipt_evidence")

        if total_amount and item_amounts:
            item_sum = sum(int(amount) for amount in item_amounts)
            tolerance = max(1000, int(total_amount * 0.15))
            if abs(int(total_amount) - item_sum) > tolerance:
                score -= 0.05
                issues.append("total_amount_mismatch")

        total_item_count = normalized.get("total_item_count")
        if total_item_count is not None and items:
            try:
                if abs(float(total_item_count) - len(items)) > max(2, len(items) * 0.5):
                    score -= 0.1
                    issues.append("total_item_count_mismatch")
            except (TypeError, ValueError):
                pass

        return max(0.0, round(score, 2)), issues

    def _build_ocr_status(self, *, quality_score: Optional[float], quality_issues: List[str]) -> str:
        if quality_score is None:
            return "unknown"
        if quality_score < OCR_MIN_QUALITY_SCORE:
            return "reupload_required"
        if quality_issues:
            return "needs_review"
        return "completed"

    def _is_unclear_item_name(self, value: Any) -> bool:
        text = self._nullable_str(value)
        if not text:
            return True
        if "�" in text or "?" in text:
            return True
        letters = re.findall(r"[0-9A-Za-z\uac00-\ud7a3]", text)
        if len(text) >= 4 and len(letters) / len(text) < 0.5:
            return True
        return len(text) <= 1

    def _build_retry_note(self, quality_issues: List[str]) -> Optional[str]:
        if not quality_issues:
            return None
        return ", ".join(quality_issues)

    def _build_prompt(self, image_id: str, *, retry_note: Optional[str] = None) -> str:
        prompt = f"""
You are an OCR and structured data extraction assistant for Korean receipts.

Extract only the following information from the receipt image:
- document_type
- is_receipt_like
- store_name
- purchase_datetime
- purchased item names
- quantity per item
- unit per item: use only "\uac1c" or "kg"
- item_amount per item
- total_item_count
- total_amount

Return only one valid JSON object. Do not include Markdown, code fences, comments, or explanations.

Output schema:
{{
  "image_id": "{image_id}",
  "document_type": "receipt|card_slip|e_receipt|non_receipt|unknown",
  "is_receipt_like": true,
  "store_name": "string|null",
  "purchase_datetime": "YYYY-MM-DD HH:mm:ss|null",
  "items": [
    {{
      "raw_name": "string",
      "quantity": "number|null",
      "unit": "\uac1c|kg|null",
      "item_amount": "number|null"
    }}
  ],
  "total_item_count": "number|null",
  "total_amount": "number|null",
  "currency": "KRW",
  "confidence_note": "string|null"
}}

Rules:
1. Use "{image_id}" as image_id exactly.
2. Classify document_type first. Use non_receipt for tables, reports, presentations, menus without purchase/payment evidence, product lists, screenshots, or unrelated documents.
3. Set is_receipt_like to true only when the image contains at least one receipt clue such as store name, purchase date/time, purchased item rows, total/payment amount, card approval/payment text, receipt number, or approval number.
4. If document_type is non_receipt, return is_receipt_like false, items empty, all receipt fields null, and explain the reason in confidence_note.
5. Put only real purchased products or menu items in items.
6. Exclude subtotals, taxes, payment methods, card numbers, approval numbers, and notices from items.
7. Exclude discount lines and zero-price option lines from items.
8. If the receipt is a card approval screen or e-receipt without visible item rows, return an empty items array.
9. Return quantity as a number. Use null if unknown.
10. Use only "\uac1c", "kg", or null for unit. Use "\uac1c" for normal packaged/menu items.
11. Keep volume text such as ml or L inside raw_name, not unit.
12. item_amount is the line amount for that item, not the unit price unless only unit price is visible.
13. total_amount is a reference value. Use null if uncertain.
14. Write uncertainty about hard-to-read text, inferred values, omitted lines, or non-receipt classification in confidence_note.
""".strip()
        if retry_note:
            prompt += "\n\n" + f"""Retry guidance:
The previous extraction was rejected by validation because of: {retry_note}.
Re-read the receipt image carefully and fix only the problematic fields. If the receipt truly has no visible item rows, keep items empty and explain that in confidence_note.
""".strip()
        return prompt

    def _parse_json_object(self, content: str) -> Dict[str, Any]:
        text = content.strip()
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        candidate = fenced.group(1).strip() if fenced else text
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end < start:
            raise ValueError("OCR model response did not contain a JSON object.")
        try:
            parsed = json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"OCR model response JSON parsing failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("OCR model response must be a JSON object.")
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
        safe = re.sub(r"[^0-9A-Za-z\uac00-\ud7a3_-]+", "_", value).strip("._")
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

    def _nullable_bool(self, value: Any) -> Optional[bool]:
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        text = str(value).strip().lower()
        if text in {"true", "1", "yes"}:
            return True
        if text in {"false", "0", "no"}:
            return False
        return None

    def _normalize_document_type(self, value: Any) -> str:
        text = (self._nullable_str(value) or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        if text in {"receipt", "card_slip", "e_receipt", "non_receipt"}:
            return text
        return "unknown"

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
