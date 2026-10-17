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

## 8. Smarter food search

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

## 9. food-recommender service

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

## 10. Website, demo users, load test and failure tests

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Building the React website, the demo users, the load test and the final README,
and running the failure tests.

**Prompts Used:**
- "aight now lets do frontend and whatever else we need to finish off to be fully complete from a code point of view locally"

**What Claude Code did and gave back:**
- Built the React website (Vite, Chart.js, Firebase login): log in or sign up with email or Google;
  a profile form with pregnancy and breastfeeding; a dashboard with energy and macros left, a
  vitamins and minerals chart, a 14-day energy chart, limits, and 7/14-day gaps; food search,
  barcode lookup, portions, saved recipes and catching up pending totals; food suggestions; and a
  footer showing each service's version and which container answered. Added its two-stage
  Dockerfile and Nginx config, and sent the gateway's `/` to it.
- Gave it a design system in `styles.css`: colour, size and shadow tokens with automatic dark mode,
  bundled Inter and Fraunces fonts, and one colour per macro used everywhere. Added shared pieces:
  a line icon set and logo, pop-up notices, progress meters, an energy ring, segmented controls, a
  number stepper, a day picker, loading placeholders and empty states. On phones the tabs move to a
  bottom bar.
- Checked the logged-in pages in a browser using recorded API answers (so no password was typed),
  in light and dark mode, and fixed what looked wrong: faint chart bars in dark mode, a bite-size
  default portion, wrapped labels, misaligned tables, and "0 left" when over the energy target.
- Added `GET /api/meals/auth/config` so the website gets its login settings when it loads, instead
  of having them built in.
- Wrote `etl/seed_demo_users.py`, which makes 4 demo users through the real API with 3 weeks of
  meals each, chosen to leave gaps in magnesium, iron, vitamin D, and iron in pregnancy, and checked
  each one shows up. Fixed it using the container's UTC date instead of the local date.
- Wrote the load test (`loadtest/`), and found and fixed `docker compose run` putting scaled-up
  services back to one copy. Ran it with 3 meal-logging and 2 nutrient-calc copies (about 115
  requests a second, shared evenly, no failures).
- Ran the failure tests: killing a copy during the load test, stopping nutrient-calc, and stopping
  a database. Made food-recommender pass on gap-analysis's own error message, and added health
  checks for the gateway and the website.
- Rewrote the README with setup, the demo users, the website, the API, tests, and the load and
  failure demos with their results, and updated the architecture notes.

**Where the AI/MT Tool Was Used:**
- `frontend/` (all files)
- `etl/seed_demo_users.py`, `loadtest/loadtest.py`, `loadtest/Dockerfile`
- `services/meal-logging/app/routes_auth.py`, `app/config.py`, `tests/test_api.py`
- `services/food-recommender/app/routes.py`, `tests/test_api.py`
- `docker-compose.yml`, `gateway/nginx.conf`
- `README.md`, `docs/architecture.md`

---

## 11. Fixing and reworking food suggestions

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Fixing food suggestions showing nothing once someone had gone over a daily limit,
and making suggestions aim at each day's targets, with a weekly view and a 7-day report.

**Prompts Used:**
- "The food suggestions arent seem to be working. It just says no foods fit right now, even when i do search foods rich in whatever too"
- "Honestly I feel like the food recommendations should be a daily thing, like the goal should be to hit the targets each day. There should also be a weekly option to see what you should eat extra cause your low for that particular week. So maybe do today and 7 days (which needs 2-3 days of logging to work) rather than 7 and 14 days."

**What Claude Code did and gave back:**
- Reproduced the empty suggestions with a demo user: after one very salty, fatty meal, every mode
  gave no foods. The rule "a serve can't take today's total over a limit" ruled out nearly every
  food once the person was already over on sodium, because nearly every food has some.
- Changed the rule so that once someone is over a limit, a serve with up to 10% of that limit is
  still allowed (a limit of zero, like alcohol in pregnancy, still allows none). When nothing fits,
  the reply now says why (for example "most foods would take you over your limit for sodium today").
- Changed gap-analysis's report to cover only the last 7 days (still needing 3 days logged).
- Gave food-recommender a `period` setting. `today` (the default) scores foods on everything not
  reached yet today: target minus what's been eaten, for every vitamin, mineral, fibre and omega-3,
  leaving out nutrients only known for part of today's food. `week` uses the 7-day report's gaps.
  Each suggestion lists its top 4 nutrients, and the explanation says what the percentage is of.
