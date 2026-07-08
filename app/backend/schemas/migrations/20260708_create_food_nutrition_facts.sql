CREATE TABLE IF NOT EXISTS food_nutrition_facts (
    id BIGSERIAL PRIMARY KEY,
    food_code VARCHAR(100),
    food_name VARCHAR(300) NOT NULL,
    representative_name VARCHAR(300),
    major_category VARCHAR(100),
    middle_category VARCHAR(100),
    minor_category VARCHAR(100),
    base_amount VARCHAR(50),
    energy_kcal NUMERIC,
    carbohydrate_g NUMERIC,
    protein_g NUMERIC,
    fat_g NUMERIC,
    sugar_g NUMERIC,
    sodium_mg NUMERIC,
    source_name VARCHAR(200),
    source_ref TEXT,
    reference_year VARCHAR(20),
    source_priority INTEGER DEFAULT 2,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE food_nutrition_facts
    ADD COLUMN IF NOT EXISTS source_priority INTEGER DEFAULT 2;

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_food_name
    ON food_nutrition_facts (food_name);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_representative_name
    ON food_nutrition_facts (representative_name);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_source_priority
    ON food_nutrition_facts (source_priority);
