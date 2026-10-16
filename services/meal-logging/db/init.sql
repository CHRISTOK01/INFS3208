-- meal_db belongs to the meal-logging service, and nothing else touches it.
-- Postgres runs this file once, the first time the meal-db container starts with an empty volume.
-- There's no users table: people sign up and log in through Google, and we store their meals
-- under their Google ID (the user_id columns below).

-- pg_trgm lets Postgres match parts of words quickly, so searching "chick" finds "chicken" fast.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- The list of foods people can search for (filled in by the data loader).
-- The nutrient values themselves are in nutrient_db. The two are matched up by fdc_id, which is the
-- USDA FoodData Central ID, or the 8-digit AUSNUT survey ID for Australian foods.
CREATE TABLE food_catalogue (
    fdc_id           INTEGER PRIMARY KEY,
    name             TEXT NOT NULL,
    data_type        TEXT NOT NULL CHECK (data_type IN
                         ('ausnut_food', 'foundation_food', 'sr_legacy_food', 'survey_fndds_food', 'branded_food')),
    -- Search order: 1 = Australian (AUSNUT), 2 = Foundation, 3 = SR Legacy, 4 = FNDDS, 5 = Branded
    -- (lower numbers come first)
    search_rank      SMALLINT NOT NULL,
    category         TEXT,
    barcode          TEXT,
    -- 'raw' or 'cooked' if the food's name says so, otherwise NULL
    prep_state       TEXT CHECK (prep_state IN ('raw', 'cooked')),
    -- true means "complete micronutrient data"; false means "label data only"
    has_full_micros  BOOLEAN NOT NULL DEFAULT false
);
CREATE INDEX food_catalogue_name_trgm ON food_catalogue USING GIN (name gin_trgm_ops);
-- Barcodes are stored the way USDA gives them, which is sometimes with extra zeros in front
-- (e.g. 0000020048556). A scanner might give 20048556. So we look them up with the leading
-- zeros removed, and this index makes that lookup fast.
CREATE INDEX food_catalogue_barcode ON food_catalogue (ltrim(barcode, '0')) WHERE barcode IS NOT NULL;

-- Everyday measures and what they weigh, e.g. "1 cup, chopped" = 128 g
CREATE TABLE food_portion (
    id           BIGSERIAL PRIMARY KEY,
    fdc_id       INTEGER NOT NULL REFERENCES food_catalogue(fdc_id) ON DELETE CASCADE,
    amount       NUMERIC(10, 3),
    description  TEXT NOT NULL,
    gram_weight  NUMERIC(10, 3) NOT NULL CHECK (gram_weight > 0)
);
CREATE INDEX food_portion_fdc ON food_portion (fdc_id);

CREATE TABLE meals (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,   -- the user's Google ID (the "sub" in their login token)
    meal_date   DATE NOT NULL,
    meal_type   TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX meals_user_date ON meals (user_id, meal_date);

-- We always store how many grams were eaten. Everything else is worked out from that.
-- calc_status stays 'pending' until nutrient-calc confirms it has counted this item in the day's totals.
CREATE TABLE meal_items (
    id            BIGSERIAL PRIMARY KEY,
    meal_id       BIGINT  NOT NULL REFERENCES meals(id) ON DELETE CASCADE,
    fdc_id        INTEGER NOT NULL REFERENCES food_catalogue(fdc_id),
    grams         NUMERIC(8, 2) NOT NULL CHECK (grams > 0),
    state         TEXT CHECK (state IN ('raw', 'cooked')),
    portion_desc  TEXT,
    calc_status   TEXT NOT NULL DEFAULT 'pending' CHECK (calc_status IN ('pending', 'done'))
);
CREATE INDEX meal_items_meal    ON meal_items (meal_id);
CREATE INDEX meal_items_pending ON meal_items (calc_status) WHERE calc_status = 'pending';

CREATE TABLE saved_recipes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    name        TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX saved_recipes_user ON saved_recipes (user_id);

CREATE TABLE saved_recipe_items (
    id         BIGSERIAL PRIMARY KEY,
    recipe_id  BIGINT  NOT NULL REFERENCES saved_recipes(id) ON DELETE CASCADE,
    fdc_id     INTEGER NOT NULL REFERENCES food_catalogue(fdc_id),
    grams      NUMERIC(8, 2) NOT NULL CHECK (grams > 0),
    state      TEXT CHECK (state IN ('raw', 'cooked'))
);
CREATE INDEX saved_recipe_items_recipe ON saved_recipe_items (recipe_id);

-- Days whose food has changed but haven't been sent to nutrient-calc yet.
-- Every time a meal is added or deleted, its day goes on this list in the same transaction.
-- Once nutrient-calc has the new totals, the day comes off the list. If nutrient-calc is down,
-- the day just stays here until POST /api/meals/meals/recalculate-pending sends it.
-- (We need this as well as calc_status: if you delete the only meal on a day, there are no
-- items left to mark as pending, but nutrient-calc still has the old totals.)
CREATE TABLE pending_days (
    user_id    TEXT NOT NULL,
    meal_date  DATE NOT NULL,
    PRIMARY KEY (user_id, meal_date)
);
