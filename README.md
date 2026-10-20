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
does this job). The services talk to each other with plain REST calls; there are no message
queues. More detail on the design is in [docs/architecture.md](docs/architecture.md).

```
browser ──► gateway :8080 ──┬─ /               ─► frontend (React, served by Nginx)
                            ├─ /api/meals      ─► meal-logging     ─► meal-db + redis
                            ├─ /api/nutrients  ─► nutrient-calc    ─► nutrient-db
                            ├─ /api/gaps       ─► gap-analysis     ─► gap-db
                            └─ /api/recommend  ─► food-recommender ─► recommender-db
```

It runs on your own computer with Docker Compose, and on Google Kubernetes Engine (GKE) across 2 VMs.
Setting it up on your computer comes first; the cloud deployment builds on it.

## What you need

- **Docker Desktop.** It includes Docker Compose.
- **Python 3.12 or newer.** You only need this to download the food data. Everything else runs in Docker.
- **For the cloud deployment only: the Google Cloud CLI (`gcloud`).** `kubectl` comes with
  Docker Desktop. Step 0 of [k8s/README.md](k8s/README.md) installs it.
- **A Google Cloud project with Identity Platform turned on.** People sign up and log in through
  Google, even when the app runs on your own computer. See "Setting up Google login" below.

On Windows PowerShell, type `curl.exe`, not `curl`. Plain `curl` in PowerShell is a different
command.

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

## Setting it up on your computer (first time)

Run these from the project folder, in order.

```bash
# 1. Make your settings file from the template
cp .env.example .env

# 2. Make a random secret, then paste it into JWT_SECRET in the .env file.
#    Also put your Google project ID and Web API key into GOOGLE_PROJECT_ID and GOOGLE_API_KEY
#    (see "Setting up Google login" above).
python -c "import secrets; print(secrets.token_hex(32))"

# 3. Build and start everything
#   --build  build the images first, so they include the latest code
#   -d       run in the background and give you the terminal back
docker compose up --build -d

# 4. Check everything is running. After about 30 seconds, each one should say "healthy".
docker compose ps

# 5. Download the food data into etl/data/ (only needed once)
#    The Australian data (about 6 MB; already there if you're working from the submission ZIP)
#    and the USDA data (about 440 MB)
python etl/download_ausnut.py
python etl/download_usda.py

# 6. The ETL: read the downloaded files, clean them, and load 1,030,440 rows into the 4 databases
#    (takes about 6 minutes, only needed once). The etl container runs etl/load_usda.py, which
#    loads the AUSNUT data as well as the USDA data.
#   run   start a one-off container for the loader
#   --rm  delete that container when it's finished
docker compose run --rm etl

# 7. Make the demo users, with 3 weeks of meals each (takes about a minute)
#   -e TODAY=...           today's date where you are (the container's clock is on UTC)
#   --entrypoint python    run this script instead of the loader
docker compose run --rm -e TODAY=<YYYY-MM-DD> --entrypoint python etl seed_demo_users.py
```

In PowerShell you can fill in today's date for step 7 automatically:
`docker compose run --rm -e TODAY=$(Get-Date -Format yyyy-MM-dd) --entrypoint python etl seed_demo_users.py`

That's it. Open **http://localhost:8080**. The databases keep their data, so next time you only
need `docker compose up -d`.

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

## Deploying to Google Kubernetes Engine (GKE)

MacroScope runs on GKE in Sydney (`australia-southeast1`): 2 identical VMs, the 4 Postgres databases
as StatefulSets with their own disks, Redis, and an HTTPS Ingress. It's live at
**https://34-120-54-167.nip.io**, and that's where it's demonstrated. [k8s/README.md](k8s/README.md)
is the record of how it was deployed, with every command commented, and it still works if followed
in another project.

**Set it up on your computer first** ("Setting it up on your computer" above). The cloud deployment builds its images
from this folder, reads the Web API key from `.env`, and copies the food data and demo users from
your local databases into the cloud ones (step 7 of the guide).

The order in [k8s/README.md](k8s/README.md):

1. Install the Google Cloud CLI and log in, and turn on the Google Cloud services (steps 0-1)
2. Build the images and upload them to Artifact Registry (step 2)
3. Make the cluster with its 2 VMs, and reserve the IP address (steps 3-4)
4. Make the settings and secrets, then start everything with `kubectl apply -f k8s/` (steps 5-6)
5. Copy the data in from your local databases (step 7)
6. Add the domain to Google sign-in and turn on HTTPS only (steps 8-9)

It ends with the demo commands (scaling, pod failure, VM failure, rolling update and rollback), and
how to pause the cluster between sessions to save credits.

## The data

The main food data is Australian: AUSNUT 2023 from Food Standards Australia New Zealand (3,741
foods with complete nutrient data, CC BY 4.0). USDA FoodData Central (public domain) fills in
everything else, including packaged foods with barcodes. Targets come from the Australian NHMRC
Nutrient Reference Values.

`etl/data/` isn't in git, because the files are too big. The submission ZIP includes the AUSNUT
files (`etl/data/ausnut/`, about 6 MB), so only the USDA data needs downloading. The last load put
**1,030,440 rows** into the databases, including 47,334 foods and 864,594 nutrient values. The full
counts, and how the data is cleaned, are in [etl/README.md](etl/README.md).

```bash
# Print the row counts again
#   --counts-only  don't load anything, just count
docker compose run --rm etl --counts-only
```

## More detail

| File | What's in it |
|---|---|
| [k8s/README.md](k8s/README.md) | deploying to GKE, step by step, and the cloud demo commands |
| [docs/architecture.md](docs/architecture.md) | how it's designed and why, including logins and the GKE setup |
| [docs/api.md](docs/api.md) | every API endpoint, and calling them from PowerShell |
| [docs/testing.md](docs/testing.md) | running the tests, the load test and failure demos (with results), and working on the website |
| [etl/README.md](etl/README.md) | the food data: where it comes from, how it's cleaned, row counts |

## What's where

```
docker-compose.yml   runs the whole app on your computer
gateway/nginx.conf   sends /api/... to the right service, and everything else to the website
frontend/            the React website, and the Nginx that serves it
services/<name>/     one folder per service: code (app/), tests, database setup (db/init.sql)
etl/                 downloads and loads the food data; seed_demo_users.py makes the demo users
loadtest/            the load test
k8s/                 Kubernetes files for GKE, and the guide to deploying (k8s/README.md)
docs/                design notes, the API, tests and demos
```
