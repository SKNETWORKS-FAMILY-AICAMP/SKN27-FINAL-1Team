# 식재료 가이드 MCP 정규화 JSON

## 1. JSON 스키마

아래는 실제 값이 아닌 입력·출력 필드 구조입니다.

```json
{
  "tool": "food_guide_lookup",
  "input": {
    "ingredient": "string",
    "sections": ["seasonality|storage|prep|washing|freshness|nutrition"]
  },
  "output": {
    "status": "ok|partial|not_found",
    "requested_sections": ["string"],
    "matched_by": "name|display_name|alias|null",
    "ingredient": {
      "ingredient_id": "string",
      "name": "string",
      "display_name": "string",
      "classification": "string",
      "data_source_type": "string",
      "aliases": [{"alias_id": "string", "name": "string"}],
      "category": {
        "major": {"major_id": "string", "name": "string"},
        "middle": {"middle_id": "string", "name": "string"}
      }
    },
    "seasonality": {
      "status": "available|missing",
      "months": [1],
      "source": {"name": "string", "url": "string|null"}
    },
    "guides": {
      "storage": {"label": "보관방법", "status": "available|missing", "guide_id": "string|null", "content": "string|null", "source": "object|null"},
      "prep": {"label": "손질방법", "status": "available|missing", "guide_id": "string|null", "content": "string|null", "source": "object|null"},
      "washing": {"label": "세척방법", "status": "available|missing", "guide_id": "string|null", "content": "string|null", "source": "object|null"},
      "freshness": {"label": "신선도 확인법", "status": "available|missing", "guide_id": "string|null", "content": "string|null", "source": "object|null"}
    },
    "nutrition": {
      "status": "available|missing",
      "nutrition_id": "string|null",
      "representative_food_name": "string|null",
      "standard_amount": "string|null",
      "energy_kcal": "number|null",
      "water_g": "number|null",
      "protein_g": "number|null",
      "fat_g": "number|null",
      "ash_g": "number|null",
      "carbohydrate_g": "number|null",
      "sugar_g": "number|null",
      "fiber_g": "number|null",
      "calcium_mg": "number|null",
      "iron_mg": "number|null",
      "phosphorus_mg": "number|null",
      "potassium_mg": "number|null",
      "sodium_mg": "number|null",
      "cholesterol_mg": "number|null",
      "saturated_fat_g": "number|null",
      "trans_fat_g": "number|null",
      "source": "object|null"
    },
    "missing_sections": ["string"]
  }
}
```

## 2. `새싹` 실제 예시

### 입력

```json
{
  "ingredient": "새싹",
  "sections": ["seasonality", "storage", "prep", "washing", "freshness", "nutrition"]
}
```

### 출력 (`structuredContent`)

