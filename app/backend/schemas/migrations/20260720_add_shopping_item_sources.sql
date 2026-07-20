BEGIN;

ALTER TABLE shopping_list_items
    ADD COLUMN IF NOT EXISTS source_type VARCHAR(30) NOT NULL DEFAULT 'recipe';

ALTER TABLE shopping_list_items
    ADD COLUMN IF NOT EXISTS source_refs JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE shopping_list_items AS item
SET source_type = list.source
FROM shopping_lists AS list
WHERE item.shopping_list_id = list.id
  AND item.source_refs = '[]'::jsonb;

COMMENT ON COLUMN shopping_list_items.source_type IS '장보기 재료 추가 출처(recipe/manual/fridge_restock/chatbot)';
COMMENT ON COLUMN shopping_list_items.source_refs IS '재료를 추가한 레시피 등 출처 참조 목록';

COMMIT;