- Updated the website's Suggestions page (Today, This week and Rich in... options) and the
  dashboard's focus card and report, checked it on a real account, and updated the tests, the demo
  user script and the docs.

**Where the AI/MT Tool Was Used:**
- `services/food-recommender/app/rules.py`, `app/routes.py`, `app/gap_client.py`, `tests/`
- `services/gap-analysis/app/routes.py`, `app/gaps.py`, `tests/test_integration.py`
- `frontend/src/pages/Suggestions.jsx`, `Dashboard.jsx`, `Login.jsx`
- `etl/seed_demo_users.py`, `README.md`, `docs/architecture.md`

---

## 12. Deploying to Google Kubernetes Engine

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Getting guidance on deploying to GKE: the Kubernetes files, a step-by-step guide
the student followed to do the deployment, and help fixing the Google sign-in setup when it didn't work.

**Prompts Used:**
- "Ive finished coding locally and its all done and all. Now I need to get to deploying: Here is some of the things I know I need to do: Need 2 VM's with the second being a duplicate of the first. Need the 4 databases. Need to implement the google sign in."
- "actually just tell me exactly what to do on the GCP and ill do it cause I want to learn"
- "ok start from what i need to do again from now onwards"
- "i need the web client id and web client secret to enable the google thing"
- "honeslty I need you to do this, I cant seem to get it working the google stuff. You may need to delete the stuff I did for the secret"
- "Firebase: Error (auth/api-key-not-valid.-please-pass-a-valid-api-key.). I get this when i hit continue with google"
- "can you delete all users on for me cause I want to sign up with my google and test everything. Also can I make the google work for everyone instead of just my account"
- "what is this privacy page? its just the same as the normal link with no /privacy.html" and "i mean like what is it meant to do? like whats the point of this"
- "is the second vm still a backup of the first rn? make sure we are still following that architecture"

**What Claude Code did and gave back:**
- Asked the student to choose how to deploy (what "2 VMs" meant for the assignment, where the
  databases should run, and what web address to use). The student chose a GKE cluster with 2 nodes,
  the databases inside the cluster, and a free nip.io address with HTTPS.
- Wrote the Kubernetes files in `k8s/` to match: the 4 Postgres databases as StatefulSets with
  their own disks, Redis, the 4 services (2 pods each, spread across both nodes, health checks,
  rolling updates), the website, autoscalers, and an HTTPS Ingress. Made each image carry its own
  version so rolling updates show in the website footer.
- Wrote `k8s/README.md`, a step-by-step guide with commented commands. The student ran the Google
  Cloud steps themselves (the image registry, building and pushing the images, creating the cluster,
  the IP address, settings and secrets, loading the data), asking about each problem along the way.
  Explained and fixed the errors they hit, like a kubectl cp problem with Windows paths and an API key
  pasted with extra characters.
- When the student asked for help with Google sign-in, found what was wrong (the consent screen was
  in Testing with no test users, localhost was missing from the authorized domains, and some origins
  were missing from the OAuth client) and fixed those at their request. The student entered the
  client secret themselves.
- At the student's request and after they chose which accounts to remove, deleted the test accounts
  and their data. Explained why Google needs a privacy policy before sign-in can be opened to
  everyone, added a privacy page, and published the app when the student asked for Google sign-in to
  work for everyone.

- When the student asked whether the second VM was still a backup of the first, checked where every
  pod was running and found three services had both copies on the same VM after rolling updates.
  Made "one copy on each VM" a firm rule (including during rolling updates), applied it with no
  downtime, explained how the databases fail over with their disks, and added a VM failure demo.

**Where the AI/MT Tool Was Used:**
- `k8s/` (all files), `services/*/Dockerfile`, `README.md`
- `frontend/public/privacy.html`, `frontend/Dockerfile`

---

## 13. More realistic energy targets

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Fixing energy (calorie) targets that came out too high, after checking them
against official guidance and common calorie calculators.

**Prompts Used:**
- "the website is overshooting how many calories an individual needs I feel like. like it says my maintence calories to maintain weight is like 2970 calories, which is much too high. Do some better research and check some calorie calculators or something and alter tweak this"

