# MacroScope

MacroScope helps you find the nutrients your diet is missing. You log what you eat, and it shows
your calories, protein, carbs, fat, fibre and over 20 vitamins and minerals against targets made
for you (from your age, sex, size, activity, goal, diet, and pregnancy or breastfeeding). It spots
what you still need to hit today's targets and what you've been short on over the last 7 days,
and suggests everyday foods that would help.

> MacroScope gives estimates from food composition data. It isn't medical advice.

It's made of four small services. Each runs in its own container with its own database:

| Service | What it does | Web address (through the gateway) |
|---|---|---|
| meal-logging | food search (cached in Redis), barcodes, logging meals, saved recipes | `/api/meals` |
| nutrient-calc | adds up the nutrients in what you ate, keeps daily totals | `/api/nutrients` |
| gap-analysis | your profile and targets, and what you're short on | `/api/gaps` |
| food-recommender | suggests foods to fill the gaps | `/api/recommend` |

The React website and the four services are all reached through one gateway at
**http://localhost:8080**, which sends each request to the right place (on Kubernetes, the Ingress
will do this job). The services talk to each other with plain REST calls; there are no message
queues. More detail on the design is in [docs/architecture.md](docs/architecture.md).

```
browser ──► gateway :8080 ──┬─ /               ─► frontend (React, served by Nginx)
                            ├─ /api/meals      ─► meal-logging     ─► meal-db + redis
                            ├─ /api/nutrients  ─► nutrient-calc    ─► nutrient-db
                            ├─ /api/gaps       ─► gap-analysis     ─► gap-db
                            └─ /api/recommend  ─► food-recommender ─► recommender-db
```

It runs on your own computer with Docker Compose, and on Google Kubernetes Engine (GKE) across 2 VMs.
The cloud deployment is explained step by step in [k8s/README.md](k8s/README.md).

## What you need

- **Docker Desktop.** It includes Docker Compose.
- **Python 3.12 or newer.** You only need this to download the food data. Everything else runs in Docker.
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

# 5. Download the food data into etl/data/ (only needed once)
#    The Australian data (about 6 MB) and the USDA data (about 440 MB)
python etl/download_ausnut.py
python etl/download_usda.py

# 6. Load the food data into the databases (takes about 6 minutes, only needed once)
#   run   start a one-off container for the loader
#   --rm  delete that container when it's finished
docker compose run --rm etl

# 7. Make the demo users, with 3 weeks of meals each (takes about a minute)
#   -e TODAY=...           today's date where you are (the container's clock is on UTC)
#   --entrypoint python    run this script instead of the loader
docker compose run --rm -e TODAY=2026-10-17 --entrypoint python etl seed_demo_users.py
```

In PowerShell you can fill in today's date for step 7 automatically:
`docker compose run --rm -e TODAY=$(Get-Date -Format yyyy-MM-dd) --entrypoint python etl seed_demo_users.py`

That's it. Open **http://localhost:8080**. The databases keep their data, so next time you only
need `docker compose up -d`.

## Setting up Google login

You only need to do this once, in the Google Cloud console (https://console.cloud.google.com).

1. Pick your project at the top of the page. Its **project ID** (e.g. `macroscope-123456`) goes
   into `GOOGLE_PROJECT_ID` in `.env`.
2. Search for **Identity Platform** and click **Enable**. It's free for up to 50,000 users a month,
   but the project needs billing turned on.
3. Under **Providers**, click **Add a provider**, choose **Email / Password**, turn it on and save.
4. Optional, for the website's **Continue with Google** button: add the **Google** provider too.
   Google fills in the details for you. Under **Settings > Security**, check `localhost` is in the
   list of authorised domains (it is by default). Without this, the button says that way of
   logging in isn't turned on, and email and password still work.
5. Click **Application setup details** (top right) and copy the `apiKey`. It goes into
   `GOOGLE_API_KEY` in `.env`. It isn't a secret: the website hands it to every browser.
6. Restart the services so they pick up the new settings: `docker compose up -d`.

## Using the website

Go to **http://localhost:8080** and make an account, or log in as one of the demo users. They all
have the password **`MacroScope-demo-2026`**:

| Email | Who they are | What the app finds |
|---|---|---|
| `alex@macroscope-demo.test` | 29, office job, lots of white bread, rice and chicken | short on magnesium, fibre, vitamin C and more |
| `priya@macroscope-demo.test` | 25, vegetarian, no legumes or fortified cereal | very short on iron (vegetarians need 1.8 times as much) |
| `sam@macroscope-demo.test` | 35, trying to lose weight, no fish, eggs or mushrooms | short on vitamin D, iron and calcium |
| `jess@macroscope-demo.test` | 32, 22 weeks pregnant, eats well | short on iron (27 mg a day in pregnancy) |

The tabs:

- **Dashboard**: today's energy and macros (and what's left), a chart of vitamins and minerals
  against your targets, your limits (sodium, saturated fat, sugar, alcohol, caffeine), and the
  nutrients you've been short on over the last 7 days.
- **Food diary**: a section for each meal (breakfast, lunch, dinner, snacks) listing what you had
  and its calories, with edit and delete on every food. **+ Add food** opens a panel to search
  (raw or cooked first), type a barcode, or pick a saved recipe; choose a household portion like
  "1 banana, medium" and it's added straight away. Any meal can be saved as a recipe.
- **Suggestions**: everyday foods, each with a sentence saying why. **Today** fills the most of what
  you still need to hit today's targets; **This week** helps with what you've been short on over
  the last 7 days; **Rich in...** finds good sources of any one nutrient.
- **My details**: your profile, including pregnancy and breastfeeding, and every target with where
  it comes from.

The date picker at the top lets you look back at (or log food for) an earlier day. The footer shows
the version each service is running and which container answered the last request.

## Everyday commands

```bash
# Start everything (add --build if you've changed any code)
docker compose up -d

