"""Load the food data (Australian AUSNUT 2023 first, then USDA) into each service's own database,
then print row counts.

Run it from the project folder (it runs inside a throwaway container, so you don't need
any Python packages installed):

    docker compose run --rm etl                         # load everything (30,000 Branded foods)
    docker compose run --rm etl --branded 5000          # a different number of Branded foods
    docker compose run --rm etl --skip-branded          # no Branded foods at all
    docker compose run --rm etl --replace               # wipe the food data and load it again
    docker compose run --rm etl --counts-only           # just print the row counts

Each service gets only what it needs, matched up by the USDA fdc_id:
    meal_db         food_catalogue, food_portion   (searching foods, portions to grams)
    nutrient_db     food_nutrient                  (nutrients per 100 g)
    recommender_db  foods                          (one row per food, vitamins and minerals in JSONB)
    gap_db          reference_intakes              (from reference_intakes.csv)

Everything is written with Postgres COPY, which sends rows in bulk rather than one INSERT at a time.
"""
import argparse
import csv
import os
import sys
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

import ausnut
import usda

DATA_DIR = Path(os.getenv("USDA_DATA_DIR", Path(__file__).resolve().parent / "data"))
REFERENCE_CSV = Path(__file__).resolve().parent / "reference_intakes.csv"

DB_URLS = {
    "meal_db": os.getenv("MEAL_DB_URL", "postgresql://meal:meal_pw@localhost:5433/meal_db"),
    "nutrient_db": os.getenv("NUTRIENT_DB_URL", "postgresql://nutrient:nutrient_pw@localhost:5434/nutrient_db"),
    "gap_db": os.getenv("GAP_DB_URL", "postgresql://gap:gap_pw@localhost:5435/gap_db"),
    "recommender_db": os.getenv("RECOMMENDER_DB_URL", "postgresql://recommender:recommender_pw@localhost:5436/recommender_db"),
}

# The tables this script fills, per database (used for clearing them and for the row counts)
TABLES = {
    "meal_db": ["food_catalogue", "food_portion"],
    "nutrient_db": ["nutrient", "food_nutrient"],
    "gap_db": ["reference_intakes"],
    "recommender_db": ["foods"],
}


# ---------------------------------------------------------------- reading

def read_all_foods(branded: int) -> list[dict]:
    ausnut_dir = DATA_DIR / "ausnut"
    if not (ausnut_dir / ausnut.NUTRIENTS_FILE).exists():
        sys.exit("Stopping: the Australian food data isn't downloaded. Run `python etl/download_ausnut.py` first.")
    start = time.time()
    print("- reading AUSNUT 2023 (Australian foods) ...", flush=True)
    australian = ausnut.read_foods(ausnut_dir)
    print(f"  {len(australian):,} foods ({time.time() - start:.0f}s)", flush=True)

    found = {}
    for folder, data_type in [("foundation", "foundation_food"),
                              ("sr_legacy", "sr_legacy_food"),
                              ("fndds", "survey_fndds_food")]:
        start = time.time()
        print(f"- reading {folder} ...", flush=True)
        found[folder] = usda.read_generic(DATA_DIR / folder, data_type)
        print(f"  {len(found[folder]):,} foods ({time.time() - start:.0f}s)", flush=True)

    links = usda.sr_legacy_links(DATA_DIR)
    filled = usda.fill_from_sr_legacy(found["foundation"], found["sr_legacy"], links)
    print(f"- filled in {filled:,} missing Foundation values from the same foods in SR Legacy", flush=True)
    foods = australian + found["foundation"] + found["sr_legacy"] + found["fndds"]

    if branded > 0:
        start = time.time()
        print(f"- reading branded (picking {branded:,}) ... this takes a few minutes", flush=True)
        found = usda.read_branded(DATA_DIR / "branded", branded)
        print(f"  {len(found):,} foods ({time.time() - start:.0f}s)", flush=True)
        foods += found
    return foods


# ---------------------------------------------------------------- writing

def food_data_present(conns) -> bool:
    return conns["meal_db"].execute("SELECT EXISTS (SELECT 1 FROM food_catalogue)").fetchone()[0]


def clear_food_data(conns):
    """Empty the food tables so they can be loaded again. Refuses if people have logged meals,
    because those meals point at foods in the catalogue."""
    in_use = conns["meal_db"].execute(
        "SELECT (SELECT count(*) FROM meal_items) + (SELECT count(*) FROM saved_recipe_items)"
    ).fetchone()[0]
    if in_use:
        sys.exit(f"Stopping: {in_use} logged meal or recipe items use the current foods. "
                 "Run `docker compose down -v` first if you really want to start from scratch.")
    # Postgres won't truncate a table other tables point at unless they're truncated together.
    # We've just checked meal_items and saved_recipe_items are empty, so this loses nothing.
    conns["meal_db"].execute("TRUNCATE food_portion, food_catalogue, meal_items, saved_recipe_items")
    conns["nutrient_db"].execute("TRUNCATE food_nutrient")
    conns["recommender_db"].execute("TRUNCATE foods")
    conns["gap_db"].execute("TRUNCATE reference_intakes")


