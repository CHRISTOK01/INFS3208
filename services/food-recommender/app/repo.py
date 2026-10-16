"""Reading foods from recommender_db."""
from psycopg import Connection


def candidate_foods(conn: Connection, nutrient_keys: list[str]) -> list[dict]:
    """Everyday Australian foods with a value for at least one of these nutrients.

    Only AUSNUT foods have a dietary guidelines code, and we only want the ones FSANZ doesn't call
    "discretionary". The finer choosing happens in rules.py. Fibre is kept in its own column, so we
    add it to the nutrients map here. That's about 2,500 rows at most, which is quick.
    """
    return conn.execute(
        """
        SELECT fdc_id, name, category, adg_code, discretionary, prep_state,
               kcal_per_100g::float AS kcal,
               nutrients || CASE WHEN fibre_g IS NULL THEN '{}'::jsonb
                                 ELSE jsonb_build_object('fibre', fibre_g::float) END AS nutrients
        FROM foods
        WHERE adg_code IS NOT NULL
          AND discretionary = false
          AND (nutrients ?| %(keys)s OR ('fibre' = ANY(%(keys)s) AND fibre_g IS NOT NULL))
        """,
        {"keys": nutrient_keys},
    ).fetchall()
