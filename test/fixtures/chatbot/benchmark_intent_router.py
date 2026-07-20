from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from ai.agents.supervisor_agent.supervisor_service import supervisor_service
from ai.agents.supervisor_agent.supervisor_agent import router_node
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


def _route_case(case: dict[str, Any], mode: str) -> dict[str, Any]:
    """선택한 라우팅 방식으로 평가 문장 하나를 분류합니다."""
    text = case["text"]
    history = case.get("history") or []
    if mode == "llm":
        return supervisor_service._route_intent_payload_with_llm(text, history)
    if mode == "rule":
        return router_node({"text": text, "history": history})
    if mode == "hybrid":
        return router_node({"text": text, "history": history, "service": supervisor_service})
    raise ValueError(f"지원하지 않는 라우팅 방식입니다: {mode}")


def _evaluate_case(case: dict[str, Any], mode: str = "llm") -> dict[str, Any]:
    """평가 문장 하나의 예측 intent와 처리 시간을 측정합니다."""
    started_at = time.perf_counter()
    result = _route_case(case, mode)
    intent_payload = result.get("intent_payload") or {}
    return {
        "text": case["text"],
        "expected": case["expected_intent"],
        "predicted": result.get("intent", "general"),
        "confidence": result.get("confidence", intent_payload.get("confidence", 0.0)),
        "latency": time.perf_counter() - started_at,
    }


def evaluate_cases(cases: list[dict[str, Any]], workers: int = 5, mode: str = "llm") -> dict[str, Any]:
    """선택한 라우팅 방식의 정확도와 intent별 실패 사례를 계산합니다."""
    wall_started_at = time.perf_counter()
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        evaluated = list(executor.map(lambda case: _evaluate_case(case, mode), cases))

    correct = 0
    intent_stats = defaultdict(lambda: {"total": 0, "correct": 0})
    failures = []

    for result in evaluated:
        expected = result["expected"]
        intent_stats[expected]["total"] += 1
        if result["predicted"] == expected:
            correct += 1
            intent_stats[expected]["correct"] += 1
        else:
            failures.append({
                "text": result["text"],
                "expected": expected,
                "predicted": result["predicted"],
                "confidence": result["confidence"],
            })

    total = len(cases)
    return {
        "mode": mode,
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4),
        "average_latency_seconds": round(sum(item["latency"] for item in evaluated) / total, 4),
        "wall_time_seconds": round(time.perf_counter() - wall_started_at, 4),
        "per_intent": dict(sorted(intent_stats.items())),
        "failures": failures,
    }


def evaluate_benchmark(cases: list[dict[str, Any]], workers: int = 5) -> dict[str, Any]:
    """동일한 데이터셋으로 Rule, LLM, Hybrid 라우팅을 차례로 비교합니다."""
    return {
        "dataset_size": len(cases),
        "results": {
            mode: evaluate_cases(cases, workers=workers, mode=mode)
            for mode in ("rule", "llm", "hybrid")
        },
    }


def main() -> int:
    """명령행 인자를 받아 intent 평가를 실행하고 기준 미달 여부를 반환합니다."""
    parser = argparse.ArgumentParser(description="Supervisor intent 라우팅 방식을 비교 평가합니다.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--min-accuracy", type=float, default=0.8)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--mode", choices=("all", "rule", "llm", "hybrid"), default="all")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.mode in {"all", "llm", "hybrid"} and not settings.OPENAI_API_KEY:
        print("OPENAI_API_KEY가 없어 실모델 평가를 실행할 수 없습니다.", file=sys.stderr)
        return 2

    cases = load_cases(args.dataset)
    report = (
        evaluate_benchmark(cases, workers=args.workers)
        if args.mode == "all"
        else evaluate_cases(cases, workers=args.workers, mode=args.mode)
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")

    target = report["results"]["hybrid"] if args.mode == "all" else report
    return 0 if target["accuracy"] >= args.min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
