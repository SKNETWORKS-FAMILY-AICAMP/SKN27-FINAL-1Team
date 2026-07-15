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
    service_major_category VARCHAR(100),
    service_middle_category VARCHAR(100),
    service_minor_category VARCHAR(200),
    service_match_status VARCHAR(50),
    service_match_basis VARCHAR(100),
    service_ingredient_id VARCHAR(50),
    representative_nutrition_score INTEGER,
    is_representative_nutrition BOOLEAN DEFAULT FALSE,
    representative_nutrition_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE food_nutrition_facts
    ADD COLUMN IF NOT EXISTS source_priority INTEGER DEFAULT 2;

ALTER TABLE food_nutrition_facts
    ADD COLUMN IF NOT EXISTS service_major_category VARCHAR(100),
    ADD COLUMN IF NOT EXISTS service_middle_category VARCHAR(100),
    ADD COLUMN IF NOT EXISTS service_minor_category VARCHAR(200),
    ADD COLUMN IF NOT EXISTS service_match_status VARCHAR(50),
    ADD COLUMN IF NOT EXISTS service_match_basis VARCHAR(100),
    ADD COLUMN IF NOT EXISTS service_ingredient_id VARCHAR(50),
    ADD COLUMN IF NOT EXISTS representative_nutrition_score INTEGER,
    ADD COLUMN IF NOT EXISTS is_representative_nutrition BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS representative_nutrition_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_food_name
    ON food_nutrition_facts (food_name);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_representative_name
    ON food_nutrition_facts (representative_name);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_source_priority
    ON food_nutrition_facts (source_priority);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_service_category
    ON food_nutrition_facts (service_major_category, service_middle_category);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_representative_flag
    ON food_nutrition_facts (is_representative_nutrition);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_service_ingredient
    ON food_nutrition_facts (service_ingredient_id);

CREATE INDEX IF NOT EXISTS idx_food_nutrition_facts_ingredient_representative
    ON food_nutrition_facts (service_ingredient_id, is_representative_nutrition, representative_nutrition_score DESC);
