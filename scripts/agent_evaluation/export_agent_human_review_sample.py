"""LLM 심사 결과에서 사람 검수용 표본을 Markdown으로 만듭니다."""

import argparse
import json
from pathlib import Path


DATASET_PATHS = (
    Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl"),
    Path("test/fixtures/agent_evaluation/agent_regression_cases.jsonl"),
)


def load_jsonl(path: Path) -> list[dict]:
    """UTF-8 JSONL 평가 데이터를 읽습니다."""
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def select_samples(judge_result: dict, cases: dict[str, dict], per_agent: int) -> list[dict]:
    """낮은 점수와 중간 점수, 높은 점수를 섞어 검수 표본을 고릅니다."""
    samples = []
    for agent, item in sorted(judge_result.get("by_agent", {}).items()):
        details = sorted(item.get("details", []), key=lambda row: row["score"])
        if not details:
            continue
        indexes = sorted({0, len(details) // 2, len(details) - 1})
        selected = [details[index] for index in indexes]
        samples.extend({"agent": agent, **row, "case": cases[row["id"]]} for row in selected[:per_agent])
    return samples


def render_markdown(samples: list[dict]) -> str:
    """사람 검수자가 점수와 의견을 직접 기록할 Markdown 표를 만듭니다."""
    lines = ["# Agent 사람 검수 표본", "", "각 항목을 관련성·유용성·완결성 기준으로 0~10점으로 평가합니다.", ""]
    for sample in samples:
        lines.extend([
            f"## {sample['agent']} · {sample['id']}",
            f"- 질문: {sample['case']['message']}",
            f"- Agent 응답: {sample.get('response_text', '')}",
            f"- LLM 심사: {sample['score']} / 10 ({sample['reason']})",
            "- 사람 점수: ",
            "- 사람 의견: ",
            "",
        ])
    return "\n".join(lines)


def main() -> None:
    """사람 검수 표본 문서를 생성합니다."""
    parser = argparse.ArgumentParser(description="Agent 사람 검수 표본 생성")
    parser.add_argument("--judge", type=Path, required=True, help="LLM 심사 결과 JSON 파일")
    parser.add_argument("--output", type=Path, default=Path("outputs/agent_evaluations/agent-human-review-sample.md"))
    parser.add_argument("--per-agent", type=int, default=3, help="에이전트별 검수 표본 수")
    parser.add_argument("--responses", type=Path, help="원문 Agent 응답 JSONL. 기존 심사 결과 보완용")
    args = parser.parse_args()

    cases = {case["id"]: case for path in DATASET_PATHS for case in load_jsonl(path)}
    judge_result = json.loads(args.judge.read_text(encoding="utf-8-sig"))
    samples = select_samples(judge_result, cases, args.per_agent)
    if args.responses:
        response_by_id = {row["id"]: row.get("response_text", "") for row in load_jsonl(args.responses)}
        for sample in samples:
            sample["response_text"] = sample.get("response_text") or response_by_id.get(sample["id"], "")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_markdown(samples), encoding="utf-8")
    print(f"사람 검수 표본 {len(samples)}건을 {args.output}에 저장했습니다.")


if __name__ == "__main__":
    main()
