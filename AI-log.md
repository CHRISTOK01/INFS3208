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

## 6. gap-analysis service

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Writing the third microservice, gap-analysis, which works out each person's
targets and finds the nutrients they're short on.

**Prompts Used:**
- "now start on the next micro-service"

**What Claude Code did and gave back:**
- Checked that the units in the reference intakes match the units nutrient-calc uses (they all did).
- Wrote the target maths: calories from the Mifflin-St Jeor equation x an activity factor,
  adjusted for the goal (cut, maintain or bulk); protein per kg of body weight; fat as 30% of
  calories; carbs as the rest; fibre, vitamins and minerals from the NHMRC table for the person's
  age and sex. Each target records where it came from, and unchecked NHMRC values say so.
- Wrote the gap rules: 7 and 14 day windows of full days before today; a day only counts for a
  nutrient if at least 80% of the food has a value for it; at least 3 such days are needed;
  "gap" below 70% of target, "excess" above the upper limit; iodine skipped. It also returns the
  top 5 gaps and how many days met each target.
- Wrote the endpoints: save/see a profile, see targets, today's intake and remaining macros, and
  the gap report, which falls back to the last saved report (marked "stale") if nutrient-calc is down.
- Reported two problems it found while testing with a real Google account, and fixed them: a
  brand-new Google token was rejected because Google's clock was a fraction ahead (it added 30
  seconds of leeway in all four services), and someone who only logged a little food would look
  short on everything (it added a rule that a day needs at least half the calorie target logged).
- Wrote 28 tests (target maths checked against hand-worked numbers, gap rules, and full
  integration with nutrient-calc), and deleted the test account and its data afterwards.

**Where the AI/MT Tool Was Used:**
- `services/gap-analysis/` (`app/targets.py`, `app/gaps.py`, `app/repo.py`, `app/routes.py`, `app/nutrient_client.py`, `app/config.py`, `app/main.py`, `requirements.txt`, all tests)
- `services/*/app/auth.py` (clock leeway), `services/nutrient-calc/tests/test_auth.py`, `services/meal-logging/tests/test_auth.py`
- `README.md`, `docs/architecture.md`

---

## 7. Australian food data and personalised targets

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Switching the main food data to Australian data (FSANZ AUSNUT 2023), and
rebuilding the profile and targets so they're worked out from published guidelines for each
person, including pregnancy and breastfeeding.

**Prompts Used:**
- "I need the app to be good at knowing the nutrients for all the foods and also good at knowing like how much of whatever someone needs according to gender, height, weight and all. How can we make this all better and accurate"
- "Yes switch to the australian database and make decisions that you think would make the system as useful and accurate as possible. I need you to ask about activity levels and all in the profile stuff and then research and figure out how much macros and micros and all people need. Make an option to select that you are pregnant on your profile so everything gets adjusted accordingly. Pretty much fine tune everything to be better and personalised as possible."

**What Claude Code did and gave back:**
- Explained where the app's numbers could be wrong (US data for Australian users, packaged foods
  with label data only, missing pregnancy and diet options, unsourced protein numbers) and
  suggested fixes in order.
- Found that FSANZ's AUSNUT 2023 suits the app better than the AFCD it first suggested: 3,741
  Australian foods with all 58 nutrients filled in, plus 9,816 portion sizes, under CC BY 4.0. It
  wrote `download_ausnut.py` and `ausnut.py` to download and read the Excel files, took copper,
  manganese and pantothenic acid from AFCD Release 3 for the same foods, and made Australian
  foods come first in search, with USDA kept as a fallback (and for barcodes). It also added four
  nutrients the Australian data has: free sugars, long chain omega-3, caffeine and alcohol.
- Researched the targets from NHMRC's own pages (energy, protein, fats, the chronic disease
  targets, and the pregnancy and breastfeeding tables for every vitamin and mineral), the NHMRC
  2020 alcohol guidelines, FSANZ's caffeine advice and the WHO sugar guideline. It rebuilt
  `reference_intakes.csv` with a script that read every number from the NHMRC tables, and checked
  that the existing values were unchanged.
- Rewrote the profile: date of birth, a lifestyle question with examples from NHMRC's table,
  exercise sessions a week, goal (lose, maintain or gain), diet (omnivore, vegetarian, vegan), and
  a due date or breastfeeding. Targets are now worked out for the date being looked at, so they
  follow birthdays and trimesters. Each target says where it came from, and the reply includes
  notes (for example about folic acid and iodine supplements in pregnancy, or B12 for vegans).
