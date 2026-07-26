"""도메인 에이전트 실제 응답을 LLM 심사로 평가합니다."""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path

from openai import OpenAI


DATASET_PATHS = (
    Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl"),
    Path("test/fixtures/agent_evaluation/agent_regression_cases.jsonl"),
)


def _load_jsonl(path: Path) -> list[dict]:
    """BOM 유무와 무관하게 JSONL 파일을 읽습니다."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def _load_cases() -> list[dict]:
    """고난도 평가셋과 실제 실패 회귀셋을 함께 읽습니다."""
    return [case for path in DATASET_PATHS for case in _load_jsonl(path)]


def _is_infrastructure_error(row: dict) -> bool:
    """에이전트 실행 자체가 실패한 결과는 품질 평가에서 제외합니다."""
    status = str((row.get("slots") or {}).get("agent_status") or row.get("status") or "").lower()
    return bool(row.get("error")) or status == "error"


def _judge_response(client: OpenAI, model: str, case: dict, response_text: str) -> dict:
    """응답의 관련성, 유용성, 완결성을 10점 만점으로 심사합니다."""
    prompt = {
        "agent": case["agent"],
        "user_message": case["message"],
        "scenario": case["expected"]["scenario"],
        "history": case["history"],
        "response": response_text,
        "rubric": {
            "relevance_0_to_4": "질문과 도메인에 정확히 답하는가. 엉뚱한 서비스나 다른 재료 답변은 0점.",
            "usefulness_0_to_4": "구체적이고 실행 가능한 정보를 주는가. 근거 없는 단정, 일반론, 오류는 감점.",
            "completeness_0_to_2": "질문의 조건, 수량, 시간, 확인 필요 여부를 빠뜨리지 않았는가.",
        },
        "instruction": "엄격하게 심사하세요. 응답이 질문을 회피하거나 일반론이면 낮게 점수화하세요. JSON만 반환하세요: relevance, usefulness, completeness, reason.",
    }
    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": "당신은 식생활 서비스 에이전트의 엄격한 품질 평가자입니다."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
    )
    result = json.loads(completion.choices[0].message.content or "{}")
    scores = {
        "relevance": max(0, min(4, int(result.get("relevance", 0)))),
        "usefulness": max(0, min(4, int(result.get("usefulness", 0)))),
        "completeness": max(0, min(2, int(result.get("completeness", 0)))),
    }
    return {**scores, "score": sum(scores.values()), "reason": str(result.get("reason") or "사유 없음")}


def main() -> None:
    """실제 응답 파일을 읽어 에이전트별 LLM 심사 결과를 저장합니다."""
    parser = argparse.ArgumentParser(description="에이전트 실제 응답 LLM 심사")
    parser.add_argument("--results", type=Path, required=True, help="도메인 에이전트 실행 결과 JSONL")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/domain-agent-llm-judge.json"))
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), help="심사에 사용할 OpenAI 모델")
    args = parser.parse_args()

    cases = {case["id"]: case for case in _load_cases()}
    rows = _load_jsonl(args.results)
    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    by_agent: dict[str, list[dict]] = defaultdict(list)
    excluded: list[dict] = []

    for row in rows:
        if _is_infrastructure_error(row):
            excluded.append({"id": row["id"], "agent": row["agent"], "reason": row.get("error") or "agent_status=error"})
            continue
        judged = _judge_response(client, args.model, cases[row["id"]], str(row.get("response_text") or ""))
        by_agent[row["agent"]].append({"id": row["id"], "response_text": str(row.get("response_text") or ""), **judged})

    summary = {}
    for agent, scores in sorted(by_agent.items()):
        total = sum(item["score"] for item in scores)
        summary[agent] = {
            "evaluated": len(scores),
            "average_score_10": round(total / len(scores), 2) if scores else None,
            "average_score_100": round(total * 10 / len(scores), 1) if scores else None,
            "details": scores,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"by_agent": summary, "excluded": excluded}, ensure_ascii=False, indent=2), encoding="utf-8")
    for agent, item in summary.items():
        print(f"{agent}: {item['average_score_10']}/10 ({item['average_score_100']}점), evaluated={item['evaluated']}")
    print(f"excluded={len(excluded)}")


if __name__ == "__main__":
    main()
