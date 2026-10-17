"""Reading foods from recommender_db."""
from psycopg import Connection


def candidate_foods(conn: Connection, nutrient_keys: list[str]) -> list[dict]:
    """Everyday Australian foods with a value for at least one of these nutrients.

    Only AUSNUT foods have a dietary guidelines code, and we only want the ones FSANZ doesn't call
    "discretionary". The finer choosing happens in rules.py. Protein, carbs, fat and fibre are kept
    in their own columns, so we add them to the nutrients map here (jsonb_strip_nulls leaves out any
    that are unknown). That's about 2,500 rows at most, which is quick.
    """
    return conn.execute(
        """
        SELECT * FROM (
            SELECT fdc_id, name, category, adg_code, discretionary, prep_state,
                   kcal_per_100g::float AS kcal,
                   nutrients || jsonb_strip_nulls(jsonb_build_object(
                       'protein', protein_g::float, 'carbs', carbs_g::float,
                       'fat', fat_g::float, 'fibre', fibre_g::float)) AS nutrients
            FROM foods
            WHERE adg_code IS NOT NULL AND discretionary = false
        ) everyday
        WHERE nutrients ?| %(keys)s
        """,
        {"keys": nutrient_keys},
    ).fetchall()
