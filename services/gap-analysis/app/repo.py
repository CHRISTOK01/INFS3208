"""All the SQL for gap_db is in this file. Each function is handed an open connection to use."""
from psycopg import Connection

PROFILE_FIELDS = ["sex", "date_of_birth", "height_cm", "weight_kg", "lifestyle", "exercise_sessions_per_week",
                  "goal", "diet", "due_date", "pre_pregnancy_weight_kg", "breastfeeding"]
PROFILE_COLUMNS = "user_id, " + ", ".join(PROFILE_FIELDS) + ", updated_at"


def numbers(row: dict | None, columns: list[str]) -> dict | None:
    """NUMERIC columns come back as Decimal. Turn them into ordinary numbers for the maths."""
    if row is not None:
        for column in columns:
            if row.get(column) is not None:
                row[column] = float(row[column])
    return row


# ---------------------------------------------------------------- profiles

def save_profile(conn: Connection, user_id: str, p: dict) -> dict:
    """Add the profile, or replace it if this user already has one."""
    updates = ", ".join(f"{f} = EXCLUDED.{f}" for f in PROFILE_FIELDS)
    row = conn.execute(
        f"""
        INSERT INTO user_profiles (user_id, {", ".join(PROFILE_FIELDS)})
        VALUES (%s, {", ".join(["%s"] * len(PROFILE_FIELDS))})
        ON CONFLICT (user_id) DO UPDATE SET {updates}, updated_at = now()
        RETURNING {PROFILE_COLUMNS}
        """,
        [user_id] + [p[f] for f in PROFILE_FIELDS],
    ).fetchone()
    return numbers(row, ["height_cm", "weight_kg", "pre_pregnancy_weight_kg"])


def get_profile(conn: Connection, user_id: str) -> dict | None:
    row = conn.execute(f"SELECT {PROFILE_COLUMNS} FROM user_profiles WHERE user_id = %s", (user_id,)).fetchone()
    return numbers(row, ["height_cm", "weight_kg", "pre_pregnancy_weight_kg"])


# ---------------------------------------------------------------- reference intakes

def get_reference_intakes(conn: Connection) -> list[dict]:
    """Every NHMRC row (a few hundred). targets.build_targets picks out the ones for each person."""
    return conn.execute(
        "SELECT nutrient_key, sex, age_min, age_max, life_stage, intake_type, rni_or_ai, upper_limit, sdt, unit "
        "FROM reference_intakes"
    ).fetchall()


# ---------------------------------------------------------------- gap results

def save_gap_results(conn: Connection, user_id: str, windows: list[dict]):
    """Keep the latest results, so we can still show something if nutrient-calc is down later."""
    conn.execute("DELETE FROM gap_results WHERE user_id = %s", (user_id,))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO gap_results (user_id, window_days, nutrient_key, avg_intake, target_amount,
                                     pct_of_target, days_met, days_with_data, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (user_id, w["window_days"], n["nutrient_key"], n["avg_intake"], n["target_amount"],
                 n["pct_of_target"], n["days_met"], n["days_with_data"], n["status"])
                for w in windows for n in w["nutrients"]
            ],
        )


def get_gap_results(conn: Connection, user_id: str) -> list[dict]:
    return conn.execute(
        """
        SELECT window_days, nutrient_key, avg_intake, target_amount, pct_of_target, days_met,
               days_with_data, status, computed_at
          FROM gap_results
         WHERE user_id = %s
         ORDER BY window_days, nutrient_key
        """,
        (user_id,),
    ).fetchall()
