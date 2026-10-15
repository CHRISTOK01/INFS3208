# ETL: getting the USDA food data into the databases

We don't keep the USDA files in git. The Branded foods file alone is about 3 GB once it's unzipped,
GitHub won't accept files over 100 MB, and the data is public anyway, so anyone can download it
again. `etl/data/` is ignored by git (apart from an empty `.gitkeep` file that keeps the folder
there). What's in the repo is the script that downloads the data.

## 1. Download the data

```bash
# Download all four USDA data sets and unzip them into etl/data/ (about 440 MB to download, 3 GB unzipped)
python etl/download_usda.py

# Just the three main data sets (about 11 MB). You lose the Branded foods, and with them barcode lookup.
#   --skip-branded  leave out the big Branded foods file
python etl/download_usda.py --skip-branded

# Download everything again, even if it's already there
#   --force  re-download and overwrite what's there
python etl/download_usda.py --force
```

| Folder | Release | Download size | What we use it for |
|---|---|---|---|
| `etl/data/foundation/` | Foundation Foods, 2026-04-30 | about 3 MB | the most detailed vitamin and mineral data, shown first in search |
| `etl/data/sr_legacy/` | SR Legacy, 2018-04 (its last release) | about 5 MB | a wide range of everyday foods |
| `etl/data/fndds/` | FNDDS, 2024-10-31 | about 3 MB | foods as people actually eat them, including mixed dishes |
| `etl/data/branded/` | Branded Foods, 2026-04-30 | about 427 MB | supermarket products with barcodes (we only load part of it) |

Where the data comes from: U.S. Department of Agriculture, Agricultural Research Service,
FoodData Central, https://fdc.nal.usda.gov/download-datasets. It's public domain (CC0).

## 2. Load it into the databases

The loader runs in its own throwaway container, so you don't need to install anything. The stack
needs to be running first (`docker compose up -d`).

```bash
# Load everything: the three main data sets plus 30,000 Branded foods (takes about 5 minutes)
#   run --rm etl  start the "etl" container, run the loader, then remove the container
docker compose run --rm etl

# Load the food data again from scratch (for example after editing reference_intakes.csv)
#   --replace  empty the food tables first. It refuses if anyone has logged meals.
docker compose run --rm etl --replace

# Load a different number of Branded foods, or none at all
#   --branded N     how many Branded foods to pick (default 30000)
#   --skip-branded  leave the Branded foods out
docker compose run --rm etl --replace --branded 10000
docker compose run --rm etl --replace --skip-branded

# Just print how many rows are in each table
#   --counts-only  don't load anything
docker compose run --rm etl --counts-only

# Run the loader's unit tests
#   --entrypoint pytest  run pytest instead of the loader
docker compose run --rm --entrypoint pytest etl -v tests
```

Each service only gets the part of the data it needs, written into its own database with Postgres
COPY (which sends rows in bulk rather than one at a time). Foods are matched across services by
their USDA `fdc_id`.

| Database | Table | What goes in it |
|---|---|---|
| meal_db | `food_catalogue` | food names, type, category, barcode, raw/cooked, data-confidence label |
| meal_db | `food_portion` | household measures and their weight, like "1 cup = 30 g" |
| nutrient_db | `food_nutrient` | how much of each nutrient is in 100 g of each food |
| recommender_db | `foods` | one row per food: calories, macros, and the vitamins and minerals as JSON |
| gap_db | `reference_intakes` | recommended daily intakes by age and sex, from `reference_intakes.csv` |

### Row counts from the last full load (2026-10-15)

| Database | Table | Rows |
|---|---|---:|
| meal_db | food_catalogue | 43,593 |
| meal_db | food_portion | 61,307 |
| nutrient_db | nutrient | 31 |
| nutrient_db | food_nutrient | 726,232 |
| gap_db | reference_intakes | 250 |
| recommender_db | foods | 43,593 |
| | **total** | **875,006** |

Foods by data set: 378 Foundation, 7,785 SR Legacy, 5,430 FNDDS and 30,000 Branded.

### How the data gets cleaned

- **Nutrients are found by name and unit** (like "Magnesium, Mg" in MG), not by fixed ID numbers,
  because the IDs differ between releases. FNDDS even uses a different numbering scheme (nutrient
  "numbers" instead of IDs), and the loader detects that automatically.
- **Fallbacks:** if a food has no plain "Energy" value, the "Energy (Atwater ...)" values are used
  instead (most Foundation foods need this). Carbs, fibre, folate and sugars have fallbacks too.
  They're listed in `NUTRIENTS` at the top of `usda.py`.
- **Units** are converted into the unit nutrient-calc uses (g, mg, µg, kcal). Vitamin D in IU
  converts exactly (40 IU = 1 µg). Vitamin A in IU can't be converted to RAE exactly, so it's
  stored as unknown.
- **Missing values are never stored as 0.** If a food has no value for a nutrient, there's no row
  for it, and the app treats it as unknown.
- **Impossible values are thrown away**, like more than 100 g of something in 100 g of food, or
  more than 900 kcal per 100 g.
- **Foundation's food.csv is mostly lab sample records.** Only the real `foundation_food` rows are
  loaded, and foods with no calorie information at all are skipped.
- **Data-confidence label:** a generic food is marked "complete micronutrient data" if we know at
  least 15 of its 24 vitamins and minerals. Branded foods are always "label data only".

### How the 30,000 Branded foods are picked

USDA lists about 2 million Branded entries, but many are the same product re-published with
updates, so there are only about 465,000 different barcodes. The loader keeps the newest version of
each, then only considers products that:

- have a barcode and aren't discontinued
- give their serving size in grams. Products measured in ml have their nutrients per 100 ml, which
  would give wrong numbers because we count everything in grams.
- aren't supplements or vitamins
- have calories, protein, carbs and fat, and at least 8 of our nutrients overall

That leaves about 350,000 products. 30,000 of them are picked at random, using a fixed seed so that
every run picks exactly the same ones.

### Recommended intakes

`reference_intakes.csv` has the NHMRC recommended intakes by age and sex. **None of the values have
been checked against the official tables yet** (they're all marked `verified = false`), and sodium
is left empty on purpose. See [REFERENCE_INTAKES_TODO.md](REFERENCE_INTAKES_TODO.md) for the checklist.

## Things to remember

- **For the submission ZIP:** include a small trimmed sample so the marker can see what the data
  looks like, along with this download script for the full set. The other option is a link to the
  exact CSVs we used. If we do that, open the link in a private browser window first to make sure
  it works. Still to do: ask on Ed Discussion which one the marker prefers.
- **For GKE:** the databases in the cloud need the data too. We can either run the loader as a
  Kubernetes Job, or port-forward to the Postgres pods and load from a laptop. We'll decide when we
  get to deployment.
- Write down the final row counts that `load_usda.py` prints, so we can quote them in the report
  and the demo.
