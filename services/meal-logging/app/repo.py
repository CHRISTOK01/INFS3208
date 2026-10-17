"""All the SQL for meal_db is in this file. Each function is handed an open connection to use."""
from datetime import date

from psycopg import Connection

from app.foods import Search, first_of_each_name, like_pattern, main_entry_pattern, starts_with_pattern, word_start_pattern

FOOD_COLUMNS = "fdc_id, name, data_type, category, barcode, prep_state, has_full_micros"


# ---------------------------------------------------------------- foods

def search_foods(conn: Connection, search: Search, limit: int, typed: str) -> list[dict]:
    """Find foods whose name contains every word. `typed` is the whole search as typed.

    The order is:
      0. if a cooking word was typed, names that start with exactly what was typed, so "baked beans"
         finds "Baked beans, canned" even though "baked" is usually a cooking word
      1. foods matching the raw/cooked choice (if there is one)
      2. main entries, where the words (or just the first word) are the whole first part of the
         name: "peanut butter" finds "Peanut butter, smooth", "chicken breast" finds "Chicken,
         breast, ...", and "banana" finds "Banana, cavendish, raw" before "Banana chip"
      3. names that start with the first word, so "milk" finds "Milk, cow" before "Yogurt, whole milk"
      4. Australian foods, then Foundation, SR Legacy, FNDDS and Branded (search_rank 1 to 5)
      5. names with the cooking word that was typed, at the start of a word ("roast" finds
         "roasted", but "boiled" doesn't count "parboiled")
      6. FSANZ's "not further defined" foods, which are its average of the usual kinds of that food
      7. raw foods, when no raw/cooked choice was made, so "banana" finds the fresh fruit first
      8. how closely the name matches what was typed
      9. shorter names, so "Bananas, raw" comes before "Bananas, dehydrated, or banana powder"
    The trigram index on name (see db/init.sql) keeps this to a few milliseconds.

    USDA sometimes lists the same food twice under the same name (different lab samples), so we
    fetch a few extra rows and keep only the first food with each name.
    """
    words = search.words
    conditions = " AND ".join("name ILIKE %s" for _ in words)
    rows = conn.execute(
        f"""
        SELECT {FOOD_COLUMNS}
          FROM food_catalogue
         WHERE {conditions}
         ORDER BY COALESCE(name ~* %s, false) DESC,
                  COALESCE(prep_state = %s, false) DESC,
                  (name ~* %s OR name ~* %s) DESC,
                  name ILIKE %s DESC,
                  search_rank,
                  COALESCE(name ~* %s, false) DESC,
                  name ILIKE '%%, not further defined' DESC,
                  COALESCE(%s::text IS NULL AND prep_state = 'raw', false) DESC,
                  similarity(name, %s) DESC,
                  length(name)
         LIMIT %s
        """,
        [like_pattern(w) for w in words]
        + [main_entry_pattern(search.all_words) if search.cooking_word else None, search.state, main_entry_pattern(words),
           main_entry_pattern(words[:1]), starts_with_pattern(words[0]),
           word_start_pattern(search.cooking_word) if search.cooking_word else None, search.state, typed, limit * 2],
    ).fetchall()
    return first_of_each_name(rows)[:limit]


def get_food_by_barcode(conn: Connection, normalised_code: str) -> dict | None:
    return conn.execute(
        f"SELECT {FOOD_COLUMNS} FROM food_catalogue WHERE ltrim(barcode, '0') = %s LIMIT 1",
        (normalised_code,),
    ).fetchone()


def get_food(conn: Connection, fdc_id: int) -> dict | None:
    return conn.execute(f"SELECT {FOOD_COLUMNS} FROM food_catalogue WHERE fdc_id = %s", (fdc_id,)).fetchone()


