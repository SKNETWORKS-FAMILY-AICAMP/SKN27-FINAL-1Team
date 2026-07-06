"""OpenAI Chat Completions client (singleton)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)


class Singleton(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


class OpenAIClient(metaclass=Singleton):
    """OpenAI client를 1회 생성하고 JSON chat completion을 제공한다."""

    def __init__(self, *, api_key: str | None = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key or OpenAI is None:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았거나 openai 패키지가 없습니다.")
        self.client = OpenAI(api_key=key)
        logger.info("OpenAI client 준비 완료")

    def chat_json(self, *, model: str, system: str, user: str) -> str | None:
        """JSON object 응답 content를 반환한다. 실패 시 None."""
        try:
            response = self.client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            )
        except Exception as exc:
            logger.warning("OpenAI 호출 실패: %s", exc)
            return None

        content = response.choices[0].message.content if response.choices else None
        if not content:
            logger.warning("OpenAI 응답이 비어 있음")
        return content


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    a = OpenAIClient()
    b = OpenAIClient()
    assert a is b

    key = os.getenv("OPENAI_API_KEY", "")
    if not key or OpenAI is None:
        logger.info("OPENAI_API_KEY 없음 — 싱글톤 smoke만 통과")
    else:
        content = a.chat_json(
            model="gpt-5-mini",
            system='JSON만 반환: {"ok": true}',
            user="ping",
        )
        assert content is not None
        logger.info("샘플 응답: %s", content[:200])
