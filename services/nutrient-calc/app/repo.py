"""All the SQL for nutrient_db is in this file. Each function is handed an open connection to use."""
from datetime import date

from psycopg import Connection


def get_nutrients(conn: Connection) -> list[dict]:
    return conn.execute(
        "SELECT id, key, name, unit, category FROM nutrient ORDER BY sort_order"
    ).fetchall()


def get_food_nutrients(conn: Connection, fdc_ids: list[int]) -> dict[int, dict[int, float]]:
    """Get the nutrient values for some foods, as {fdc_id: {nutrient_id: amount per 100 g}}.

    A food we have no data for won't appear at all. A nutrient without a value won't appear
    either, which means we don't know it.
    """
    rows = conn.execute(
        "SELECT fdc_id, nutrient_id, amount_per_100g FROM food_nutrient WHERE fdc_id = ANY(%s)",
        (list(fdc_ids),),
    ).fetchall()
    result: dict[int, dict[int, float]] = {}
    for row in rows:
        result.setdefault(row["fdc_id"], {})[row["nutrient_id"]] = float(row["amount_per_100g"])
    return result


def upsert_daily_totals(conn: Connection, user_id: str, day: date, totals: dict[int, dict], item_count: int):
    """Save the totals for one user and day, one row per nutrient, replacing what was there before.

    We use an "upsert" (insert, or update if the row already exists) rather than deleting and
    re-inserting. That way two updates for the same day arriving together can't trip over each other.
    """
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO daily_totals (user_id, date, nutrient_id, amount, is_complete, coverage_pct,
                                      item_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (user_id, date, nutrient_id) DO UPDATE
               SET amount = EXCLUDED.amount,
                   is_complete = EXCLUDED.is_complete,
                   coverage_pct = EXCLUDED.coverage_pct,
                   item_count = EXCLUDED.item_count,
                   updated_at = now()
            """,
            [
                (user_id, day, nutrient_id, t["amount"], t["is_complete"], t["coverage_pct"], item_count)
                for nutrient_id, t in totals.items()
            ],
        )


def delete_daily_totals(conn: Connection, user_id: str, day: date):
    """Nothing is logged for that day any more, so remove its rows.

    An empty day means "no data", not "ate nothing".
    """
    conn.execute("DELETE FROM daily_totals WHERE user_id = %s AND date = %s", (user_id, day))


def get_daily_totals(conn: Connection, user_id: str, start: date, end: date) -> list[dict]:
    """Get every day from start to end that has food logged.

    Each day comes back as {"date", "item_count", "nutrients": {key: {...}}}.
    """
    rows = conn.execute(
        """
        SELECT d.date, d.item_count, n.key, d.amount, d.is_complete, d.coverage_pct
          FROM daily_totals d
          JOIN nutrient n ON n.id = d.nutrient_id
         WHERE d.user_id = %s AND d.date BETWEEN %s AND %s
         ORDER BY d.date, n.sort_order
        """,
        (user_id, start, end),
    ).fetchall()

    days: dict[date, dict] = {}
    for row in rows:
        day = days.setdefault(row["date"], {"date": row["date"], "item_count": row["item_count"], "nutrients": {}})
        day["nutrients"][row["key"]] = {
            "amount": None if row["amount"] is None else float(row["amount"]),
            "is_complete": row["is_complete"],
            "coverage_pct": float(row["coverage_pct"]),
        }
    return list(days.values())
