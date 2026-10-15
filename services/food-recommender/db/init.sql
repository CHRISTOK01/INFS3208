-- recommender_db belongs to the food-recommender service, and nothing else touches it.
-- Postgres runs this file once, the first time the recommender-db container starts with an empty volume.
-- It holds its own copy of the food data, laid out to make ranking easy: one row per food, with all
-- the vitamins and minerals in a single JSONB column. It's matched to the other services by fdc_id.

CREATE TABLE foods (
    fdc_id             INTEGER PRIMARY KEY,
    name               TEXT NOT NULL,
    category           TEXT,
    data_type          TEXT NOT NULL,
    kcal_per_100g      NUMERIC(8, 2),
    protein_g          NUMERIC(8, 2),
    carbs_g            NUMERIC(8, 2),
    fat_g              NUMERIC(8, 2),
    fibre_g            NUMERIC(8, 2),
    typical_serving_g  NUMERIC(8, 2) NOT NULL DEFAULT 100,
    has_full_micros    BOOLEAN NOT NULL DEFAULT false,
    -- Looks like {"magnesium": 79.0, "iron": 2.7, ...}: the amount per 100 g, in the same units
    -- nutrient-calc uses. If we don't know a nutrient, it's just left out of the map (never 0).
    nutrients          JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Lets us quickly find foods that have a value for a nutrient, e.g. WHERE nutrients ? 'magnesium'
CREATE INDEX foods_nutrients_gin ON foods USING GIN (nutrients);
-- Lets us quickly narrow the list down by calories before ranking
CREATE INDEX foods_kcal ON foods (kcal_per_100g);
