import json
import logging
from openai import OpenAI
from app.backend.core.config import settings

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

logger = logging.getLogger(__name__)

class ExpirationAIService:
    def __init__(self):
        # API Keys 설정
        self.openai_api_key = settings.OPENAI_API_KEY
        self.tavily_api_key = settings.TAVILY_API_KEY
        self.model = settings.OPENAI_MODEL
        
        self.openai_client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key else None
        
        # Tavily Client 초기화 (키가 있거나 패키지가 설치된 경우에만)
        if self.tavily_api_key and TavilyClient:
            self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
        else:
            self.tavily_client = None

    def search_food_expiration_info(self, query: str) -> str:
        """
        Tavily Search API를 통해 식재료 보관 기한 정보를 검색합니다.
        """
        if not self.tavily_client:
            return "검색 엔진(Tavily)이 활성화되어 있지 않습니다. 자체 지식만 활용하세요."
        
        try:
            logger.info(f"Tavily Search 호출 중: {query}")
            response = self.tavily_client.search(
                query=query, 
                search_depth="advanced", 
                max_results=3,
                include_answer=True
            )
            # Tavily의 요약된 AI 응답을 우선 사용하거나 검색 결과 본문을 합침
            answer = response.get("answer", "")
            if answer:
                return answer
                
            results = response.get("results", [])
            content = "\n".join([f"- {res['content']}" for res in results])
            return content if content else "관련된 검색 결과가 없습니다."
        except Exception as e:
            logger.error(f"Tavily 검색 중 오류 발생: {str(e)}")
            return "검색 중 오류가 발생했습니다. 자체 지식을 활용하세요."

    def predict_expiration_days(self, ingredient_name: str, category: str = "기타", storage_method: str = "냉장") -> int:
        """
        OpenAI의 Tool Calling(ReAct 방식)을 활용하여, 식재료 소비기한을 실시간으로 검색하고 판단합니다.
        """
        if not self.openai_client:
            logger.warning("OPENAI_API_KEY가 설정되지 않아 기본 소비기한(7일)을 반환합니다.")
            return 7

        system_prompt = (
            "당신은 식품 안전 및 식재료 보관 전문가 에이전트입니다.\n"
            "사용자가 식재료 이름, 카테고리, 보관 방법을 제공하면, 검색 도구(search_food_expiration_info)를 통해 실시간으로 알아본 후 판단하세요.\n\n"
            "중요한 판단 과정 (Thinking Process):\n"
            "1. 입력된 식재료의 속성(생물, 가공식품, 건조/발효 등)을 파악하세요. 만약 사용자가 선택한 '카테고리'가 식재료의 '이름'과 명백히 모순될 경우(예: 이름은 '삼겹살'인데 카테고리가 '채소'이거나 '기타'인 경우), 잘못된 카테고리를 무시하고 식재료 '이름'의 본질적 속성을 최우선으로 판단하세요.\n"
            "2. 사용자가 제시한 '보관 방법'에 따라 다음 기준을 엄격히 적용하여 기본 소비기한을 도출하세요:\n"
            "   - [실온/상온 보관]: 수분이 많은 생물은 매우 짧게(1~3일), 곡류나 건조/가공/발효 식품은 매우 길게(수개월~년 단위) 설정합니다.\n"
            "   - [냉장 보관]: 일반적인 채소/고기/신선식품은 3일~2주일 내외, 유제품이나 소스류는 1개월 내외로 설정합니다.\n"
            "   - [냉동 보관]: 미생물 번식이 완전히 억제되므로 '냉장'이나 '실온'에 비해 소비기한이 월등히(보통 6개월~1년 이상) 깁니다. (예: 냉동 양파, 냉동 고기 등은 180일~365일 이상)\n"
            "3. 사용자의 건강을 위해 도출된 기간에서 20%의 '안전 마진'을 차감한 보수적인 일수를 도출하되, 보관 기한이 긴 품목(냉동, 발효 등)은 20% 차감 후에도 충분히 긴 기한이 유지되도록 합리적으로 계산하세요.\n\n"
            "최종 응답 규칙:\n"
            "오직 '정수(숫자)' 1개만 반환하세요. 다른 어떤 설명이나 단어(일, days 등)도 절대 포함하면 안 됩니다."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"식재료: {ingredient_name}, 카테고리: {category}, 보관 방법: {storage_method}"}
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_food_expiration_info",
                    "description": "식재료의 보관 방법에 따른 식약처 권장 유통기한/소비기한을 웹에서 검색합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "검색어 (예: '시금치 냉장 보관 기간', '비비고 만두 냉동 소비기한')"
                            }
                        },
                        "required": ["query"]
                    }
                }
            }
        ]

        try:
            # 1차 호출: LLM이 도구 사용 여부를 판단
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1
            )
            
            response_message = response.choices[0].message
            messages.append(response_message)
            
            # 2. 도구(Tool) 호출이 있는지 확인
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name == "search_food_expiration_info":
                        args = json.loads(tool_call.function.arguments)
                        query = args.get("query")
                        
                        # 실제 도구 함수 실행
                        search_result = self.search_food_expiration_info(query)
                        
                        # 결과를 메시지 목록에 추가
                        messages.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": "search_food_expiration_info",
                            "content": search_result
                        })
                        
                # 3. 도구 실행 결과를 포함하여 2차 호출 (최종 결론 도출)
                second_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=10
                )
                final_answer = second_response.choices[0].message.content.strip()
            else:
                # 도구를 사용하지 않고 바로 대답한 경우
                final_answer = response_message.content.strip()
            
            # 숫자만 포함되어 있는지 확인 및 파싱
            predicted_days = int("".join(filter(str.isdigit, final_answer)))
            
            if predicted_days <= 0:
                return 3
            if predicted_days > 730:
                return 730
                
            return predicted_days

        except Exception as e:
            logger.error(f"LLM 기반 에이전트 루프 중 오류 발생: {str(e)}")
            return 7 # 안전망(Fallback)

expiration_ai_service = ExpirationAIService()
