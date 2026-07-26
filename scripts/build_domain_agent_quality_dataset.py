"""도메인 에이전트의 재현 가능한 고난도 품질 평가셋을 생성합니다."""

import json
from copy import deepcopy
from pathlib import Path


OUTPUT_PATH = Path("test/fixtures/agent_evaluation/domain_agent_quality_cases.jsonl")
VARIANTS = {
    "inventory": ("감자", "양파", "두부", "호박"),
    "guide": ("감자", "양파", "고추", "딸기"),
    "recipe": ("감자", "두부", "대파", "닭가슴살"),
    "shopping": ("우유", "계란", "파스타면", "올리브유"),
    "alarm": ("장보기", "우유 사기", "두부 먹기", "회의"),
    "general_food": ("설탕", "간장", "냉동 피자", "남은 치킨"),
}


def _acceptance(*, any_words, forbidden=(), action=False, labels=(), sources=0, source_url=False, slots=()):
    """모든 에이전트가 공유하는 응답 품질 채점 기준을 만듭니다."""
    return {
        "must_contain_any": list(any_words),
        "must_contain_all": [],
        "forbidden_patterns": list(forbidden),
        "minimum_length": 20,
        "requires_action": action,
        "required_action_labels": list(labels),
        "minimum_sources": sources,
        "requires_source_url": source_url,
        "required_slot_keys": list(slots),
    }


def _scenario(message, scenario, acceptance, history=None):
    """시나리오 정의를 평가 데이터 한 행으로 정리합니다."""
    return {
        "message": message,
        "scenario": scenario,
        "history": history or [],
        "acceptance": acceptance,
    }


def _inventory_scenarios(item):
    return [
        _scenario(f"냉장고에 {item} 2개 추가해줘", "수량과 보관 위치 확인", _acceptance(any_words=(item, "확인"), action=True, labels=("확인",))),
        _scenario(f"{item} 1개 먹었어", "소비 전 확인", _acceptance(any_words=(item, "확인"), action=True, labels=("확인",))),
        _scenario(f"{item} 전부 폐기해줘", "전체 폐기 수량 확인", _acceptance(any_words=(item, "확인"), forbidden=("폐기 처리했어요",), action=True)),
        _scenario(f"냉동실에 있는 {item} 재고 알려줘", "보관 위치 재고 조회", _acceptance(any_words=(item, "냉동"), forbidden=("장보기 목록",))),
        _scenario(f"{item} 중에 소비기한 임박한 게 있어?", "특정 재료 소비기한 조회", _acceptance(any_words=(item, "소비기한", "D-"))),
        _scenario("그거 2개로 추가할게", "직전 추가 요청의 수량 보완", _acceptance(any_words=(item, "2개", "확인"), action=True), [{"role": "bot", "text": f"{item}를 몇 개 추가할까요?"}]),
        _scenario(f"{item} 냉장으로 넣으려던 거 취소해줘", "대기 중인 추가 요청 취소", _acceptance(any_words=(item, "취소"), action=True), [{"role": "bot", "text": f"{item}를 냉장고에 추가할까요?"}]),
        _scenario(f"{item} 5개 중 2개만 버릴게", "일부 폐기 수량 보존", _acceptance(any_words=(item, "2개", "확인"), action=True)),
        _scenario(f"내 냉장고에 {item} 남아 있어?", "특정 재료 재고 조회", _acceptance(any_words=(item, "냉장고"), forbidden=("장보기",))),
        _scenario(f"{item} 보관 위치를 냉동으로 바꿔줘", "보관 위치 변경 확인", _acceptance(any_words=(item, "냉동", "확인"), action=True)),
    ]


def _guide_scenarios(item):
    return [
        _scenario(f"{item} 보관법 알려줘", "보관 가이드 조회", _acceptance(any_words=(item, "보관"), sources=1)),
        _scenario(f"{item} 깨끗하게 세척하는 방법", "세척 가이드 조회", _acceptance(any_words=(item, "세척", "씻"), sources=1)),
        _scenario(f"{item} 상했는지 확인하는 법", "신선도 판별 안내", _acceptance(any_words=(item, "신선", "상"), sources=1)),
        _scenario(f"{item} 영양성분과 칼로리 알려줘", "영양 정보 조회", _acceptance(any_words=(item, "칼로리", "영양"), sources=1)),
        _scenario(f"{item} 손질은 어떻게 해?", "손질 가이드 조회", _acceptance(any_words=(item, "손질"), sources=1)),
        _scenario("그럼 냉동 보관은?", "직전 식재료의 보관 후속 질문", _acceptance(any_words=(item, "냉동", "보관"), sources=1), [{"role": "bot", "text": f"{item} 냉장 보관법을 안내했어요.", "intent": "ingredient.guide", "slots": {"ingredient": item, "guide_type": "storage"}}]),
        _scenario(f"{item} 말고 양파 보관법 알려줘", "식재료 정정", _acceptance(any_words=("양파", "보관"), forbidden=(f"{item} 보관법",), sources=1), [{"role": "bot", "text": f"{item} 보관법을 안내했어요."}]),
        _scenario(f"{item} 제철이 언제야?", "제철 정보 조회", _acceptance(any_words=(item, "제철", "월"), sources=1)),
        _scenario(f"{item}와 비슷한 식재료도 알려줘", "연관 식재료 조회", _acceptance(any_words=(item, "비슷", "식재료"), sources=1)),
        _scenario(f"{item} 보관할 때 피해야 할 점", "보관 주의사항 안내", _acceptance(any_words=(item, "보관", "피"), sources=1)),
    ]


