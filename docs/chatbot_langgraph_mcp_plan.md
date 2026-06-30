# 챗봇 LangGraph/MCP 확장 초안

## 목표
현재 챗봇은 질문에 답하는 라우터형 챗봇이다. 다음 단계는 사용자의 자연어를 실제 서비스 기능으로 연결하는 행동형 챗봇으로 확장한다.

## 1단계: Intent Router 고도화
- 냉장고 조회, 임박 재료, 보관법, 레시피 추천, 영수증 안내는 현재 라우터를 유지한다.
- 재료 추가, 재료 소비, 재료 폐기처럼 DB 변경이 필요한 intent만 별도로 분리한다.

## 2단계: LangGraph 상태 관리
- 대화 상태에 `intent`, `ingredient_name`, `quantity`, `unit`, `storage`, `pending_action`을 저장한다.
- 정보가 부족하면 바로 실행하지 않고 추가 질문을 한다.
- 예: “감자 추가해줘” → “몇 개 추가할까요?” → “2개” → 등록 확인.

## 3단계: MCP/API Tool Calling
- 백엔드 API를 직접 노출하지 않고 안전한 tool wrapper를 만든다.
- 후보 tool:
  - `inventory_add_item`
  - `inventory_consume_item`
  - `inventory_discard_item`
  - `inventory_list_items`
  - `recipe_search`
- 쓰기 작업은 실행 전 확인 메시지를 거친다.

## 4단계: 안전 장치
- 사용자의 소유 재료만 수정한다.
- 수량, 단위, 재료명 검증 실패 시 실행하지 않는다.
- 삭제/폐기/소비는 확인 응답 이후에만 실행한다.

## 예시 흐름
사용자: 내 냉장고에 감자 추가해줘  
챗봇: 감자를 몇 개 추가할까요?  
사용자: 2개  
챗봇: 감자 2개를 냉장고에 추가할까요?  
사용자: 응  
챗봇: 감자 2개를 추가했어요.