```json
{
  "status": "ok",
  "requested_sections": ["seasonality", "storage", "prep", "washing", "freshness", "nutrition"],
  "matched_by": "name",
  "ingredient": {
    "ingredient_id": "ingredient_0196",
    "name": "새싹",
    "display_name": "새싹",
    "classification": "채소류",
    "data_source_type": "영양+가이드",
    "aliases": [{"alias_id": "alias_0428", "name": "어린잎"}],
    "category": {
      "major": {"major_id": "major_0002", "name": "농산물"},
      "middle": {"middle_id": "middle_0011", "name": "채소류"}
    }
  },
  "seasonality": {
    "status": "available",
    "months": [3],
    "source": {"name": "농촌진흥청 국립농업과학원/NICS 이달의 식재료", "url": "https://nics.go.kr/food/kfi/foodMonth/list"}
  },
  "guides": {
    "storage": {
      "label": "보관방법",
      "status": "available",
      "guide_id": "guide_0232",
      "content": "사용하고 남은 새싹채소는 비닐 팩에 담아 냉장 보관한다. 이때 입김을 불어 넣어 팽팽하게 묶으면 새싹채소가 눌려 짓무르는 것을 방지할 뿐만 아니라 입김에 포함된 이산화탄소가 채소의 변질을 늦춰준다.",
      "source": {"source_id": "source_0077", "name": "국립식량과학원 이달의 식재료", "url": "https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=34&menuId=PS03599"}
    },
    "prep": {
      "label": "손질방법",
      "status": "available",
      "guide_id": "guide_0233",
      "content": "새싹채소는 발아 후 1주일 안에 수확하며, 노지에서 생산하지 않아 농약을 사용하지 않고 재배한다. 따라서 특별한 세척법 없이 간단하게 씻으면 되지만 잎 전체가 여리므로 주의한다. 큰 용기에 물을 받아 살살 흔들어 씻고, 세척 후에는 채반에 받쳐 물기를 털어낸다.",
      "source": {"source_id": "source_0077", "name": "국립식량과학원 이달의 식재료", "url": "https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=34&menuId=PS03599"}
    },
    "washing": {
      "label": "세척방법",
      "status": "available",
      "guide_id": "guide_0234",
      "content": "흙이나 이물질을 제거한 뒤 물에 잠시 담갔다가 흐르는 물에 여러 번 헹군다. 잎이 겹쳐 있거나 주름진 부분은 잔류물이 남기 쉬우므로 펼쳐서 씻는다.",
      "source": {"source_id": "source_0015", "name": "식품의약품안전처/식생활안전관리원 잔류농약 세척법", "url": "https://www.foodsafetykorea.go.kr/portal/board/boardDetail.do?bbs_no=bbs001&menu_grp=MENU_NEW01&menu_no=3120&ntctxt_no=1100621"}
    },
    "freshness": {
      "label": "신선도 확인법",
      "status": "available",
      "guide_id": "guide_0235",
      "content": "새싹채소는 어린순이 부드럽고 맛있다. 길이가 5cm를 넘지 않는 것이 좋으며, 누렇게 변색한 것은 피한다. 줄기나 잎 부분에 검은색 반점이 생긴 것은 썩었거나 곰팡이가 핀 것이므로 구입하지 않는 것이 좋다. 새싹 종류별로 고유의 색을 띠는 것이 신선한 것으로, 브로콜리 싹과 다채 싹은 초록색을 띠고 있으며, 적양배추 싹은 붉고, 배추 싹은 노란빛을 띤다.",
      "source": {"source_id": "source_0077", "name": "국립식량과학원 이달의 식재료", "url": "https://www.nics.go.kr/food/kfi/foodMonth/view?fd_se=286&fd_snn=34&menuId=PS03599"}
    }
  },
  "nutrition": {
    "status": "available",
    "nutrition_id": "nutrition_0196",
    "representative_food_name": "비타민채(다채)",
    "standard_amount": "100g",
    "energy_kcal": 15,
    "water_g": 94.5,
    "protein_g": 2.26,
    "fat_g": 0.5,
    "ash_g": 1.27,
    "carbohydrate_g": 1.44,
    "sugar_g": 0,
    "fiber_g": 0.9,
    "calcium_mg": 142,
    "iron_mg": 9.74,
    "phosphorus_mg": 53,
    "potassium_mg": 391,
    "sodium_mg": 31,
    "cholesterol_mg": 0,
    "saturated_fat_g": 0,
    "trans_fat_g": 0.03,
    "source": {"source_id": "source_0039", "name": "농진청(’20)", "url": null}
  },
  "missing_sections": []
}
```

## 3. 핵심 규칙

- `status`: `ok`, `partial`, `not_found`
- `matched_by`: `name`, `display_name`, `alias`; 미검색은 `null`
- 요청하지 않은 항목은 출력에서 생략
- 가이드 누락은 `status: "missing"`, 나머지는 `null`
- 일부 영양소가 `null`이어도 Nutrition 노드가 있으면 `available`
- 흐름: `Supervisor Agent → Guide Agent → MCP → Guide Agent 답변`
