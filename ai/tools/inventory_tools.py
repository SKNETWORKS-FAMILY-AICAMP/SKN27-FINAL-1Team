from pydantic import BaseModel, Field
from langchain_core.tools import tool

class ConsumeIngredientInput(BaseModel):
    ingredient_name: str = Field(description="소비할 식재료의 이름 (예: 두부, 감자)")
    quantity: float = Field(description="소비할 수량 (예: 1, 0.5 등)")

@tool("consume_ingredient", args_schema=ConsumeIngredientInput)
def consume_ingredient_tool(ingredient_name: str, quantity: float) -> str:
    """사용자가 특정 식재료를 사용(소비)했거나 먹었다고 할 때 호출하여 수량을 차감합니다. 
    이 도구를 호출하려면 반드시 식재료 이름과 소비한 수량 정보가 필요합니다. 
    만약 사용자가 수량을 말하지 않았다면 호출하지 말고 수량을 물어보세요."""
    # TODO: 실제 DB 연동 로직은 chat_graph에서 session 주입 등을 통해 구현해야 함.
    # 지금은 테스트용 메시지를 반환합니다.
    return f"{ingredient_name} {quantity}개가 정상적으로 소비(차감) 처리되었습니다!"

class AddIngredientInput(BaseModel):
    ingredient_name: str = Field(description="새로 추가할 식재료의 이름")
    quantity: float = Field(description="추가할 수량")
    storage_method: str = Field(default="\ub0c9\uc7a5", description="보관 방법 (냉장, 냉동, 실온 중 택 1)")

@tool("add_ingredient", args_schema=AddIngredientInput)
def add_ingredient_tool(ingredient_name: str, quantity: float, storage_method: str) -> str:
    """사용자가 냉장고에 새로운 식재료를 넣었다고 할 때 호출합니다."""
    return f"{ingredient_name} {quantity}개가 {storage_method}에 추가되었습니다!"

INVENTORY_TOOLS = [consume_ingredient_tool, add_ingredient_tool]