def load_meal_db(conn, foods):
    with conn.cursor() as cur:
        with cur.copy("COPY food_catalogue (fdc_id, name, data_type, search_rank, category, barcode, "
                      "prep_state, has_full_micros) FROM STDIN") as copy:
            for f in foods:
                copy.write_row((f["fdc_id"], f["name"], f["data_type"], f["search_rank"], f["category"],
                                f["barcode"], f["prep_state"], f["has_full_micros"]))
        with cur.copy("COPY food_portion (fdc_id, description, gram_weight) FROM STDIN") as copy:
            for f in foods:
                for description, grams in f["portions"]:
                    copy.write_row((f["fdc_id"], description, grams))


def load_nutrient_db(conn, foods):
    # Look up nutrient-calc's own IDs for each key rather than hard-coding them here
    ids = dict(conn.execute("SELECT key, id FROM nutrient").fetchall())
    missing = set(usda.NUTRIENTS) - set(ids)
    if missing:
        sys.exit(f"Stopping: nutrient_db has no nutrient row for {sorted(missing)}")
    with conn.cursor() as cur:
        with cur.copy("COPY food_nutrient (fdc_id, nutrient_id, amount_per_100g) FROM STDIN") as copy:
            for f in foods:
                for key, amount in f["nutrients"].items():
                    copy.write_row((f["fdc_id"], ids[key], amount))


def load_recommender_db(conn, foods):
    with conn.cursor() as cur:
        with cur.copy("COPY foods (fdc_id, name, category, data_type, kcal_per_100g, protein_g, carbs_g, "
                      "fat_g, fibre_g, typical_serving_g, prep_state, has_full_micros, "
                      "adg_code, adg_name, discretionary, nutrients) FROM STDIN") as copy:
            for f in foods:
                n = f["nutrients"]
                micros = {k: v for k, v in n.items() if k not in usda.MACROS}
                copy.write_row((f["fdc_id"], f["name"], f["category"], f["data_type"],
                                n.get("energy"), n.get("protein"), n.get("carbs"), n.get("fat"), n.get("fibre"),
                                f["typical_serving_g"], f["prep_state"], f["has_full_micros"],
                                f["adg_code"], f["adg_name"], f["discretionary"], Jsonb(micros)))


def load_gap_db(conn):
    """Load the recommended intakes from reference_intakes.csv. Empty cells become NULL."""
    if not REFERENCE_CSV.exists():
        print(f"  (no {REFERENCE_CSV.name} found, skipping reference intakes)")
        return
    columns = ["nutrient_key", "sex", "age_min", "age_max", "life_stage", "intake_type", "rni_or_ai",
               "upper_limit", "sdt", "unit", "source", "verified"]
    with conn.cursor() as cur:
        with cur.copy(f"COPY reference_intakes ({', '.join(columns)}) FROM STDIN") as copy:
            for row in usda.read_csv(REFERENCE_CSV):
                copy.write_row([row[c].strip() or None for c in columns])


def print_counts(conns):
    print("\nRow counts per database and table:")
    total = 0
    for db, tables in TABLES.items():
        for table in tables:
            count = conns[db].execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            total += count
            print(f"  {db:15} {table:20} {count:>10,}")
    print(f"  {'':15} {'total':20} {total:>10,}")


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--branded", type=int, default=30_000, help="how many Branded foods to load (default 30000)")
    parser.add_argument("--skip-branded", action="store_true", help="don't load any Branded foods")
    parser.add_argument("--replace", action="store_true", help="clear the food data first and load it again")
    parser.add_argument("--counts-only", action="store_true", help="only print the row counts")
    args = parser.parse_args()

    # autocommit=False (the default): each database's load is committed only if it all worked
    conns = {db: psycopg.connect(url) for db, url in DB_URLS.items()}
    try:
        if args.counts_only:
            print_counts(conns)
            return

        if food_data_present(conns):
            if not args.replace:
                print("Food data is already loaded. Use --replace to load it again.")
                print_counts(conns)
                return
            print("- clearing the old food data")
            clear_food_data(conns)

        start = time.time()
        foods = read_all_foods(0 if args.skip_branded else args.branded)

        print("- writing meal_db ...", flush=True)
        load_meal_db(conns["meal_db"], foods)
        print("- writing nutrient_db ...", flush=True)
        load_nutrient_db(conns["nutrient_db"], foods)
        print("- writing recommender_db ...", flush=True)
        load_recommender_db(conns["recommender_db"], foods)
        print("- writing gap_db ...", flush=True)
        load_gap_db(conns["gap_db"])

        for conn in conns.values():
            conn.commit()
        # Refresh the planner statistics so the new indexes get used straight away
        for conn in conns.values():
            conn.autocommit = True
            conn.execute("ANALYZE")
        print(f"\nDone in {time.time() - start:.0f}s")
        print_counts(conns)
    finally:
        for conn in conns.values():
            conn.close()


if __name__ == "__main__":
    main()
