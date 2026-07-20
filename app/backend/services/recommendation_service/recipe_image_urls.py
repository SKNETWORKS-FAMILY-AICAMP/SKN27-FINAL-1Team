from __future__ import annotations

from urllib.parse import quote

FIREBASE_STORAGE_PUBLIC_BASE_URL = (
    "https://firebasestorage.googleapis.com/v0/b/"
    "bobbeori.firebasestorage.app/o"
)
MAIN_IMAGE_PATH = "recipe-images/v2"
STEP_IMAGE_PATH = "recipe-step-images/v1"


def recipe_code(recipe_id: int) -> str:
    """숫자형 RDB ID를 Firebase 객체명에 사용하는 R0001 형식으로 변환한다."""
    normalized_id = int(recipe_id)
    if normalized_id <= 0:
        raise ValueError("recipe_id는 1 이상이어야 합니다.")
    return f"R{normalized_id:04d}"


def _public_storage_url(object_path: str) -> str:
    encoded_path = quote(object_path, safe="")
    return f"{FIREBASE_STORAGE_PUBLIC_BASE_URL}/{encoded_path}?alt=media"


def build_main_image_url(recipe_id: int) -> str:
    object_path = f"{MAIN_IMAGE_PATH}/{recipe_code(recipe_id)}.webp"
    return _public_storage_url(object_path)


def build_step_image_url(recipe_id: int, step_number: int) -> str:
    normalized_step = int(step_number)
    if normalized_step <= 0:
        raise ValueError("step_number는 1 이상이어야 합니다.")
    object_path = (
        f"{STEP_IMAGE_PATH}/"
        f"{recipe_code(recipe_id)}/{normalized_step:02d}.webp"
    )
    return _public_storage_url(object_path)
