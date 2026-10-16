-- nutrient_db belongs to the nutrient-calc service, and nothing else touches it.
-- Postgres runs this file once, the first time the nutrient-db container starts with an empty volume.

-- The nutrients MacroScope keeps track of. The ids and keys here are our own, not USDA's.
-- The `key` (like 'magnesium') is how the services refer to a nutrient when they talk to each other.
-- When the data is loaded, each USDA nutrient is matched to one of these rows by its name and
-- unit in nutrient.csv, and every amount is converted into the unit listed here. Australian (AUSNUT)
-- foods are matched by their column name instead.
CREATE TABLE nutrient (
    id          SMALLINT PRIMARY KEY,
    key         TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    unit        TEXT NOT NULL CHECK (unit IN ('kcal', 'g', 'mg', 'ug')),
    category    TEXT NOT NULL CHECK (category IN ('macro', 'mineral', 'vitamin', 'other')),
    sort_order  SMALLINT NOT NULL
);

INSERT INTO nutrient (id, key, name, unit, category, sort_order) VALUES
    -- macros
    ( 1, 'energy',         'Energy',             'kcal', 'macro',    1),
    ( 2, 'protein',        'Protein',            'g',    'macro',    2),
    ( 3, 'carbs',          'Carbohydrate',       'g',    'macro',    3),
    ( 4, 'fat',            'Fat',                'g',    'macro',    4),
    ( 5, 'fibre',          'Dietary fibre',      'g',    'macro',    5),
    -- minerals
    (10, 'calcium',        'Calcium',            'mg',   'mineral', 10),
    (11, 'iron',           'Iron',               'mg',   'mineral', 11),
    (12, 'magnesium',      'Magnesium',          'mg',   'mineral', 12),
    (13, 'phosphorus',     'Phosphorus',         'mg',   'mineral', 13),
    (14, 'potassium',      'Potassium',          'mg',   'mineral', 14),
    (15, 'sodium',         'Sodium',             'mg',   'mineral', 15),
    (16, 'zinc',           'Zinc',               'mg',   'mineral', 16),
    (17, 'copper',         'Copper',             'mg',   'mineral', 17),
    (18, 'manganese',      'Manganese',          'mg',   'mineral', 18),
    (19, 'selenium',       'Selenium',           'ug',   'mineral', 19),
    -- Iodine: every Australian (AUSNUT) food has it, but USDA has it for hardly any of its foods
    (20, 'iodine',         'Iodine',             'ug',   'mineral', 20),
    -- vitamins
    (30, 'vitamin_a',      'Vitamin A (RAE)',    'ug',   'vitamin', 30),
    (31, 'vitamin_c',      'Vitamin C',          'mg',   'vitamin', 31),
    (32, 'vitamin_d',      'Vitamin D',          'ug',   'vitamin', 32),
    (33, 'vitamin_e',      'Vitamin E',          'mg',   'vitamin', 33),
    (34, 'vitamin_k',      'Vitamin K',          'ug',   'vitamin', 34),
    (35, 'thiamin',        'Thiamin (B1)',       'mg',   'vitamin', 35),
    (36, 'riboflavin',     'Riboflavin (B2)',    'mg',   'vitamin', 36),
    (37, 'niacin',         'Niacin (B3)',        'mg',   'vitamin', 37),
    (38, 'pantothenic',    'Pantothenic acid',   'mg',   'vitamin', 38),
    (39, 'vitamin_b6',     'Vitamin B6',         'mg',   'vitamin', 39),
    (40, 'folate',         'Folate (DFE)',       'ug',   'vitamin', 40),
    (41, 'vitamin_b12',    'Vitamin B12',        'ug',   'vitamin', 41),
    (42, 'choline',        'Choline',            'mg',   'vitamin', 42),
    -- other things worth watching, mainly so we can warn about having too much
    (50, 'saturated_fat',  'Saturated fat',      'g',    'other',   50),
    (51, 'sugars',         'Total sugars',       'g',    'other',   51),
    -- these four only come from the Australian data (USDA has caffeine and alcohol too)
    (52, 'free_sugars',    'Free sugars',        'g',    'other',   52),
    (53, 'omega3_lc',      'Long chain omega-3', 'mg',   'other',   53),
    (54, 'caffeine',       'Caffeine',           'mg',   'other',   54),
    (55, 'alcohol',        'Alcohol',            'g',    'other',   55);

-- How much of each nutrient is in 100 g of each food. Filled in by the data loader using COPY.
-- If a food has no row for a nutrient, that means we DON'T KNOW (it was never measured).
-- We never put in 0 for an unknown, because then people could be wrongly told they're low on it.
-- The primary key also works as the index for looking up (fdc_id, nutrient_id).
CREATE TABLE food_nutrient (
    fdc_id           INTEGER  NOT NULL,
    nutrient_id      SMALLINT NOT NULL REFERENCES nutrient(id),
    amount_per_100g  NUMERIC(12, 4) NOT NULL CHECK (amount_per_100g >= 0),
    PRIMARY KEY (fdc_id, nutrient_id)
);

-- Each user's totals for each day. Recalculated every time meal-logging sends us that day's food.
--   amount       the total of the values we know (NULL if we didn't know any of them)
--   is_complete  true only if every food logged that day had a value for this nutrient
--   coverage_pct how much of the day's food, by weight, had a value for this nutrient (0 to 100).
--                Packaged foods often leave nutrients off the label, so this tells gap-analysis
--                whether an incomplete total is nearly right (say 95%) or could be far too low.
-- A day with nothing logged has no rows at all, which means "no data", not "ate nothing".
CREATE TABLE daily_totals (
    user_id      TEXT     NOT NULL,   -- the user's Google ID (the "sub" in their login token)
    date         DATE     NOT NULL,
    nutrient_id  SMALLINT NOT NULL REFERENCES nutrient(id),
    amount       NUMERIC(14, 4),
    is_complete  BOOLEAN  NOT NULL,
    coverage_pct NUMERIC(4, 1) NOT NULL CHECK (coverage_pct BETWEEN 0 AND 100),
    item_count   INTEGER  NOT NULL,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, date, nutrient_id)
);
