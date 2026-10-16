# AI Log

All prompts are copied word for word. Where a prompt was very long (the project brief), it's
summarised.

---

## 1. Project setup and the nutrient-calc service

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Setting up the project and writing the first microservice, nutrient-calc.

**Prompts Used:**
- I gave Claude Code my full project brief. It described the app (macro and micronutrient
  tracking with 7 and 14 day gap checks), the assignment rules (4 microservices, each with its
  own database, 10,000+ records, no message queues, every command commented), the tech stack
  (Python 3.14, FastAPI, PostgreSQL, Redis, React, Docker Compose, later GKE), the four services
  and their tables, the data sources (USDA FoodData Central, NHMRC reference values) and the build
  phases. I finished it with: "First help me do all the initial setup for the repo before you
  start. We will build each service one by one locally and test each one to make sure they work
  before moving to the next. So do the setup and start with the first microservice."
- "install docker and then tell me exactly how to test it all"
- "this all works, so anything else we may need to do for this service or is that it?"

**What Claude Code did and gave back:**
- Checked that every Python package installs on Python 3.14 before pinning versions, and told me
  about two changes: using `httpx2` instead of `httpx` for tests, and calling `bcrypt` directly
  instead of `passlib`.
- Created `docker-compose.yml` with four separate Postgres 18 databases, Redis, the four services
  and an Nginx gateway on port 8080, plus a database schema (`db/init.sql`) for every service.
- Wrote nutrient-calc: adding up 31 nutrients for a list of foods, saving each user's daily totals
  (always recalculating the whole day so nothing is counted twice), and treating missing nutrient
  values as unknown rather than zero. Also wrote its unit and integration tests.
- Listed the design decisions it had made for me to check, e.g. plain SQL instead of an ORM, no
  path rewriting in the gateway (to match GKE Ingress), and no host ports on the services (so they
  can be scaled).
- Installed Docker Desktop, ran all the tests in containers (35 passed), and gave me step-by-step
  commands to check the stack, load balancing (`--scale nutrient-calc=3`) and a database failure
  (`/health` stays 200 while `/ready` goes to 503).
- Confirmed nutrient-calc was finished apart from things that depend on later phases (real data,
  being called by meal-logging and gap-analysis, load testing, Kubernetes files).

**Where the AI/MT Tool Was Used:**
- `docker-compose.yml`, `.env.example`, `.gitignore`, `.gitattributes`, `gateway/nginx.conf`
- `services/nutrient-calc/` (all files)
- `services/meal-logging/`, `services/gap-analysis/`, `services/food-recommender/` (starter files and `db/init.sql`)
- `README.md`, `docs/architecture.md`

---

## 2. Loading the USDA data

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Downloading the USDA food data, cleaning it, and loading it into each
service's own database.

