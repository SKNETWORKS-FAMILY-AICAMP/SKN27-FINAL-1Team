"""Supervisor 라우팅 회귀 사례를 검증합니다."""

from ai.agents.supervisor_agent.supervisor_agent import router_node


def test_registered_ingredient_list_is_not_treated_as_add_request():
    """등록한 식재료 조회 문장이 재료 추가로 오분류되지 않는지 확인합니다."""
    result = router_node({"text": "등록한 식재료 보여줘", "history": []})

    assert result["intent"] == "inventory.list"


def test_guide_and_calendar_lists_keep_their_domain_priority():
    """분류 목록과 일정 목록은 냉장고 재료 목록으로 오분류되지 않는지 확인합니다."""
    guide_result = router_node({"text": "채소에 뭐가 있어?", "history": []})
    calendar_result = router_node({"text": "다음주 일정 뭐 있어?", "history": []})

    assert guide_result["intent"] == "ingredient.guide"
    assert calendar_result["intent"] == "alarm.calendar"