def get_foods(conn: Connection, fdc_ids: list[int]) -> dict[int, dict]:
    """Several foods at once, as {fdc_id: food}. Foods that don't exist are just left out."""
    rows = conn.execute(
        f"SELECT {FOOD_COLUMNS} FROM food_catalogue WHERE fdc_id = ANY(%s)", (list(fdc_ids),)
    ).fetchall()
    return {row["fdc_id"]: row for row in rows}


def get_portions(conn: Connection, fdc_id: int) -> list[dict]:
    return conn.execute(
        "SELECT id, description, gram_weight FROM food_portion WHERE fdc_id = %s ORDER BY gram_weight",
        (fdc_id,),
    ).fetchall()


def get_portions_by_id(conn: Connection, portion_ids: list[int]) -> dict[int, dict]:
    rows = conn.execute(
        "SELECT id, fdc_id, description, gram_weight FROM food_portion WHERE id = ANY(%s)",
        (list(portion_ids),),
    ).fetchall()
    return {row["id"]: row for row in rows}


# ---------------------------------------------------------------- meals

def create_meal(conn: Connection, user_id: str, meal_date: date, meal_type: str) -> int:
    return conn.execute(
        "INSERT INTO meals (user_id, meal_date, meal_type) VALUES (%s, %s, %s) RETURNING id",
        (user_id, meal_date, meal_type),
    ).fetchone()["id"]


def add_meal_items(conn: Connection, meal_id: int, items: list[dict]):
    """Add items to a meal. They start as 'pending' until nutrient-calc has counted them."""
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO meal_items (meal_id, fdc_id, grams, state, portion_desc) VALUES (%s, %s, %s, %s, %s)",
            [(meal_id, i["fdc_id"], i["grams"], i["state"], i["portion_desc"]) for i in items],
        )


def get_meal(conn: Connection, user_id: str, meal_id: int) -> dict | None:
    """One meal, but only if it belongs to this user."""
    return conn.execute(
        "SELECT id, meal_date, meal_type, created_at FROM meals WHERE id = %s AND user_id = %s",
        (meal_id, user_id),
    ).fetchone()


def get_meals(conn: Connection, user_id: str, start: date, end: date) -> list[dict]:
    return conn.execute(
        "SELECT id, meal_date, meal_type, created_at FROM meals "
        "WHERE user_id = %s AND meal_date BETWEEN %s AND %s ORDER BY meal_date, created_at",
        (user_id, start, end),
    ).fetchall()


def get_items_for_meals(conn: Connection, meal_ids: list[int]) -> list[dict]:
    """The items in some meals, with each food's name."""
    return conn.execute(
        """
        SELECT i.id, i.meal_id, i.fdc_id, f.name, i.grams, i.state, i.portion_desc, i.calc_status
          FROM meal_items i
          JOIN food_catalogue f ON f.fdc_id = i.fdc_id
         WHERE i.meal_id = ANY(%s)
         ORDER BY i.id
        """,
        (list(meal_ids),),
    ).fetchall()


def delete_meal(conn: Connection, meal_id: int):
    conn.execute("DELETE FROM meals WHERE id = %s", (meal_id,))  # its items go too (ON DELETE CASCADE)


def get_meal_item(conn: Connection, meal_id: int, item_id: int) -> dict | None:
    """One item, but only if it's in that meal."""
    return conn.execute(
        "SELECT id, meal_id, fdc_id, grams, state, portion_desc FROM meal_items WHERE id = %s AND meal_id = %s",
        (item_id, meal_id),
    ).fetchone()


def update_meal_item(conn: Connection, item_id: int, grams: float, portion_desc: str | None):
    """Change how much of a food was eaten. It goes back to 'pending' until nutrient-calc has the
    new day's totals."""
    conn.execute(
        "UPDATE meal_items SET grams = %s, portion_desc = %s, calc_status = 'pending' WHERE id = %s",
        (grams, portion_desc, item_id),
    )


