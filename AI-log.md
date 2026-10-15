# AI Log

All prompts are copied word for word. The full project brief is in the appendix at the bottom.

---

## 1. Project setup and the nutrient-calc service

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Set up the repository and Docker Compose stack (four Postgres databases, Redis,
Nginx gateway, starter code for all four services), and wrote the nutrient-calc service and its tests.

**Prompts Used:**
- The full project brief (see appendix), followed by: "First help me do all the initial setup for
  the repo before you start. We will build each service one by one locally and test each one to make
  sure they work before moving to the next. So do the setup and start with the first microservice."

**Where the AI/MT Tool Was Used:**
- `docker-compose.yml`, `.env.example`, `.gitignore`, `.gitattributes`, `gateway/nginx.conf`
- `services/nutrient-calc/` (all files)
- `services/meal-logging/`, `services/gap-analysis/`, `services/food-recommender/` (starter files and `db/init.sql`)
- `README.md`, `docs/architecture.md`

---

## 2. Loading the USDA data

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Wrote the scripts that clean the USDA data and load it into each service's
database, with tests. Created the reference intakes CSV (values not yet verified against NHMRC) and
its checklist. Loaded the data and removed old test rows from the database.

**Prompts Used:**
- "Yes if you think 30,000 is a good number then sure thats fine. Also run the clean thing for me too"

**Where the AI/MT Tool Was Used:**
- `etl/usda.py`, `etl/load_usda.py`, `etl/Dockerfile`, `etl/requirements.txt`, `etl/tests/`
- `etl/reference_intakes.csv`, `etl/REFERENCE_INTAKES_TODO.md`, `etl/README.md`
- `docker-compose.yml` (the `etl` service)

---

## 3. Coverage fix in nutrient-calc

**AI/MT Tool:** Claude Code (Anthropic), Claude Opus 5.5

**Purpose of Use:** Added a `coverage_pct` field to the daily totals, updated the tests and docs,
and marked iodine as not used in gap analysis.

**Prompts Used:**
- "wait so can you explain if the nutrient-calc takes data from that data? or not? Also do you see
  any problems with the way that service was coded due to the layout of the data? or is it all good"
- "Make what you think are the most reasonable fixes and tell me what you did"

**Where the AI/MT Tool Was Used:**
- `services/nutrient-calc/app/calc.py`, `app/repo.py`, `db/init.sql`
- `services/nutrient-calc/tests/test_calc.py`, `tests/test_integration.py`
- `docs/architecture.md`, `etl/REFERENCE_INTAKES_TODO.md`

---