# Stop everything. Your data is kept.
docker compose down

# Stop everything AND delete all the data. You'll need to do steps 6 and 7 again afterwards.
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

## The API

`{user_id}` is your Google ID (`GET /api/meals/auth/me` shows it). People can only see their own
data; our services can ask about anyone, using their own short-lived service token.

**meal-logging** (`/api/meals/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| The login settings the website needs (project and public API key) | `GET /auth/config` | no |
| See who you're logged in as | `GET /auth/me` | yes |
| Search foods by name (raw or cooked first if you ask) | `GET /foods/search?q=banana&state=raw` | no |
| Look up a packaged food by barcode | `GET /foods/barcode/{code}` | no |
| See a food and its household portions | `GET /foods/{fdc_id}` | no |
| Log a meal (in grams, or as portions) | `POST /meals` | yes |
| List, view and delete meals; add, change the amount of, or remove food | `GET /meals?start&end`, `GET /meals/{id}`, `DELETE /meals/{id}`, `POST /meals/{id}/items`, `PATCH /meals/{id}/items/{item_id}`, `DELETE /meals/{id}/items/{item_id}` | yes |
| Send days that nutrient-calc missed while it was down | `POST /meals/recalculate-pending` | yes |
| Saved recipes: save, list, delete, log again in one click | `POST /recipes`, `GET /recipes`, `DELETE /recipes/{id}`, `POST /recipes/{id}/log` | yes |

**nutrient-calc** (`/api/nutrients/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| List the nutrients we track | `GET /nutrients` | no |
| What's in 100 g of a food | `GET /foods/{fdc_id}` | no |
| Add up the nutrients in a list of foods | `POST /calculate` | yes |
| Save or read a user's daily totals | `PUT /daily/{user_id}/{date}`, `GET /daily/{user_id}?start&end` | yes |

**gap-analysis** (`/api/gaps/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| The choices for the sign-up form (lifestyles with descriptions, goals, diets) | `GET /profile-options` | no |
| Save your details, and see the targets they lead to | `PUT /profile/{user_id}` | yes |
| See your details, or your targets for a day and where each number came from | `GET /profile/{user_id}`, `GET /targets/{user_id}?date=` | yes |
| A day's intake against your targets, and the calories and macros you have left | `GET /today/{user_id}?date=2026-10-17` | yes |
| Your gaps and excesses over the last 7 days | `GET /report/{user_id}?date=2026-10-17` | yes |

**food-recommender** (`/api/recommend/...`)

| What | Endpoint | Login needed? |
|---|---|---|
| Foods that fill the most of what you still need today, within the calories you have left | `GET /foods/{user_id}?date=2026-10-17` | yes |
| Foods for what you've been short on over the last 7 days | `GET /foods/{user_id}?date=2026-10-17&period=week` | yes |
| Good sources of one nutrient, gaps or not | `GET /foods/{user_id}?date=2026-10-17&nutrient=iron` | yes |

Every service also has `GET /health` (is it running?), `GET /ready` (can it reach its database?)
and `GET /version`, both at the root and under its own path.

## Trying the API from PowerShell

The website is the easy way in, but you can call the API directly too. First get a login token
from Google:

```powershell
# Read your Web API key from .env (Google's login API needs it)
$KEY = (Select-String -Path .env -Pattern '^GOOGLE_API_KEY=(.*)').Matches[0].Groups[1].Value

# Log in as a demo user. The reply's "idToken" is your login token (it lasts an hour).
#   -X POST   send a POST request
#   -H        add a header (here, saying the body is JSON)
#   -d        the request body
$login = curl.exe -s -X POST "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$KEY" -H "Content-Type: application/json" -d '{\"email\":\"priya@macroscope-demo.test\",\"password\":\"MacroScope-demo-2026\",\"returnSecureToken\":true}' | ConvertFrom-Json
$TOKEN = $login.idToken
$MYID = $login.localId     # your Google ID

# (To make a new account instead, use accounts:signUp in place of accounts:signInWithPassword.)
```

You can also paste the token into **Authorize** on any service's `/docs` page and use
**Try it out**. Some things to try:

```powershell
# Search for a food (no login needed). Run it twice: the X-Cache header goes from MISS to HIT.
#   -i  show the headers as well as the reply
curl.exe -i "http://localhost:8080/api/meals/foods/search?q=banana"

# See a food's household portions, like "1 banana, medium = 127 g"
curl.exe http://localhost:8080/api/meals/foods/16502001

# Log a medium banana (127 g) for a snack. Instead of "grams", you can give "portion_id" (one of
# the portions from the reply above) and "quantity" (how many).
curl.exe -X POST http://localhost:8080/api/meals/meals -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{\"meal_date\":\"2026-10-17\",\"meal_type\":\"snack\",\"items\":[{\"fdc_id\":16502001,\"grams\":127}]}'

# How much energy and macros you have left today
#   the ` before ? stops PowerShell treating the ? specially
(curl.exe -s "http://localhost:8080/api/gaps/today/$MYID`?date=2026-10-17" -H "Authorization: Bearer $TOKEN" | ConvertFrom-Json).remaining

# Your gaps over the last 7 days (it looks at the full days BEFORE the date you give)
$report = curl.exe -s "http://localhost:8080/api/gaps/report/$MYID`?date=2026-10-17" -H "Authorization: Bearer $TOKEN" | ConvertFrom-Json
$report.windows[0].top_gaps
$report.windows[0].nutrients | Format-Table nutrient_key, avg_intake, unit, pct_of_target, status

# Foods that would help fill them, each with a reason
$rec = curl.exe -s "http://localhost:8080/api/recommend/foods/$MYID`?date=2026-10-17" -H "Authorization: Bearer $TOKEN" | ConvertFrom-Json
$rec.suggestions | Format-List name, why
```

## Running the tests

```bash
# Run each service's tests in a one-off container. -e INTEGRATION=1 also runs the tests that use
# the real databases and the other services, so the app needs to be running with the data loaded.
#   --rm               delete the container afterwards
#   -e INTEGRATION=1   turn on the integration tests (leave it out for just the quick ones)
docker compose run --rm -e INTEGRATION=1 nutrient-calc pytest -v
docker compose run --rm -e INTEGRATION=1 meal-logging pytest -v
docker compose run --rm -e INTEGRATION=1 gap-analysis pytest -v
docker compose run --rm -e INTEGRATION=1 food-recommender pytest -v

# The data loader's tests
#   --entrypoint pytest  run pytest instead of the loader
docker compose run --rm --entrypoint pytest etl -v tests
```

## Demo: load balancing, load test and failures

**Load balancing.** Run several copies of a service; the gateway shares requests between them.

```bash
# Run 3 copies of meal-logging and 2 of nutrient-calc
#   --scale <service>=<n>  how many copies of that service to run
docker compose up -d --scale meal-logging=3 --scale nutrient-calc=2

# Wait about 10 seconds (the gateway looks the copies up every 10 s), then run this a few
# times. "served_by" changes from one copy to the next.
curl.exe http://localhost:8080/api/meals/version
```

The footer of the website shows the same thing: "Last answer: meal-logging, from `<container>`".

**Load test.** 20 simulated people searching, logging meals and working out nutrients, as fast as
they can. It ends with a table of how many requests worked, how fast they were, and which copies
answered. It uses its own test account and cleans up its meals afterwards.

```bash
# Run the load test
#   --users    how many people at once (default 20)
#   --seconds  how long to keep going (default 60)
docker compose run --rm loadtest --users 20 --seconds 60
```

On a laptop with the copies above, this did about 115 requests a second with no failures, split
evenly (633 / 603 / 598 requests across the three meal-logging copies). The command doesn't restart
the app, so it keeps the extra copies you started.

**Failure tests.** Stop things while the app is in use and watch it cope. These are the results
from running them:

```bash
# 1. A copy crashes in the middle of the load test. Start the load test in one terminal, and
#    while it's running, kill one copy from another terminal:
docker compose run --rm loadtest --users 20 --seconds 30
docker kill macroscope-meal-logging-2
#    Result: 3,505 of 3,510 requests still worked. The 5 that failed were meals being saved on
#    that copy at the moment it died. The gateway doesn't resend those, because sending a save
#    twice could log the meal twice. Searches and other reads were retried on the other copies.

# 2. nutrient-calc goes down completely
docker compose stop nutrient-calc
#    Result: on the website you can still search and log meals. They're saved and marked
#    "totals pending". The dashboard shows the last saved 7-day report, marked as out of date,
#    and says today's totals can't be worked out right now. Suggestions say the same.
docker compose start nutrient-calc
#    Then click "Update my totals" in the Food diary (or POST /api/meals/meals/recalculate-pending)
#    and everything catches up.

# 3. A database goes down
docker compose stop recommender-db
#    Result: only the Suggestions tab is affected. It says "Database unavailable, please retry
#    shortly". food-recommender stays running (/health gives 200) but /ready gives 503, which is
#    how Kubernetes will know to stop sending it requests.
curl.exe -i http://localhost:8080/api/recommend/ready
docker compose start recommender-db
#    Within a few seconds it's back to normal.
```

## Working on the website

The website is in `frontend/` (React and Vite, with Chart.js for the charts and Google's Firebase
library for logging in). All its colours and sizes are set once at the top of `src/styles.css`,
which also switches to dark mode when your computer is in dark mode. It's built into plain files
and served by its own small Nginx container.
To change it with instant reloading instead of rebuilding the container each time:

```bash
# Install the packages (only needed once)
#   --prefix frontend  run in the frontend folder
npm install --prefix frontend

# Start Vite's development server on http://localhost:5173. It passes /api calls on to the
# gateway, so the rest of the app needs to be running in Docker.
npm run dev --prefix frontend
```

When you're happy, `docker compose up --build -d frontend` puts the new version into the container.

## The data

The main food data is Australian: AUSNUT 2023 from Food Standards Australia New Zealand (3,741
foods with complete nutrient data, CC BY 4.0). USDA FoodData Central (public domain) fills in
everything else, including packaged foods with barcodes. Targets come from the Australian NHMRC
Nutrient Reference Values. The files are too big for git, so the repo has scripts to download them.

The last load put **1,030,440 rows** into the databases, including 47,334 foods and 864,594
nutrient values. The full counts, and how the data is cleaned, are in [etl/README.md](etl/README.md).

```bash
# Print the row counts again
docker compose run --rm etl --counts-only

# Open a SQL prompt in nutrient-calc's database (type \q to leave)
#   exec            run a command in a container that's already running
#   -U nutrient     log in as the "nutrient" user
#   -d nutrient_db  open the nutrient_db database
docker compose exec nutrient-db psql -U nutrient -d nutrient_db
```

## What's where

```
docker-compose.yml   runs the whole app on your computer
gateway/nginx.conf   sends /api/... to the right service, and everything else to the website
frontend/            the React website, and the Nginx that serves it
services/<name>/     one folder per service: code (app/), tests, database setup (db/init.sql)
etl/                 downloads and loads the food data; seed_demo_users.py makes the demo users
loadtest/            the load test
k8s/                 Kubernetes files for GKE, and the guide to deploying (k8s/README.md)
docs/                design notes
```
