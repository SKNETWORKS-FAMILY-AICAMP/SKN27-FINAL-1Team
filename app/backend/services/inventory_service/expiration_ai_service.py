import json
import logging
import re

from app.backend.core.config import settings

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

try:
    from tavily import TavilyClient
except ImportError:
    TavilyClient = None

logger = logging.getLogger(__name__)

DEFAULT_STORAGE = "냉장"
VALID_STORAGE_METHODS = {"냉장", "냉동", "실온"}
DEFAULT_CATEGORY = "기타"
DRIED_SEAWEED_NAMES = {"김", "구운김", "조미김", "김가루", "마른김"}

# 카테고리만으로 판단하기 어려운 대표 식재료만 예외 룰로 관리합니다.
INGREDIENT_LIFESPAN_OVERRIDES = [
    {
        "keywords": ["김치", "kimchi", "깍두기", "오이소박이", "묵은지"],
        "days": {"냉장": 45, "냉동": 180, "실온": 2},
    },
    {
        "keywords": ["된장", "고추장", "간장", "쌈장"],
        "days": {"냉장": 180, "냉동": 365, "실온": 60},
    },
    {
        "keywords": ["두부"],
        "days": {"냉장": 5, "냉동": 30, "실온": 1},
    },
    {
        "keywords": ["계란", "달걀"],
        "days": {"냉장": 21, "냉동": 60, "실온": 7},
    },
    {
        "keywords": ["스팸"],
        "days": {"냉장": 365, "냉동": 365, "실온": 730},
    },
    {
        "keywords": ["얼음", "ice", "생수", "소금", "설탕", "꿀"],
        "days": {"냉장": 730, "냉동": 730, "실온": 730},
    },
]

# 일반 식재료는 식재료명 대신 카테고리와 보관 위치를 기준으로 보수적인 기본값을 사용합니다.
CATEGORY_LIFESPAN_RULES = {
    "채소": {"aliases": ["채소", "야채"], "days": {"냉장": 7, "냉동": 90, "실온": 2}},
    "과일": {"aliases": ["과일", "과채"], "days": {"냉장": 7, "냉동": 90, "실온": 3}},
    "육류": {"aliases": ["육류", "고기", "소고기", "돼지고기", "닭고기"], "days": {"냉장": 3, "냉동": 180, "실온": 1}},
    "수산물": {"aliases": ["수산물", "해산물", "생선", "어패류"], "days": {"냉장": 2, "냉동": 90, "실온": 1}},
    "유제품": {"aliases": ["유제품", "우유", "치즈", "요거트", "요구르트"], "days": {"냉장": 7, "냉동": 30, "실온": 1}},
    "가공식품": {"aliases": ["가공식품", "가공", "즉석식품"], "days": {"냉장": 30, "냉동": 180, "실온": 14}},
    "발효식품": {"aliases": ["발효식품", "발효"], "days": {"냉장": 45, "냉동": 180, "실온": 30}},
    "곡류": {"aliases": ["곡류", "쌀", "잡곡", "면", "파스타"], "days": {"냉장": 180, "냉동": 365, "실온": 180}},
    "조미료": {"aliases": ["조미료", "소스", "양념", "장류"], "days": {"냉장": 180, "냉동": 365, "실온": 60}},
    DEFAULT_CATEGORY: {"aliases": [DEFAULT_CATEGORY], "days": {"냉장": 7, "냉동": 30, "실온": 1}},
}


