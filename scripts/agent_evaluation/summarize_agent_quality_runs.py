"""반복 실행한 Agent 품질 심사 결과를 평균과 변동 폭으로 집계합니다."""

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path


def load_judge_result(path: Path) -> dict:
    """LLM 심사 결과 JSON 파일을 읽습니다."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_summary(results: list[dict]) -> dict:
    """에이전트별 반복 심사 점수의 평균과 표준편차를 계산합니다."""
    scores_by_agent: dict[str, list[float]] = defaultdict(list)
    for result in results:
        for agent, item in result.get("by_agent", {}).items():
            score = item.get("average_score_10")
            if score is not None:
                scores_by_agent[agent].append(float(score))

    by_agent = {}
    for agent, scores in sorted(scores_by_agent.items()):
        by_agent[agent] = {
            "runs": len(scores),
            "average_score_10": round(statistics.mean(scores), 2),
            "standard_deviation": round(statistics.pstdev(scores), 3),
            "scores": scores,
        }

    all_scores = [score for scores in scores_by_agent.values() for score in scores]
    return {
        "runs": len(results),
        "by_agent": by_agent,
        "overall_average_score_10": round(statistics.mean(all_scores), 2) if all_scores else None,
    }


def main() -> None:
    """여러 심사 결과 파일을 하나의 반복 평가 보고서로 저장합니다."""
    parser = argparse.ArgumentParser(description="반복 Agent 품질 평가 결과 집계")
    parser.add_argument("--inputs", type=Path, nargs="+", required=True, help="LLM 심사 결과 JSON 파일 목록")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/domain-agent-repeat-summary.json"))
    args = parser.parse_args()

    report = build_summary([load_judge_result(path) for path in args.inputs])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    for agent, item in report["by_agent"].items():
        print(f"{agent}: {item['average_score_10']}/10, 표준편차={item['standard_deviation']}, 실행={item['runs']}회")


if __name__ == "__main__":
    main()