def _recipe_scenarios(item):
    return [
        _scenario(f"냉장고 재료와 {item}로 저녁 메뉴 추천해줘", "보유 재료 기반 추천", _acceptance(any_words=(item, "레시피"), sources=1)),
        _scenario(f"{item}로 30분 안에 만들 수 있는 요리", "시간 제약 레시피 추천", _acceptance(any_words=(item, "30분", "레시피"), sources=1)),
        _scenario(f"소비기한 임박한 {item}을 먼저 쓰는 메뉴 추천", "임박 재료 우선 추천", _acceptance(any_words=(item, "소비기한", "레시피"), sources=1)),
        _scenario(f"{item} 레시피 조리 시간 알려줘", "특정 재료 조리법 탐색", _acceptance(any_words=(item, "분", "레시피"), sources=1)),
        _scenario(f"{item}과 잘 어울리는 사이드 메뉴", "음식 페어링", _acceptance(any_words=(item, "어울", "사이드"), sources=1)),
        _scenario(f"{item}로 초보도 실패 없는 요리 추천", "난이도 제약 추천", _acceptance(any_words=(item, "간단", "레시피"), sources=1)),
        _scenario(f"{item}를 많이 쓸 수 있는 한 끼 메뉴", "재료 소진 추천", _acceptance(any_words=(item, "메뉴", "레시피"), sources=1)),
        _scenario(f"{item} 없이 만들 수 있는 대체 레시피", "재료 대체 추천", _acceptance(any_words=(item, "대체", "레시피"), sources=1)),
        _scenario(f"{item} 들어간 도시락 메뉴 추천", "용도 제약 추천", _acceptance(any_words=(item, "도시락", "레시피"), sources=1)),
        _scenario(f"어제 본 {item} 레시피 말고 다른 메뉴 보여줘", "중복 레시피 제외", _acceptance(any_words=(item, "다른", "레시피"), sources=1), [{"role": "bot", "text": f"{item} 레시피를 보여드렸어요.", "intent": "recipe.recommend", "slots": {"shown_recipe_ids": [1, 2]}}]),
    ]


def _shopping_scenarios(item):
    return [
        _scenario(f"{item} 가격 비교해줘", "단일 상품 가격 비교", _acceptance(any_words=(item, "가격"))),
        _scenario(f"장보기 목록에 {item} 넣어줘", "장보기 추가 전 확인", _acceptance(any_words=(item, "확인"), action=True)),
        _scenario(f"장보기 목록에서 {item} 빼줘", "장보기 삭제 전 확인", _acceptance(any_words=(item, "삭제", "확인"), action=True)),
        _scenario(f"{item} 더 싼 판매처 없어?", "가격 비교 후속 요청", _acceptance(any_words=(item, "가격", "판매처")), [{"role": "bot", "text": f"{item} 가격 비교 결과예요.", "intent": "shopping.compare", "slots": {"shopping_product": item}}]),
        _scenario(f"{item} 가격 정보가 안 나오는 이유", "가격 부재 사유 안내", _acceptance(any_words=(item, "가격", "정보"))),
        _scenario(f"{item} 2개를 장보기 목록에 추가할까?", "수량 포함 장보기 추가 확인", _acceptance(any_words=(item, "확인"), action=True)),
        _scenario(f"이번 주에 산 {item} 기록 보여줘", "구매 이력 조회", _acceptance(any_words=(item, "장보", "기록"))),
        _scenario(f"현재 장보기 목록에서 {item} 남아 있어?", "현재 목록 특정 항목 조회", _acceptance(any_words=(item, "장보기"))),
        _scenario(f"{item}와 우유를 같이 가격 비교해줘", "복수 상품 가격 비교", _acceptance(any_words=(item, "우유", "가격"))),
        _scenario("나머지 품목도 전부 보여줘", "축약된 장보기 목록 확장", _acceptance(any_words=("장보기", "목록")), [{"role": "bot", "text": f"{item} 외 3개가 더 있어요.", "intent": "shopping.current", "slots": {}}]),
    ]


