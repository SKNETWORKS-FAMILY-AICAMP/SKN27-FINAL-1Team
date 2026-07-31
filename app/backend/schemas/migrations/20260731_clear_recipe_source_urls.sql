UPDATE recipes
SET source_url = NULL
WHERE source_url IS NOT NULL;
