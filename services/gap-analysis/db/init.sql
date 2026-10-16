-- gap_db belongs to the gap-analysis service, and nothing else touches it.
-- Postgres runs this file once, the first time the gap-db container starts with an empty volume.
-- Nutrients are referred to by their short key (like 'magnesium'), the same as in nutrient-calc.

CREATE TABLE user_profiles (
    user_id         TEXT PRIMARY KEY,             -- the user's Google ID (the "sub" in their login token)
    sex             TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    age_years       SMALLINT NOT NULL CHECK (age_years BETWEEN 14 AND 120),
    weight_kg       NUMERIC(5, 1) NOT NULL CHECK (weight_kg > 0),
    height_cm       NUMERIC(5, 1) NOT NULL CHECK (height_cm > 0),
    activity_level  TEXT NOT NULL CHECK (activity_level IN
                        ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    goal            TEXT NOT NULL CHECK (goal IN ('cut', 'maintain', 'bulk')),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Each user's daily targets. Worked out again whenever they change their profile.
CREATE TABLE targets (
    user_id        TEXT   NOT NULL REFERENCES user_profiles(user_id) ON DELETE CASCADE,
    nutrient_key   TEXT   NOT NULL,
    target_amount  NUMERIC(12, 4),          -- NULL if we don't have a reference value yet
    upper_limit    NUMERIC(12, 4),          -- NULL if there's no upper limit
    unit           TEXT   NOT NULL,
    source         TEXT   NOT NULL,         -- where the number came from, e.g. 'NHMRC NRV' or 'calculated (Mifflin-St Jeor)'
    PRIMARY KEY (user_id, nutrient_key)
);

-- Recommended intakes by age and sex. Filled in by the data loader from etl/reference_intakes.csv.
-- Every value has to be checked against the official NHMRC tables. `verified` stays false until then.
CREATE TABLE reference_intakes (
    id            SERIAL PRIMARY KEY,
    nutrient_key  TEXT NOT NULL,
    sex           TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    age_min       SMALLINT NOT NULL,
    age_max       SMALLINT NOT NULL,
    intake_type   TEXT CHECK (intake_type IN ('RDI', 'AI')),
    rni_or_ai     NUMERIC(12, 4),            -- NULL means it hasn't been filled in yet
    upper_limit   NUMERIC(12, 4),            -- NULL means there's no upper limit, or it hasn't been filled in yet
    unit          TEXT NOT NULL,
    source        TEXT NOT NULL,
    verified      BOOLEAN NOT NULL DEFAULT false,
    UNIQUE (nutrient_key, sex, age_min, age_max)
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
