from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from ai.agents.supervisor_agent.supervisor_service import supervisor_service
from app.backend.core.config import settings


DEFAULT_DATASET = Path(__file__).with_name("intent_evaluation_cases.json")


def load_cases(path: Path) -> list[dict[str, Any]]:
    """JSON 파일에서 intent 평가 문장을 읽고 최소 형식을 검증합니다."""
    cases = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(cases, list) or not cases:
        raise ValueError("평가 데이터셋은 비어 있지 않은 JSON 배열이어야 합니다.")
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict) or not case.get("text") or not case.get("expected_intent"):
            raise ValueError(f"{index}번째 평가 문장 형식이 올바르지 않습니다.")
    return cases


def evaluate_cases(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """실제 Supervisor LLM 분류기로 정확도와 intent별 실패 사례를 계산합니다."""
    correct = 0
    total_latency = 0.0
    failures = []
    intent_stats = defaultdict(lambda: {"total": 0, "correct": 0})

    for case in cases:
        started_at = time.perf_counter()
        result = supervisor_service._route_intent_payload_with_llm(
            case["text"],
            case.get("history") or [],
        )
        total_latency += time.perf_counter() - started_at

        expected = case["expected_intent"]
        predicted = result.get("intent", "general")
        intent_stats[expected]["total"] += 1
        if predicted == expected:
            correct += 1
            intent_stats[expected]["correct"] += 1
            continue

        failures.append({
            "text": case["text"],
            "expected": expected,
            "predicted": predicted,
            "confidence": result.get("confidence", 0.0),
        })

    total = len(cases)
    return {
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4),
        "average_latency_seconds": round(total_latency / total, 4),
        "per_intent": dict(sorted(intent_stats.items())),
        "failures": failures,
    }


def main() -> int:
    """명령행 인자를 받아 intent 평가를 실행하고 기준 미달 여부를 반환합니다."""
    parser = argparse.ArgumentParser(description="Supervisor LLM intent 분류 정확도를 평가합니다.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY가 없어 실모델 평가를 실행할 수 없습니다.", file=sys.stderr)
        return 2

    report = evaluate_cases(load_cases(args.dataset))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    return 0 if report["accuracy"] >= args.min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
