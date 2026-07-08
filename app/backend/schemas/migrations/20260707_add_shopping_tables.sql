BEGIN;

CREATE TABLE IF NOT EXISTS shopping_lists (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    recipe_id BIGINT REFERENCES recipes(id) ON DELETE SET NULL,
    source VARCHAR(30) NOT NULL DEFAULT 'recipe',
    status VARCHAR(30) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_shopping_lists_source CHECK (source IN ('recipe', 'manual')),
    CONSTRAINT ck_shopping_lists_status CHECK (status IN ('active', 'completed'))
);

CREATE TABLE IF NOT EXISTS shopping_list_items (
    id BIGSERIAL PRIMARY KEY,
    shopping_list_id BIGINT NOT NULL REFERENCES shopping_lists(id) ON DELETE CASCADE,
    ingredient_id BIGINT REFERENCES ingredients(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    required_quantity NUMERIC(10, 2),
    unit VARCHAR(30),
    provider VARCHAR(30) NOT NULL DEFAULT 'naver',
    product_id VARCHAR(100),
    product_name VARCHAR(500),
    product_link TEXT,
    product_image VARCHAR(1000),
    price INTEGER,
    mall_name VARCHAR(255),
    is_checked BOOLEAN NOT NULL DEFAULT TRUE,
    is_purchased BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE shopping_lists IS '사용자 장보기 목록';
COMMENT ON COLUMN shopping_lists.user_id IS '사용자 ID';
COMMENT ON COLUMN shopping_lists.recipe_id IS '기준 레시피 ID';
COMMENT ON COLUMN shopping_lists.source IS '생성 출처(recipe/manual)';
COMMENT ON COLUMN shopping_lists.status IS '진행 상태(active/completed)';

COMMENT ON TABLE shopping_list_items IS '장보기 목록 재료 및 외부 상품 링크 스냅샷';
COMMENT ON COLUMN shopping_list_items.shopping_list_id IS '장보기 목록 ID';
COMMENT ON COLUMN shopping_list_items.ingredient_id IS '식재료 마스터 ID';
COMMENT ON COLUMN shopping_list_items.name IS '장보기 재료명/검색어';
COMMENT ON COLUMN shopping_list_items.required_quantity IS '필요 수량';
COMMENT ON COLUMN shopping_list_items.unit IS '필요 수량 단위';
COMMENT ON COLUMN shopping_list_items.provider IS '쇼핑 provider';
COMMENT ON COLUMN shopping_list_items.product_id IS '외부 상품 ID';
COMMENT ON COLUMN shopping_list_items.product_name IS '외부 상품명';
COMMENT ON COLUMN shopping_list_items.product_link IS '구매 링크';
COMMENT ON COLUMN shopping_list_items.product_image IS '상품 이미지 URL';
COMMENT ON COLUMN shopping_list_items.price IS '검색 시점 가격';
COMMENT ON COLUMN shopping_list_items.mall_name IS '판매몰명';
COMMENT ON COLUMN shopping_list_items.is_checked IS '구매 대상 선택 여부';
COMMENT ON COLUMN shopping_list_items.is_purchased IS '구매 완료 여부';

CREATE INDEX IF NOT EXISTS idx_shopping_lists_user_id ON shopping_lists(user_id);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_recipe_id ON shopping_lists(recipe_id);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_status ON shopping_lists(status);
CREATE INDEX IF NOT EXISTS idx_shopping_lists_created_at ON shopping_lists(created_at);
CREATE INDEX IF NOT EXISTS idx_shopping_list_items_list_id ON shopping_list_items(shopping_list_id);
CREATE INDEX IF NOT EXISTS idx_shopping_list_items_ingredient_id ON shopping_list_items(ingredient_id);
CREATE INDEX IF NOT EXISTS idx_shopping_list_items_provider ON shopping_list_items(provider);
CREATE INDEX IF NOT EXISTS idx_shopping_list_items_checked ON shopping_list_items(is_checked);
CREATE INDEX IF NOT EXISTS idx_shopping_list_items_purchased ON shopping_list_items(is_purchased);

COMMIT;