def _alarm_scenarios(item):
    return [
        _scenario(f"내일 {item} 일정 등록해줘", "날짜 포함 일정 생성", _acceptance(any_words=(item, "내일", "확인"), action=True)),
        _scenario(f"내일 오후 7시에 {item} 알림 등록", "시간 포함 알림 생성", _acceptance(any_words=(item, "오후 7시", "확인"), action=True)),
        _scenario(f"다음 주 화요일 {item} 일정 추가해줘", "상대 날짜 일정 생성", _acceptance(any_words=(item, "다음 주 화요일", "확인"), action=True)),
        _scenario(f"내일 {item} 일정 있어?", "날짜 기준 일정 조회", _acceptance(any_words=(item, "일정"))),
        _scenario(f"{item} 알림 읽음 처리해줘", "알림 상태 변경 확인", _acceptance(any_words=(item, "읽음", "확인"), action=True)),
        _scenario(f"내일 {item} 일정 삭제해줘", "일정 삭제 전 확인", _acceptance(any_words=(item, "삭제", "확인"), action=True)),
        _scenario(f"30분 뒤 {item} 알림 맞춰줘", "상대 시간 알림 생성", _acceptance(any_words=(item, "30분", "확인"), action=True)),
        _scenario(f"이번 주 {item} 관련 알림 보여줘", "알림 목록 조회", _acceptance(any_words=(item, "알림"))),
        _scenario(f"{item} 일정 시간을 오후 8시로 바꿔줘", "일정 수정 확인", _acceptance(any_words=(item, "오후 8시", "확인"), action=True)),
        _scenario("그 일정 취소해줘", "직전 일정 취소", _acceptance(any_words=(item, "취소", "확인"), action=True), [{"role": "bot", "text": f"내일 {item} 일정을 등록할까요?", "intent": "alarm.calendar", "slots": {"keyword": item, "date": "내일"}}]),
    ]


def _general_food_scenarios(item):
    return [
        _scenario(f"{item} 1큰술은 몇 ml야?", "조리 단위 환산", _acceptance(any_words=(item, "ml", "큰술"))),
        _scenario(f"{item} 대신 쓸 수 있는 재료", "재료 대체 안내", _acceptance(any_words=(item, "대신", "대체"))),
        _scenario(f"{item} 맛있게 데우는 방법", "재가열 조리 팁", _acceptance(any_words=(item, "데우", "온도", "시간"))),
        _scenario(f"{item}와 식물성 대체품 차이가 뭐야?", "식품 비교", _acceptance(any_words=(item, "차이", "맛"))),
        _scenario(f"{item} 너무 짤 때 맛을 조절하는 법", "조리 실패 보정", _acceptance(any_words=(item, "짠", "조절"))),
        _scenario(f"{item} 남았을 때 활용 아이디어", "남은 음식 활용", _acceptance(any_words=(item, "활용", "먹"))),
        _scenario(f"{item}를 처음 먹는 사람에게 추천하는 조합", "음식 조합 제안", _acceptance(any_words=(item, "추천", "조합"))),
        _scenario(f"{item} 한 컵은 몇 g 정도야?", "부피·무게 환산", _acceptance(any_words=(item, "g", "컵"))),
        _scenario(f"{item} 조리할 때 불 조절 팁", "조리 기법 안내", _acceptance(any_words=(item, "불", "조리"))),
        _scenario(f"{item}와 어울리지 않는 재료가 있어?", "궁합 주의 안내", _acceptance(any_words=(item, "어울", "주의"))),
    ]


SCENARIO_BUILDERS = {
    "inventory": _inventory_scenarios,
    "guide": _guide_scenarios,
    "recipe": _recipe_scenarios,
    "shopping": _shopping_scenarios,
    "alarm": _alarm_scenarios,
    "general_food": _general_food_scenarios,
}


def build_cases() -> list[dict]:
    """에이전트별 40건, 총 240건의 개발·홀드아웃 평가 케이스를 생성합니다."""
    cases = []
    for agent, variants in VARIANTS.items():
        index = 1
        for item in variants:
            for scenario in SCENARIO_BUILDERS[agent](item):
                case = deepcopy(scenario)
                case.update({
                    "id": f"{agent}-{index:02d}",
                    "agent": agent,
                    "difficulty": "hard",
                    "split": "dev" if index <= 30 else "holdout",
                    "expected": {"scenario": case.pop("scenario"), "acceptance": case.pop("acceptance")},
                })
                cases.append(case)
                index += 1
    return cases


def main() -> None:
    """생성 결과를 버전 관리하는 JSONL 평가셋 파일로 저장합니다."""
    cases = build_cases()
    OUTPUT_PATH.write_text(
        "\n".join(json.dumps(case, ensure_ascii=False) for case in cases) + "\n",
        encoding="utf-8",
    )
    print(f"{len(cases)}건 평가셋을 {OUTPUT_PATH}에 저장했습니다.")


if __name__ == "__main__":
    main()
