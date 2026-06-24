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

    def predict_storage_and_lifespan(self, ingredient_name: str, category: str = "기타", storage_method: str = None) -> tuple[str, int]:
        """
        OpenAI의 Tool Calling(ReAct 방식)을 활용하여, 식재료의 최적 보관 방법과 소비기한을 실시간으로 판단합니다.
        """
        if not self.openai_client:
            logger.warning("OPENAI_API_KEY가 설정되지 않아 기본값(냉장, 7일)을 반환합니다.")
            return storage_method or "냉장", 7

        system_prompt = (
            "당신은 식품 안전 및 식재료 보관 전문가 에이전트입니다.\n"
            "사용자가 식재료 이름, 카테고리를 제공하며, 보관 방법을 제공할 수도 있고 안 할 수도 있습니다. 검색 도구(search_food_expiration_info)를 통해 실시간으로 알아본 후 판단하세요.\n\n"
            "중요한 판단 과정 (Thinking Process):\n"
            "1. 입력된 식재료의 속성(생물, 가공식품, 건조/발효 등)을 파악하세요.\n"
            "2. 보관 방법이 주어지지 않은 경우(None 또는 미입력), 해당 식재료가 가장 신선하게 오래 유지될 수 있는 '최적의 보관 방법'(냉장, 냉동, 실온 중 택1)을 먼저 결정하세요.\n"
            "3. 결정된 보관 방법(또는 사용자가 이미 지정한 보관 방법)에 따라 다음 기준을 엄격히 적용하여 소비기한 일수를 도출하세요:\n"
            "   - [실온/상온 보관]: 수분이 많은 생물은 매우 짧게(1~3일), 곡류나 건조/가공/발효 식품은 매우 길게(수개월~년 단위) 설정합니다.\n"
            "   - [냉장 보관]: 일반적인 채소/고기/신선식품은 3일~2주일 내외, 유제품이나 소스류는 1개월 내외로 설정합니다.\n"
            "   - [냉동 보관]: 미생물 번식이 완전히 억제되므로 매우 깁니다. (예: 180일~365일 이상)\n"
            "4. 사용자의 건강을 위해 도출된 기간에서 20%의 '안전 마진'을 차감한 보수적인 일수를 도출하세요.\n\n"
            "최종 응답 규칙:\n"
            "응답은 반드시 '보관방법|일수' 형식이어야 합니다. (예: 냉장|14, 냉동|30, 실온|7)\n"
            "보관방법은 반드시 '냉장', '냉동', '실온' 중 하나여야 합니다. 숫자 부분은 정수만 가능하며, 다른 어떤 설명이나 단어도 포함하지 마세요."
        )

        user_content = f"식재료: {ingredient_name}, 카테고리: {category}"
        if storage_method:
            user_content += f", 보관 방법: {storage_method} (이 보관 방법을 기준으로 기한을 산출하세요)"
        else:
            user_content += ", 보관 방법: 미지정 (최적의 보관 방법을 스스로 판단하세요)"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
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
                    max_tokens=20
                )
                final_answer = second_response.choices[0].message.content.strip()
            else:
                # 도구를 사용하지 않고 바로 대답한 경우
                final_answer = response_message.content.strip()
            
            # "냉장|14" 형식 파싱
            parts = final_answer.split("|")
            if len(parts) == 2:
                final_storage = parts[0].strip()
                days_str = "".join(filter(str.isdigit, parts[1]))
                predicted_days = int(days_str) if days_str else 7
            else:
                # 파싱 실패 시 폴백
                final_storage = storage_method or "냉장"
                days_str = "".join(filter(str.isdigit, final_answer))
                predicted_days = int(days_str) if days_str else 7
            
            if final_storage not in ["냉장", "냉동", "실온"]:
                final_storage = "냉장"

            if predicted_days <= 0:
                predicted_days = 3
            if predicted_days > 730:
                predicted_days = 730
                
            return final_storage, predicted_days

        except Exception as e:
            logger.error(f"LLM 기반 에이전트 루프 중 오류 발생: {str(e)}")
            return storage_method or "냉장", 7 # 안전망(Fallback)

expiration_ai_service = ExpirationAIService()