**What Claude Code did and gave back:**
- Worked through the student's 2,970 kcal: resting energy 1,548 kcal x activity level 1.92, which is
  in the "active" range for someone who mostly sits.
- Checked it against the FAO/WHO/UNU 2004 energy report (which NHMRC's values are based on) and
  common online calculators. Found exercise was counted about three times too high (FAO: an hour a
  day adds about 0.2 to the activity level) and the "sitting with some walking" level was set above
  FAO's typical office worker (1.55).
- Changed the activity levels to FAO's categories and scaled exercise from FAO's figure, bringing the
  same profile to about 2,540 kcal. Updated the tests with the new hand-worked numbers and the docs.

**Where the AI/MT Tool Was Used:**
- `services/gap-analysis/app/targets.py`, `tests/test_targets.py`, `tests/test_integration.py`
- `docs/architecture.md`, `k8s/30-services.yaml`

---

## 14. Website visual and usability improvements

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Making the website simpler and clearer to use: a food diary layout, a
today/this week view on the dashboard, and easier-to-read charts and food suggestions.

**Prompts Used:**
- "my focus thing says every target hit when i havent got enough carbs for the day (include macros too), also havent got enough pantothenic acid, mangenense or copper. Also on the hover popup for the vitamin and minerals, dont make it say like (from the 40% of todays food that has a value for it), just say the measurement like 1.2 of 1.7: 70.2%."
- "Ok I need you to make an edit to the webpage. On the suggestions page, if you just have data for one day, it comes up with the recommendations and all to fill the gaps and all that, but on the home screen, it is limited to the weekly cycle. I need you to edit the your focus this week section so you can select the today and 7 day option (So i should be able to pick what i wanna see - cause i wanna get recommendations and analysis for today if i aint got enough data and all). Also with this some food has no value stuff, why is that grey and a seperate thing? Like just calculate the foods that have the value and put it into the under or over 70% category accordingly."
- "redesign the log food page to look like a diary/log page ... Breakfast (+) Lunch - rice with chicken (edit/delete) (+) Dinner (+) ... Something like this cause I feel like that is a more use friendly and more simple way to lay it out so everyone understands"
- "On the food ideas page, need to make the food title like eg. Milk bigger and bolder, and the coloured category of the item says like (milk, yougurt, cream or whatever), thats confusing because the user cant erasily identify what yuou arte recommending, make those categories say like Dairy, etc. Also the text in each food recommendation at the bottom, delete it, its not needed cause it just repeats what the graphs and other stuff in the box say above it anyway."

**What Claude Code did and gave back:**
- Rebuilt the log food page as a food diary: a section for each meal listing its foods with their
  calories, edit and delete on every food, "+ Add food" (a panel to search, type a barcode or pick a
  saved recipe), and today's calories eaten, target and what's left at the top. Added a
  `PATCH /api/meals/meals/{meal_id}/items/{item_id}` endpoint to meal-logging so the edit button
  can change an amount, with tests.
- Gave the dashboard's "Your focus" card a Today / This week switch, with its button opening
  Suggestions in the matching mode. "Today" now counts energy, the macros and nutrients only some
  foods have values for, and Suggestions can fill protein, carbs and fat too.
- Simplified the vitamins and minerals chart: no separate grey colour, and the pop-up just shows the
  amount, the target and the percentage.
- Made the food suggestion cards easier to read: bigger, bolder food names, short food group tags
  (Vegetables, Fruit, Grains, Dairy, Protein), and no repeated sentence at the bottom.
- Checked the changes in a preview with a demo user's data, and updated the README and docs.

**Where the AI/MT Tool Was Used:**
- `frontend/src/pages/LogMeal.jsx`, `Dashboard.jsx`, `Suggestions.jsx`, `frontend/src/App.jsx`, `frontend/src/components/Icon.jsx`, `frontend/src/styles.css`
- `services/meal-logging/app/routes_meals.py`, `app/repo.py`, `tests/test_foods.py`, `tests/test_integration.py`
- `services/food-recommender/app/rules.py`, `app/repo.py`, `tests/test_rules.py`
- `README.md`, `docs/architecture.md`, `k8s/30-services.yaml`, `k8s/40-frontend.yaml`

---