def delete_meal_item(conn: Connection, meal_id: int, item_id: int) -> bool:
    """Returns False if that item isn't in that meal."""
    cur = conn.execute("DELETE FROM meal_items WHERE id = %s AND meal_id = %s", (item_id, meal_id))
    return cur.rowcount == 1


# ---------------------------------------------------------------- keeping nutrient-calc up to date

def lock_day(conn: Connection, user_id: str, day: date):
    """Stop anyone else changing or sending this user's day until our transaction finishes.

    This is a Postgres "advisory lock". It doesn't lock any table; it's just a named lock that
    everyone agrees to take first. Because it lives in the database, it works across every copy
    of meal-logging. Without it, two meals saved at the same moment could each send nutrient-calc
    a day that's missing the other one.
    """
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"day:{user_id}:{day}",))


def mark_day_pending(conn: Connection, user_id: str, day: date):
    conn.execute(
        "INSERT INTO pending_days (user_id, meal_date) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (user_id, day),
    )


def get_day_items(conn: Connection, user_id: str, day: date) -> list[dict]:
    """Everything a user ate on one day, ready to send to nutrient-calc."""
    return conn.execute(
        """
        SELECT i.fdc_id, i.grams
          FROM meal_items i
          JOIN meals m ON m.id = i.meal_id
         WHERE m.user_id = %s AND m.meal_date = %s
        """,
        (user_id, day),
    ).fetchall()


def mark_day_done(conn: Connection, user_id: str, day: date):
    """nutrient-calc has the up-to-date day, so take it off the pending list."""
    conn.execute(
        """
        UPDATE meal_items i SET calc_status = 'done'
          FROM meals m
         WHERE m.id = i.meal_id AND m.user_id = %s AND m.meal_date = %s AND i.calc_status = 'pending'
        """,
        (user_id, day),
    )
    conn.execute("DELETE FROM pending_days WHERE user_id = %s AND meal_date = %s", (user_id, day))


def get_pending_days(conn: Connection, user_id: str | None, limit: int) -> list[dict]:
    """Days still waiting to be sent, oldest first. user_id=None means every user's."""
    return conn.execute(
        "SELECT user_id, meal_date FROM pending_days "
        "WHERE %s::text IS NULL OR user_id = %s ORDER BY meal_date LIMIT %s",
        (user_id, user_id, limit),
    ).fetchall()


# ---------------------------------------------------------------- saved recipes

def create_recipe(conn: Connection, user_id: str, name: str, items: list[dict]) -> int:
    recipe_id = conn.execute(
        "INSERT INTO saved_recipes (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)
    ).fetchone()["id"]
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO saved_recipe_items (recipe_id, fdc_id, grams, state) VALUES (%s, %s, %s, %s)",
            [(recipe_id, i["fdc_id"], i["grams"], i["state"]) for i in items],
        )
    return recipe_id


def get_recipes(conn: Connection, user_id: str) -> list[dict]:
    return conn.execute(
        "SELECT id, name, created_at FROM saved_recipes WHERE user_id = %s ORDER BY name", (user_id,)
    ).fetchall()


def get_recipe(conn: Connection, user_id: str, recipe_id: int) -> dict | None:
    return conn.execute(
        "SELECT id, name, created_at FROM saved_recipes WHERE id = %s AND user_id = %s", (recipe_id, user_id)
    ).fetchone()


def get_items_for_recipes(conn: Connection, recipe_ids: list[int]) -> list[dict]:
    return conn.execute(
        """
        SELECT r.id, r.recipe_id, r.fdc_id, f.name, r.grams, r.state
          FROM saved_recipe_items r
          JOIN food_catalogue f ON f.fdc_id = r.fdc_id
         WHERE r.recipe_id = ANY(%s)
         ORDER BY r.id
        """,
        (list(recipe_ids),),
    ).fetchall()


def delete_recipe(conn: Connection, recipe_id: int):
    conn.execute("DELETE FROM saved_recipes WHERE id = %s", (recipe_id,))