- Explained the rules it chose (energy from BMR x NHMRC activity level, protein limits, the goal
  adjustments and the safety rules for pregnancy) and the sources for each.
- Updated the tests (new ones for every target rule, worked out by hand) and reloaded the data.

**Where the AI/MT Tool Was Used:**
- `etl/ausnut.py`, `etl/download_ausnut.py`, `etl/usda.py`, `etl/load_usda.py`, `etl/requirements.txt`, `etl/reference_intakes.csv`, `etl/REFERENCE_INTAKES.md`, `etl/README.md`, `etl/tests/test_ausnut.py`
- `services/gap-analysis/` (`app/targets.py`, `app/gaps.py`, `app/repo.py`, `app/routes.py`, `db/init.sql`, all tests)
- `services/nutrient-calc/db/init.sql`, `services/meal-logging/db/init.sql`, `services/meal-logging/app/foods.py`, `services/meal-logging/app/repo.py`, meal-logging tests
- `README.md`, `docs/architecture.md`

---

## 9. Smarter food search

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Making food search find the food people mean, now that Australian and US foods
are mixed together and named differently.

**Prompts Used:**
- "do the search fix first"

**What Claude Code did and gave back:**
- Checked whether AUSNUT's number of portions could show which foods are most common, and found
  it couldn't (it would put brioche first for "bread"), so didn't use it.
- Changed the search so that plural endings are cut off ("strawberries" finds "Strawberry, raw"),
  cooking words like "boiled" or "grilled" mean "show cooked foods first" rather than having to be
  in the name (unless the whole search is the start of a name, like "baked beans"), main entries
  ("Banana, cavendish, raw") come before foods that only mention the word ("Banana chip"), FSANZ's
  "not further defined" average foods come next, and raw foods come before cooked ones when no
  choice is made.
- Tried about 30 everyday searches against the real data after each change, and fixed the
  problems it found on the way (raw foods weren't preferred because of how Postgres sorts empty
  values, "boiled" matched "parboiled", "roast" didn't match "roasted").
- Added unit tests for the new search rules and integration tests for five everyday searches.

**Where the AI/MT Tool Was Used:**
- `services/meal-logging/app/foods.py`, `app/repo.py`, `app/routes_foods.py`, `tests/test_foods.py`, `tests/test_integration.py`
- `docs/architecture.md`

---

## 10. food-recommender service

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Building the fourth service, which suggests foods to fill the gaps
gap-analysis finds.

**Prompts Used:**
- "start on the next micro-service"

**What Claude Code did and gave back:**
- Found that AUSNUT tags every food with its Australian Dietary Guidelines food group and whether
  it's "discretionary", and changed the data loader to copy those into recommender_db, so the
  recommender only suggests everyday foods using FSANZ's own judgement.
- Built the service: it asks gap-analysis for the 14-day gaps and for what's left today (calories,
  limits, diet, pregnancy), then scores every suitable food on one standard serve by how much of
  each shortfall it makes up, and explains each suggestion in a sentence. It also has a "foods rich
  in one nutrient" option. gap-analysis's /today now also sends the person's situation (diet and
  pregnancy) for this.
- Looked up FSANZ's pregnancy advice (listeria and mercury in fish) and leaves those foods out for
  pregnant users, and leaves out meat, fish, eggs or dairy to match the person's diet.
- Tried it on real data and fixed what looked wrong: AUSNUT's first portion size was often the
  whole food ("1 whole duck"), so it switched to the dietary guidelines' standard serves (checked
  against the Nutrition Australia fact sheet); it also left out baby foods, wild and game foods,
  ingredients like dried mushroom and egg yolk, and raw or dry forms of foods you'd cook.
- Added unit tests, API tests with gap-analysis faked, and integration tests (including a vegan
  check), and ran a full test through the gateway with a throwaway Google account.

**Where the AI/MT Tool Was Used:**
- `services/food-recommender/app/rules.py`, `app/routes.py`, `app/repo.py`, `app/gap_client.py`, `app/config.py`, `app/main.py`, `db/init.sql`, `requirements.txt`, `tests/`
- `services/gap-analysis/app/routes.py`, `app/targets.py`, `tests/test_targets.py`
- `etl/ausnut.py`, `etl/usda.py`, `etl/load_usda.py`, `etl/tests/test_ausnut.py`
- `README.md`, `docs/architecture.md`, `etl/README.md`

---
