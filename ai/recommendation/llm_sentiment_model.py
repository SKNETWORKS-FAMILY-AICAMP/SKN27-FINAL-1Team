"""OpenAI gpt-5-mini 기반 레시피 리뷰/댓글 감성 분석기."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore[misc, assignment]

logger = logging.getLogger(__name__)

MODEL_NAME = "gpt-5-mini"
SCORE_DECIMAL_PLACES = 4

SYSTEM_PROMPT = (
    "당신은 한국어 레시피 리뷰·댓글 감성 분석기입니다.\n"
    "입력 텍스트의 긍정·부정 확률을 0~1 사이 실수로 추정하세요.\n"
    "두 값의 합은 대략 1이 되도록 하세요.\n"
    '반드시 JSON만 반환: {"positive": float, "negative": float}'
)


def _clamp_score(value: float) -> float:
    return round(max(0.0, min(1.0, value)), SCORE_DECIMAL_PLACES)


def parse_sentiment_response(content: str) -> dict[str, float]:
    """LLM JSON 응답을 positive/negative 점수 dict로 변환한다."""
    data = json.loads(content)
    positive = _clamp_score(float(data["positive"]))
    negative = _clamp_score(float(data["negative"]))
    return {"positive": positive, "negative": negative}


class LLMSentimentAnalyzer:
    """OpenAI Chat Completions로 문장 단위 감성 추론을 수행한다."""

    def __init__(self, *, api_key: str | None = None, model_name: str | None = None) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY", "")
        if not key or OpenAI is None:
            raise ValueError("OPENAI_API_KEY가 설정되지 않았거나 openai 패키지가 없습니다.")
        self.model_name = model_name or MODEL_NAME
        self.client = OpenAI(api_key=key)
        logger.info("LLM 감성 모델 준비 완료: %s", self.model_name)

    def predict_sentiment(self, text: str) -> dict[str, float]:
        """문장에 대한 긍·부정 추정값 dict를 반환한다."""
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": text},
                ],
            )
        except Exception as exc:
            logger.warning("LLM 호출 실패: %s", exc)
            return {"positive": float("nan"), "negative": float("nan")}

        content = response.choices[0].message.content if response.choices else None
        if not content:
            logger.warning("LLM 응답이 비어 있음")
            return {"positive": float("nan"), "negative": float("nan")}

        try:
            return parse_sentiment_response(content)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("LLM 응답 파싱 실패: %s — %s", exc, content[:200])
            return {"positive": float("nan"), "negative": float("nan")}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parsed = parse_sentiment_response('{"positive": 0.92, "negative": 0.08}')
    assert parsed == {"positive": 0.92, "negative": 0.08}

    clamped = parse_sentiment_response('{"positive": 1.5, "negative": -0.1}')
    assert clamped == {"positive": 1.0, "negative": 0.0}

    analyzer = LLMSentimentAnalyzer()
    sample = analyzer.predict_sentiment("맛있어요 정말 최고입니다")
    logger.info("샘플 결과: %s", sample)
    assert 0.0 <= sample["positive"] <= 1.0
    assert 0.0 <= sample["negative"] <= 1.0
