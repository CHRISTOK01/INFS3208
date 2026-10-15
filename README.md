# MacroScope

MacroScope helps you find the nutrients your diet is missing. You log what you eat, and it shows
your calories, protein, carbs, fat, fibre and about 25 vitamins and minerals against your own
targets. It spots the nutrients you're often short on over the last 7 and 14 days, and suggests
foods that would help.

> MacroScope gives estimates from food composition data. It isn't medical advice.

It's made of four small services. Each runs in its own container with its own database:

| Service | What it does | Web address (through the gateway) |
|---|---|---|
| meal-logging | accounts, food search, logging meals | `/api/meals` |
| nutrient-calc | adds up the nutrients in what you ate | `/api/nutrients` |
| gap-analysis | your targets, and what you're short on | `/api/gaps` |
| food-recommender | suggests foods to fill the gaps | `/api/recommend` |

Everything is reached through one gateway at **http://localhost:8080**, which sends each request to
the right service. More detail on the design is in [docs/architecture.md](docs/architecture.md).

## Progress

- [x] Phase 1: project setup (Docker Compose, 4 databases, Redis, gateway)
- [x] Phase 2: USDA food data loaded (875,006 rows)
- [x] Phase 3a: nutrient-calc service
- [ ] Phase 3b to 3d: meal-logging, gap-analysis, food-recommender
- [ ] Phase 4: React frontend and demo users
- [ ] Phase 5: load test and failure test
- [ ] Phase 6: final README

## What you need

- **Docker Desktop.** It includes Docker Compose.
- **Python 3.12 or newer.** You only need this to download the data. Everything else runs in Docker.

On Windows PowerShell, type `curl.exe`, not `curl`. Plain `curl` in PowerShell is a different
command.

## Setting it up (first time)

Run these from the project folder, in order.

```bash
# 1. Make your settings file from the template
cp .env.example .env

# 2. Make a random secret, then paste it into JWT_SECRET in the .env file
python -c "import secrets; print(secrets.token_hex(32))"

# 3. Build and start everything
#   --build  build the images first, so they include the latest code
#   -d       run in the background and give you the terminal back
docker compose up --build -d

# 4. Check everything is running. After about 30 seconds, each one should say "healthy".
docker compose ps

# 5. Download the USDA food data into etl/data/ (about 440 MB, only needed once)
python etl/download_usda.py

# 6. Load the food data into the databases (takes about 5 minutes, only needed once)
#   run   start a one-off container for the loader
#   --rm  delete that container when it's finished
docker compose run --rm etl
```

That's it. The databases keep their data, so next time you only need `docker compose up -d`.

## Everyday commands

```bash
# Start everything (add --build if you've changed any code)
docker compose up -d

# Stop everything. Your data is kept.
docker compose down

# Stop everything AND delete all the data. You'll need to do step 6 again afterwards.
#   -v  also delete the database storage
docker compose down -v

# Show a service's logs as they happen (Ctrl+C to stop)
#   -f  keep showing new lines
docker compose logs -f nutrient-calc
```

## Checking it works

```bash
# Ask a service for its version. The reply also says which container answered.
curl.exe http://localhost:8080/api/nutrients/version

# Check a service can reach its database. 200 means yes, 503 means no.
#   -i  show the status code as well as the reply
curl.exe -i http://localhost:8080/api/nutrients/ready
```

Each service has a page in your browser where you can try out its API, for example
http://localhost:8080/api/nutrients/docs. Swap `nutrients` for `meals`, `gaps` or `recommend` to see
the others.

## Running the tests

```bash
# Run nutrient-calc's tests in a one-off container
#   --rm  delete the container afterwards
docker compose run --rm nutrient-calc pytest -v

# Same again, but also run the tests that use the real database
#   -e INTEGRATION=1  turn on the database tests
docker compose run --rm -e INTEGRATION=1 nutrient-calc pytest -v

# Run the data loader's tests
#   --entrypoint pytest  run pytest instead of the loader
docker compose run --rm --entrypoint pytest etl -v tests
```

## Demo: load balancing and failures

```bash
# Run 3 copies of nutrient-calc
#   --scale nutrient-calc=3  how many copies to run
docker compose up -d --scale nutrient-calc=3

# Wait about 10 seconds, then run this a few times.
# "served_by" changes, because the gateway shares requests between the copies.
curl.exe http://localhost:8080/api/nutrients/version

# Go back to one copy
docker compose up -d --scale nutrient-calc=1

# Stop nutrient-calc's database to pretend it has crashed
docker compose stop nutrient-db

# The service stays up (/health gives 200) but says it isn't ready (/ready gives 503)
curl.exe -i http://localhost:8080/api/nutrients/health
curl.exe -i http://localhost:8080/api/nutrients/ready

# Start the database again. /ready goes back to 200 within a few seconds.
docker compose start nutrient-db
```

## The data

The food data comes from USDA FoodData Central (https://fdc.nal.usda.gov/download-datasets), which
is public domain. It's too big for git, so the repo has a script to download it instead.

The last load put **875,006 rows** into the databases, including 43,593 foods and 726,232 nutrient
values. The full counts, and how the data is cleaned, are in [etl/README.md](etl/README.md).

To look inside a database:

```bash
# Open a SQL prompt in nutrient-calc's database (type \q to leave)
#   exec            run a command in a container that's already running
#   -U nutrient     log in as the "nutrient" user
#   -d nutrient_db  open the nutrient_db database
docker compose exec nutrient-db psql -U nutrient -d nutrient_db
```

## What's where

```
docker-compose.yml   runs the whole app on your computer
gateway/nginx.conf   sends each /api/... request to the right service
services/<name>/     one folder per service: code (app/), tests, database setup (db/init.sql)
etl/                 downloads and loads the USDA data
frontend/            the React app (phase 4)
loadtest/            load test (phase 5)
k8s/                 Kubernetes files (later)
docs/                design notes
```
