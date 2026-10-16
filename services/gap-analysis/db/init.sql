-- gap_db belongs to the gap-analysis service, and nothing else touches it.
-- Postgres runs this file once, the first time the gap-db container starts with an empty volume.
-- Nutrients are referred to by their short key (like 'magnesium'), the same as in nutrient-calc.

CREATE TABLE user_profiles (
    user_id          TEXT PRIMARY KEY,           -- the user's Google ID (the "sub" in their login token)
    sex              TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    date_of_birth    DATE NOT NULL,              -- so the age (and the targets) move on with birthdays
    height_cm        NUMERIC(5, 1) NOT NULL CHECK (height_cm > 0),
    weight_kg        NUMERIC(5, 1) NOT NULL CHECK (weight_kg > 0),
    -- what a normal day looks like (see LIFESTYLES in app/targets.py), and how often they exercise
    lifestyle        TEXT NOT NULL CHECK (lifestyle IN
                         ('mostly_seated', 'seated_some_walking', 'standing_walking', 'heavy_work')),
    exercise_sessions_per_week SMALLINT NOT NULL CHECK (exercise_sessions_per_week BETWEEN 0 AND 14),
    goal             TEXT NOT NULL CHECK (goal IN ('lose', 'maintain', 'gain')),
    diet             TEXT NOT NULL CHECK (diet IN ('omnivore', 'vegetarian', 'vegan')),
    -- Pregnancy: the due date tells us the trimester on any day. NULL if not pregnant.
    due_date         DATE,
    pre_pregnancy_weight_kg NUMERIC(5, 1) CHECK (pre_pregnancy_weight_kg > 0),
    breastfeeding    BOOLEAN NOT NULL DEFAULT false,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- There's no targets table: targets are worked out from the profile each time they're needed,
-- because they change with age and with each stage of a pregnancy.

-- Recommended intakes by age, sex and life stage (none, pregnant or breastfeeding), from
-- etl/reference_intakes.csv. Every value has been checked against the official NHMRC tables.
CREATE TABLE reference_intakes (
    id            SERIAL PRIMARY KEY,
    nutrient_key  TEXT NOT NULL,
    sex           TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    age_min       SMALLINT NOT NULL,
    age_max       SMALLINT NOT NULL,
    life_stage    TEXT NOT NULL DEFAULT 'none' CHECK (life_stage IN ('none', 'pregnant', 'breastfeeding')),
    intake_type   TEXT CHECK (intake_type IN ('RDI', 'AI')),
    rni_or_ai     NUMERIC(12, 4),            -- NULL when there's only a limit (sodium)
    upper_limit   NUMERIC(12, 4),            -- NULL means there's no upper limit for food
    sdt           NUMERIC(12, 4),            -- NHMRC's "suggested dietary target" for long-term health, if any
    unit          TEXT NOT NULL,
    source        TEXT NOT NULL,
    verified      BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (nutrient_key, sex, age_min, age_max, life_stage)
);

-- The most recent gap check for each user, time window (7 or 14 days) and nutrient.
CREATE TABLE gap_results (
    user_id         TEXT     NOT NULL,
    window_days     SMALLINT NOT NULL CHECK (window_days IN (7, 14)),
    nutrient_key    TEXT     NOT NULL,
    avg_intake      NUMERIC(14, 4),          -- average over the days that actually have data
    target_amount   NUMERIC(12, 4),
    pct_of_target   NUMERIC(8, 2),
    days_met        SMALLINT NOT NULL,
    days_with_data  SMALLINT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('gap', 'ok', 'excess', 'unknown')),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, window_days, nutrient_key)
);
