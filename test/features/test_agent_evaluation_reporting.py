"""반복 평가 집계와 사람 검수 표본 생성 규칙을 검증합니다."""

from scripts.agent_evaluation.export_agent_human_review_sample import render_markdown, select_samples
from scripts.agent_evaluation.summarize_agent_quality_runs import build_summary


def test_repeat_quality_summary_calculates_average_and_variance():
    """반복 심사 결과는 에이전트별 평균과 표준편차를 제공해야 합니다."""
    report = build_summary([
        {"by_agent": {"guide": {"average_score_10": 6.0}}},
        {"by_agent": {"guide": {"average_score_10": 8.0}}},
        {"by_agent": {"guide": {"average_score_10": 7.0}}},
    ])

    assert report["by_agent"]["guide"] == {
        "runs": 3,
        "average_score_10": 7.0,
        "standard_deviation": 0.816,
        "scores": [6.0, 8.0, 7.0],
    }


def test_human_review_sample_includes_low_middle_and_high_scores():
    """사람 검수 표본은 특정 점수대에 치우치지 않아야 합니다."""
    cases = {str(index): {"message": f"질문 {index}"} for index in range(3)}
    judge_result = {
        "by_agent": {
            "guide": {
                "details": [
                    {"id": "0", "score": 1, "reason": "낮음"},
                    {"id": "1", "score": 5, "reason": "중간"},
                    {"id": "2", "score": 9, "reason": "높음"},
                ]
            }
        }
    }

    markdown = render_markdown(select_samples(judge_result, cases, per_agent=3))

    assert "LLM 심사: 1 / 10" in markdown
    assert "LLM 심사: 5 / 10" in markdown
    assert "LLM 심사: 9 / 10" in markdown
