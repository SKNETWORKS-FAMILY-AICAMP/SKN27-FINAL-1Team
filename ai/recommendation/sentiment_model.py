"""한국어 고객 리뷰 BERT 감성 분류기 (싱글톤)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import torch
from torch.nn import functional as F
from transformers import AutoModelForSequenceClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[2]
if __package__ is None:
    sys.path.insert(0, str(ROOT))

logger = logging.getLogger(__name__)

#####################################################################################
# 설정
#####################################################################################

MODEL_NAME = "WhitePeak/bert-base-cased-Korean-sentiment"
MAX_SEQUENCE_LENGTH = 512
SCORE_DECIMAL_PLACES = 4

SENTIMENT_POSITIVE = "positive"
SENTIMENT_NEGATIVE = "negative"


def _normalize_label(label: str) -> str:
    text = label.lower().replace("label_", "")
    if "pos" in text:
        return SENTIMENT_POSITIVE
    if "neg" in text:
        return SENTIMENT_NEGATIVE
    return text


def _scores_from_probs(probs: torch.Tensor, id2label: dict) -> tuple[float, float]:
    """config.id2label 기준으로 positive/negative softmax 점수를 반환한다."""
    positive_score = 0.0
    negative_score = 0.0
    for idx, prob in enumerate(probs):
        raw = id2label.get(idx, id2label.get(str(idx), ""))
        label = _normalize_label(str(raw))
        if label == SENTIMENT_POSITIVE:
            positive_score = prob.item()
        elif label == SENTIMENT_NEGATIVE:
            negative_score = prob.item()
    if positive_score == 0.0 and negative_score == 0.0 and len(probs) == 2:
        # ponytail: id2label 미정의 모델 fallback — 0=negative, 1=positive
        negative_score = probs[0].item()
        positive_score = probs[1].item()
    return positive_score, negative_score

#####################################################################################
# 싱글톤 패턴
#####################################################################################


class Singleton(type):
    _instances: dict[type, object] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]


#####################################################################################
# BERT 감성 분류기
#####################################################################################


class SentimentClassifier(metaclass=Singleton):
    """토크나이저·분류 모델을 1회 로드하고 문장 단위 감성 추론을 수행한다."""

    def __init__(self, model_name: str | None = None) -> None:
        name = model_name or MODEL_NAME
        self.model_name = name
        self.tokenizer = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForSequenceClassification.from_pretrained(name)
        logger.info("감성 모델 로드 완료: %s", name)

    def predict_sentiment(self, text: str) -> dict[str, str | float]:
        """문장에 대한 긍·부정 softmax 확률과 대표 라벨 dict를 반환한다."""
        inputs = self.tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            padding=True,
            max_length=MAX_SEQUENCE_LENGTH,
        )

        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = F.softmax(outputs.logits, dim=-1)[0]

        positive_score, negative_score = _scores_from_probs(
            probs, self.model.config.id2label
        )
        dec = SCORE_DECIMAL_PLACES
        label = (
            SENTIMENT_POSITIVE
            if positive_score >= negative_score
            else SENTIMENT_NEGATIVE
        )

        return {
            "sentimental": label,
            "score": round(max(positive_score, negative_score), dec),
            "positive_score": round(positive_score, dec),
            "negative_score": round(negative_score, dec),
        }

    def close(self) -> None:
        """모델 참조를 해제한다."""
        self.model = None
        self.tokenizer = None
        logger.info("감성 모델 리소스 해제 완료")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logger.info("=== SentimentClassifier 싱글톤 smoke ===")

    a = SentimentClassifier()
    b = SentimentClassifier()
    logger.info("같은 인스턴스? %s", a is b)

    sample = a.predict_sentiment("맛있어요 정말 최고입니다")
    logger.info("샘플 결과: %s", sample)
    assert sample["sentimental"] == SENTIMENT_POSITIVE

    tv_review = a.predict_sentiment(
        "티비에서 보고 만들어 먹어봐야지 했는데 해먹어보니 맛있어서 식구들이 좋아했어요."
    )
    logger.info("레시피 후기 샘플: %s", tv_review)
    assert tv_review["sentimental"] == SENTIMENT_POSITIVE
