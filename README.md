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
- [x] Phase 3b: meal-logging service
- [ ] Phase 3c and 3d: gap-analysis, food-recommender
- [ ] Phase 4: React frontend and demo users
- [ ] Phase 5: load test and failure test
- [ ] Phase 6: final README

## What you need

- **Docker Desktop.** It includes Docker Compose.
- **Python 3.12 or newer.** You only need this to download the data. Everything else runs in Docker.
- **A Google Cloud project with Identity Platform turned on.** People sign up and log in through
  Google, even when the app runs on your own computer. See "Setting up Google login" below.

On Windows PowerShell, type `curl.exe`, not `curl`. Plain `curl` in PowerShell is a different
command.

## Setting it up (first time)

Run these from the project folder, in order.

```bash
# 1. Make your settings file from the template
cp .env.example .env

# 2. Make a random secret, then paste it into JWT_SECRET in the .env file.
#    Also put your Google project ID and Web API key into GOOGLE_PROJECT_ID and GOOGLE_API_KEY
#    (see "Setting up Google login" below).
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

## Setting up Google login

You only need to do this once, in the Google Cloud console (https://console.cloud.google.com).

1. Pick your project at the top of the page. Its **project ID** (e.g. `macroscope-123456`) goes
   into `GOOGLE_PROJECT_ID` in `.env`.
2. Search for **Identity Platform** and click **Enable**. It's free for up to 50,000 users a month,
   but the project needs billing turned on.
3. Under **Providers**, click **Add a provider**, choose **Email / Password**, turn it on and save.
   (The "Sign in with Google" button gets set up with the website, in phase 4.)
4. Click **Application setup details** (top right) and copy the `apiKey`. It goes into
   `GOOGLE_API_KEY` in `.env`.
5. Restart the services so they pick up the new settings: `docker compose up -d`.

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

## What the finished services can do

**meal-logging** (`/api/meals/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| See who you're logged in as (signing up and logging in happen through Google) | `GET /auth/me` | yes |
| Search foods by name (raw or cooked first if you ask) | `GET /foods/search?q=banana&state=raw` | no |
| Look up a packaged food by barcode | `GET /foods/barcode/{code}` | no |
| See a food and its household portions | `GET /foods/{fdc_id}` | no |
| Log a meal (in grams, or as portions) | `POST /meals` | yes |
| List, view and delete meals; add or remove food | `GET /meals?start&end`, `GET /meals/{id}`, `DELETE /meals/{id}`, `POST /meals/{id}/items`, `DELETE /meals/{id}/items/{item_id}` | yes |
| Send days that nutrient-calc missed while it was down | `POST /meals/recalculate-pending` | yes |
| Saved recipes: save, list, delete, log again in one click | `POST /recipes`, `GET /recipes`, `DELETE /recipes/{id}`, `POST /recipes/{id}/log` | yes |

**nutrient-calc** (`/api/nutrients/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| List the nutrients we track | `GET /nutrients` | no |
| What's in 100 g of a food | `GET /foods/{fdc_id}` | no |
| Add up the nutrients in a list of foods | `POST /calculate` | yes |
| Save or read a user's daily totals | `PUT /daily/{user_id}/{date}`, `GET /daily/{user_id}?start&end` | yes |

## Trying out meal-logging

First you need a login token from Google. Until the website exists (phase 4), you can get one
straight from Google's sign-up API. In PowerShell:

```powershell
# Read your Web API key from .env (Google's sign-up API needs it)
$KEY = (Select-String -Path .env -Pattern '^GOOGLE_API_KEY=(.*)').Matches[0].Groups[1].Value

# Make an account with Google. The reply's "idToken" is your login token (it lasts an hour).
#   -X POST   send a POST request
#   -H        add a header (here, saying the body is JSON)
#   -d        the request body
curl.exe -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signUp?key=$KEY" -H "Content-Type: application/json" -d '{\"email\":\"me@example.com\",\"password\":\"password123\",\"returnSecureToken\":true}'

# Already have an account? Log in instead (same reply, with a new idToken)
curl.exe -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$KEY" -H "Content-Type: application/json" -d '{\"email\":\"me@example.com\",\"password\":\"password123\",\"returnSecureToken\":true}'
```

Then the easiest way to try things is the API page in your browser,
http://localhost:8080/api/meals/docs. Click **Authorize** at the top, paste the `idToken`, and use
**Try it out** on any endpoint.

Or from PowerShell:

```powershell
# Search for a food (no login needed). Run it twice: the X-Cache header goes from MISS to HIT.
#   -i  show the headers as well as the reply
curl.exe -i "http://localhost:8080/api/meals/foods/search?q=banana"

# See a food's household portions, like "1 medium = 118 g"
curl.exe http://localhost:8080/api/meals/foods/173944

# Look up a packaged food by its barcode
curl.exe http://localhost:8080/api/meals/foods/barcode/20048556

# Save your idToken so you don't have to paste it every time (put your own token in the quotes)
$TOKEN = "paste-the-idToken-here"

# Check it works: this says who you're logged in as
curl.exe http://localhost:8080/api/meals/auth/me -H "Authorization: Bearer $TOKEN"

# Log 100 g of raw spinach for lunch
curl.exe -X POST http://localhost:8080/api/meals/meals -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{\"meal_date\":\"2026-10-15\",\"meal_type\":\"lunch\",\"items\":[{\"fdc_id\":168462,\"grams\":100}]}'

# See that day's meals
curl.exe "http://localhost:8080/api/meals/meals?start=2026-10-15" -H "Authorization: Bearer $TOKEN"
```

**What happens if nutrient-calc is down:**

```powershell
# Stop nutrient-calc
docker compose stop nutrient-calc

# Log a meal (same command as above). It still saves, but says "calc_status": "pending".

# Start nutrient-calc again, wait about 10 seconds, then send the waiting days
docker compose start nutrient-calc
curl.exe -X POST http://localhost:8080/api/meals/meals/recalculate-pending -H "Authorization: Bearer $TOKEN"
```

## Running the tests

```bash
# Run nutrient-calc's tests in a one-off container
#   --rm  delete the container afterwards
docker compose run --rm nutrient-calc pytest -v

# Same again, but also run the tests that use the real database
#   -e INTEGRATION=1  turn on the database tests
docker compose run --rm -e INTEGRATION=1 nutrient-calc pytest -v

# meal-logging's tests. The INTEGRATION=1 ones need the food data loaded and nutrient-calc running.
#   -e INTEGRATION=1  turn on the tests that use the real databases, Redis and nutrient-calc
docker compose run --rm -e INTEGRATION=1 meal-logging pytest -v

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
