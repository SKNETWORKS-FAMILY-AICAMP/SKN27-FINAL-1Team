ALTER TABLE shopping_list_items
    ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN shopping_list_items.is_deleted IS '사용자 삭제 여부';