class ExpirationAIService:
    """식재료 보관 위치와 소비기한을 룰 기반 보정과 AI로 예측하는 서비스입니다."""

    def __init__(self):
        # 외부 API 클라이언트는 키와 패키지가 모두 준비된 경우에만 활성화합니다.
        self.openai_api_key = settings.OPENAI_API_KEY
        self.tavily_api_key = settings.TAVILY_API_KEY
        self.model = settings.OPENAI_MODEL

        self.openai_client = OpenAI(api_key=self.openai_api_key) if self.openai_api_key and OpenAI else None
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key) if self.tavily_api_key and TavilyClient else None

    def _normalize_storage_method(self, storage_method: str = None) -> str:
        """입력된 보관 방법을 서비스 표준 보관 위치로 정규화합니다."""
        return storage_method if storage_method in VALID_STORAGE_METHODS else DEFAULT_STORAGE

    def _normalize_category(self, category: str = None) -> str:
        """입력된 카테고리를 카테고리 소비기한 룰의 대표 키로 정규화합니다."""
        category_text = (category or "").replace(" ", "").lower()
        for normalized_category, rule in CATEGORY_LIFESPAN_RULES.items():
            if any(alias.replace(" ", "").lower() in category_text for alias in rule["aliases"]):
                return normalized_category
        return DEFAULT_CATEGORY

    def is_valid_ingredient_name(self, ingredient_name: str) -> bool:
        """초성 나열 같은 식재료가 아닌 입력을 최소 규칙으로 걸러냅니다."""
        name = (ingredient_name or "").strip()
        return bool(name and re.search(r"[가-힣A-Za-z]", name))

    def get_ingredient_override_lifespan(self, ingredient_name: str, storage_method: str = None) -> tuple[str, int] | None:
        """대표 식재료 예외 룰에 해당하면 보관 위치와 소비기한을 반환합니다."""
        name = (ingredient_name or "").replace(" ", "").lower()

        # 얼음은 보관 위치가 비어 있으면 냉동을 기본값으로 사용합니다.
        if "얼음" in name or "ice" in name:
            storage = storage_method if storage_method in VALID_STORAGE_METHODS else "냉동"
            return storage, 730

        storage = self._normalize_storage_method(storage_method)

        # 김은 한 글자라 김치 같은 다른 식재료와 섞이지 않게 정확한 이름만 보정합니다.
        if name in DRIED_SEAWEED_NAMES:
            seaweed_days = {"냉장": 180, "냉동": 365, "실온": 180}
            return storage, seaweed_days.get(storage, seaweed_days[DEFAULT_STORAGE])

        if "통조림" in name or name.endswith("캔") or name.startswith("캔"):
            canned_days = {"냉장": 365, "냉동": 365, "실온": 730}
            return storage, canned_days.get(storage, canned_days[DEFAULT_STORAGE])

        # 소스류는 사용자가 카테고리를 고르지 않아도 조미료 기준을 적용합니다.
        if "소스" in name:
            sauce_days = CATEGORY_LIFESPAN_RULES["조미료"]["days"]
            return storage, sauce_days.get(storage, sauce_days[DEFAULT_STORAGE])

        # 건조 파스타면은 보관 위치 미입력 시 실온 보관을 기본으로 사용합니다.
        if "파스타" in name or "스파게티" in name:
            storage = storage_method if storage_method in VALID_STORAGE_METHODS else "실온"
            pasta_days = {"냉장": 180, "냉동": 365, "실온": 365}
            return storage, pasta_days.get(storage, pasta_days["실온"])

        for rule in INGREDIENT_LIFESPAN_OVERRIDES:
            if any(keyword.replace(" ", "").lower() in name for keyword in rule["keywords"]):
                return storage, rule["days"].get(storage, rule["days"][DEFAULT_STORAGE])
        return None

    def _get_rule_based_lifespan(
        self,
        ingredient_name: str,
        category: str = None,
        storage_method: str = None,
    ) -> tuple[str, int]:
        """예외 식재료 룰을 먼저 보고, 없으면 카테고리 기본 룰로 소비기한을 계산합니다."""
        override = self.get_ingredient_override_lifespan(ingredient_name, storage_method)
        if override:
            return override

        storage = self._normalize_storage_method(storage_method)
        normalized_category = self._normalize_category(category)
        category_days = CATEGORY_LIFESPAN_RULES[normalized_category]["days"]
        return storage, category_days.get(storage, category_days[DEFAULT_STORAGE])

    def search_food_expiration_info(self, query: str) -> str:
        """Tavily Search API로 식재료 보관 기간 정보를 검색합니다."""
        if not self.tavily_client:
            return "검색 엔진이 활성화되어 있지 않습니다. 자체 지식을 사용하세요."

        try:
            logger.info("Tavily Search 호출 중: %s", query)
            response = self.tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=3,
                include_answer=True,
            )

            answer = response.get("answer", "")
            if answer:
                return answer

            results = response.get("results", [])
            content = "\n".join([f"- {res['content']}" for res in results])
            return content if content else "관련된 검색 결과가 없습니다."
        except Exception as exc:
            logger.error("Tavily 검색 중 오류 발생: %s", exc)
            return "검색 중 오류가 발생했습니다. 자체 지식을 사용하세요."

    def predict_storage_and_lifespan(
        self,
        ingredient_name: str,
        category: str = DEFAULT_CATEGORY,
        storage_method: str = None,
    ) -> tuple[str, int]:
        """식재료명과 보관 방법을 기준으로 권장 보관 위치와 소비기한 일수를 예측합니다."""
        normalized_storage = self._normalize_storage_method(storage_method)
        override = self.get_ingredient_override_lifespan(ingredient_name, storage_method)
        if override:
            return override

        rule_storage, rule_days = self._get_rule_based_lifespan(ingredient_name, category, normalized_storage)

        if not self.openai_client:
            logger.info("OpenAI 클라이언트가 없어 룰 기반 보관 기간을 반환합니다.")
            return rule_storage, rule_days

        system_prompt = (
            "당신은 식품 안전 및 식재료 보관 전문가 AI입니다.\n"
            "사용자가 식재료명, 카테고리, 보관 방법을 제공합니다. 보관 방법이 없으면 최적 보관 방법을 판단하세요.\n"
            "필요하면 search_food_expiration_info 도구로 정보를 확인한 뒤 보수적인 소비기한을 산출하세요.\n"
            "단, 얼음, 소금, 설탕, 생수 등 사실상 소비기한이 무제한이거나 상하지 않는 식재료는 일수를 730으로 반환하세요.\n"
            "최종 응답은 반드시 '보관방법|일수' 형식이어야 합니다. 예: 냉장|14\n"
            "보관방법은 반드시 '냉장', '냉동', '실온' 중 하나만 사용하고, 일수는 정수만 사용하세요."
        )

        user_content = f"식재료: {ingredient_name}, 카테고리: {category}, 보관 방법: {normalized_storage}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_food_expiration_info",
                    "description": "식재료의 보관 방법별 권장 소비기한을 웹에서 검색합니다.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "검색어 예: 김치 냉장 보관 기간",
                            }
                        },
                        "required": ["query"],
                    },
                },
            }
        ]

        try:
            # 1차 호출에서 모델이 검색 도구를 사용할지 판단합니다.
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
            )

            response_message = response.choices[0].message
            messages.append(response_message)

            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    if tool_call.function.name != "search_food_expiration_info":
                        continue

                    args = json.loads(tool_call.function.arguments)
                    search_result = self.search_food_expiration_info(args.get("query", ""))
                    messages.append(
                        {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": "search_food_expiration_info",
                            "content": search_result,
                        }
                    )

                # 검색 결과를 반영해 최종 보관 방법과 일수를 다시 받습니다.
                second_response = self.openai_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=20,
                )
                final_answer = second_response.choices[0].message.content.strip()
            else:
                final_answer = response_message.content.strip()

            return self._parse_ai_answer(final_answer, normalized_storage, rule_days)
        except Exception as exc:
            logger.error("소비기한 AI 예측 중 오류 발생: %s", exc)
            return rule_storage, rule_days

    def _parse_ai_answer(self, answer: str, fallback_storage: str, fallback_days: int) -> tuple[str, int]:
        """AI 응답을 서비스에서 사용할 보관 방법과 일수로 변환합니다."""
        parts = (answer or "").split("|")
        if len(parts) == 2:
            final_storage = parts[0].strip()
            days_text = parts[1]
        else:
            final_storage = fallback_storage
            days_text = answer or ""

        days_str = "".join(filter(str.isdigit, days_text))
        predicted_days = int(days_str) if days_str else fallback_days

        if final_storage not in VALID_STORAGE_METHODS:
            final_storage = fallback_storage

        if predicted_days <= 0:
            predicted_days = 3
        if predicted_days > 730:
            predicted_days = 730

        return final_storage, predicted_days

    def predict_ingredient_info(self, ingredient_name: str) -> dict:
        """식재료명만으로 유효성, 보관방법, 일수를 종합적으로 예측합니다."""
        if not self.is_valid_ingredient_name(ingredient_name):
            return {
                "is_valid_food": False,
                "storage_method": "",
                "lifespan_days": 0
            }

        if not self.openai_client:
            return {
                "is_valid_food": True,
                "storage_method": "",
                "lifespan_days": 7
            }
        system_prompt = (
            "당신은 식재료 전문가 AI입니다.\n"
            "사용자가 입력한 단어가 먹을 수 있는 실제 식재료인지 판단하세요.\n"
            "장난스러운 입력(예: 'ㅁㄴㅇ', '책상', '폰')이면 유효성을 False로 반환하세요.\n"
            "식재료가 맞다면, 최적의 보관 방법(냉장, 냉동, 실온 중 택1)과 보수적인 소비기한 일수를 추론하세요.\n"
            "단, 얼음, 소금, 설탕, 생수 등 사실상 상하지 않는 재료는 일수를 730으로 반환하세요.\n"
            "응답 형식은 반드시 'True/False|보관방법|일수' 형식이어야 합니다.\n"
            "예시1: True|냉장|14\n"
            "예시2: True|냉동|730\n"
            "예시3: False|실온|0"
        )

        try:
            response = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": ingredient_name},
                ],
                temperature=0.1,
                max_tokens=30,
            )
            answer = response.choices[0].message.content.strip()
            parts = answer.split("|")

            if len(parts) >= 3:
                is_valid = parts[0].strip().lower() == "true"
                storage = parts[1].strip()
                days_str = "".join(filter(str.isdigit, parts[2]))
                days = int(days_str) if days_str else 7

                if storage not in VALID_STORAGE_METHODS:
                    storage = DEFAULT_STORAGE

                return {
                    "is_valid_food": is_valid,
                    "storage_method": storage,
                    "lifespan_days": min(max(days, 1), 730) if is_valid else 0
                }
        except Exception as exc:
            logger.error("식재료 종합 정보 예측 중 오류 발생: %s", exc)

        return {
            "is_valid_food": True,
            "storage_method": "",
            "lifespan_days": 7
        }


expiration_ai_service = ExpirationAIService()