**Prompts Used:**
- I pasted advice (which I'd got from Claude) on how to handle the USDA files: don't commit the
  raw files to git, add a download script instead, include a trimmed sample or a link in the
  submission, and plan how to load the data on GKE.
- Claude Code suggested loading a 30,000-food subset of the Branded foods. I replied: "Yes if you
  think 30,000 is a good number then sure thats fine. Also run the clean thing for me too"

**What Claude Code did and gave back:**
- Wrote `etl/download_usda.py`, which downloads exact, pinned USDA releases (Foundation, SR Legacy,
  FNDDS and Branded) into `etl/data/`, kept out of git.
- Wrote the cleaning rules (`etl/usda.py`): nutrients are found by name and unit rather than
  hard-coded IDs, energy falls back to the Atwater values when needed, units are converted
  (e.g. vitamin D from IU), impossible values are dropped, and missing values are never stored as 0.
- Wrote the loader (`etl/load_usda.py`), which bulk-loads with Postgres COPY and prints row counts.
  The load gave 875,006 rows (43,593 foods and 726,232 nutrient values).
- Reported the problems it found and fixed: FNDDS uses a different nutrient numbering (it would
  have loaded zero nutrients for 5,430 foods), zero-calorie foods like water were being dropped,
  273 junk portion rows, and a database rule that broke reloading.
- Created `etl/reference_intakes.csv` with NHMRC recommended intakes from its own knowledge. It
  told me none of the values were checked against the official tables, marked all 250 rows as
  unverified, left sodium empty on purpose, and wrote a checklist for me to verify them
  (`etl/REFERENCE_INTAKES_TODO.md`).
- Checked the results against published USDA values (raw spinach and banana), and deleted old
  test rows from the database.

**Where the AI/MT Tool Was Used:**
- `etl/download_usda.py`, `etl/usda.py`, `etl/load_usda.py`, `etl/Dockerfile`, `etl/requirements.txt`, `etl/tests/`
- `etl/reference_intakes.csv`, `etl/REFERENCE_INTAKES_TODO.md`, `etl/README.md`
- `docker-compose.yml` (the `etl` service), `.gitignore`

---

## 3. Coverage fix in nutrient-calc

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Checking whether nutrient-calc's code suited the real data, and fixing the
problems found.

**Prompts Used:**
- "wait so can you explain if the nutrient-calc takes data from that data? or not? Also do you see
  any problems with the way that service was coded due to the layout of the data? or is it all good"
- "Make what you think are the most reasonable fixes and tell me what you did"

**What Claude Code did and gave back:**
- Explained that nutrient-calc reads the `food_nutrient` table loaded into its own database, and
  only works with food IDs and grams sent by meal-logging.
- Counted how many foods have a value for each nutrient, and reported that magnesium, zinc and the
  B vitamins are only known for about 30% of foods (mostly because Branded foods only list a few
  nutrients on the label), and iodine for only 0.3%.
- Explained the problem this causes: one packaged food with no magnesium value made a whole day's
  magnesium "incomplete".
- Added `coverage_pct` to the daily totals (the share of the day's food, by weight, that had a
  value), updated the database and tests, and tested it on a real meal (magnesium known for 91.8%
  of the food).
- Marked iodine as not used in gap analysis, and saved a note that the demo users should mostly
  log generic foods.

**Where the AI/MT Tool Was Used:**
- `services/nutrient-calc/app/calc.py`, `app/repo.py`, `db/init.sql`
- `services/nutrient-calc/tests/test_calc.py`, `tests/test_integration.py`
- `docs/architecture.md`, `etl/REFERENCE_INTAKES_TODO.md`

---

## 4. meal-logging service

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Writing the second microservice, meal-logging.

**Prompts Used:**
- "I committed, now start doing meal-logging service, if you need me to clarify anything, just ask,
  if not, go ahead"

**What Claude Code did and gave back:**
- Wrote food search with a Redis cache (the `X-Cache` header shows HIT or MISS), barcode lookup,
  each food's household portions, turning portions into grams, logging and deleting meals and
  items, and saved recipes that can be logged again in one click.
- Wrote the link to nutrient-calc: every change saves the meal and puts the day on a
  `pending_days` list, then sends the whole day to nutrient-calc. If nutrient-calc is down, the
  meal is still saved as "pending" and `POST /meals/recalculate-pending` catches up later. A
  Postgres lock per user and day stops two meals saved at once from overwriting each other.
- Reported problems it found while testing and fixed: "milk" showed yogurt and cheese first,
  duplicate food names, barcodes stored with extra leading zeros, and searches taking 7 seconds
  when Redis was stopped (now it skips Redis for 30 seconds after an error).
- Tested the failure cases for real by stopping nutrient-calc and Redis, wrote 33 tests, and gave
  me step-by-step commands to check it myself.

**Where the AI/MT Tool Was Used:**
- `services/meal-logging/` (all files in `app/` and `tests/`, plus `db/init.sql` and `requirements.txt`)
- `README.md`, `docs/architecture.md`

---

## 5. Switching logins to Google Cloud Identity Platform

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Replacing our own login system with Google Cloud Identity Platform.

**Prompts Used:**
- "I realised I want to use Google's authentication system rather than building my own. This is
  more secure and a better way to do it according to my tutor. Also in the app, we are going to
  have a sign up and login stage where users put in their gender, height, weight, activity levels
  and then it calculates how much of everything they need for the nutrient gap checking?"
- Claude Code asked me four questions, and I answered: sign in with both email/password and a
  Google button; I already have a Google Cloud project; ask users for details like gender,
  height, weight and activity level and use them to calculate their requirements; make the switch
  now, before gap-analysis.
- "Did those steps" (after setting up Identity Platform in my project)

**What Claude Code did and gave back:**
- Explained what changes with Google login, and that only one part stays our own: the short-lived
  token one service uses to call another.
- Checked that the extra package needed to verify Google's tokens (`cryptography`) installs on
  Python 3.14.
- Rewrote `auth.py` in all four services to check Google's tokens (signed by Google, made for my
  project, not expired). Our own service tokens now only work for service-to-service calls.
- Removed meal-logging's register and login endpoints, password hashing and `users` table, and
  changed user IDs to Google's text IDs in all four databases. Food and reference data weren't
  touched.
- Rewrote the tests to use fake Google tokens, so they run without internet access.
- Gave me the steps to enable Identity Platform, then tested it with real Google accounts: sign
  up, log a meal, check another service accepts the same token, and check that other users' data
  and fake tokens are blocked (403 and 401). It deleted the test accounts afterwards.

**Where the AI/MT Tool Was Used:**
- `services/*/app/auth.py`, `app/config.py`, `app/main.py`, `tests/conftest.py`, `requirements.txt` (all four services)
- `services/meal-logging/` (`app/routes_auth.py`, `app/repo.py`, `app/routes_meals.py`, `app/nutrient_client.py`, `db/init.sql`, tests)
- `services/nutrient-calc/` (`app/routes.py`, `app/repo.py`, `db/init.sql`, tests), `services/gap-analysis/db/init.sql`
- `docker-compose.yml`, `.env.example`, `README.md`, `docs/architecture.md`

---
