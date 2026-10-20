# Running MacroScope on your own computer

> Part of the MacroScope docs. Start at the [README](../README.md), which also lists where everything else is.

The [README](../README.md) is the path to deploying MacroScope on Google Cloud, and its step 3
loads the food data into local databases with Docker Compose. This page is for running and using the
whole app locally (for development, or to try it before deploying). You need the `.env` file and
Google login from steps 1-2 of the README first.

The commands work in Windows PowerShell and the macOS/Linux Terminal. On macOS/Linux, type `python3`
instead of `python`. On a Mac, run `setopt interactivecomments` first, so zsh skips the `#`
comment lines in the blocks below when you paste them.

## First time

Run these from the project folder, in order.

```bash
# 1. Make your settings file from the template
cp .env.example .env

# 2. Make a random secret, then paste it into JWT_SECRET in the .env file.
#    Also put your Google project ID and Web API key into GOOGLE_PROJECT_ID and GOOGLE_API_KEY
#    (see step 1 of the README). On macOS/Linux use python3 here and in step 5.
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

```

7. Make the demo users, with 3 weeks of meals each (takes about a minute). `TODAY` is today's date
where you are (the container's clock is on UTC), and `--entrypoint python` runs this script
instead of the loader.

```powershell
# Windows (PowerShell)
docker compose run --rm -e TODAY=$(Get-Date -Format yyyy-MM-dd) --entrypoint python etl seed_demo_users.py
```

```bash
# macOS / Linux
docker compose run --rm -e TODAY=$(date +%F) --entrypoint python etl seed_demo_users.py
```

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

```powershell
# Windows (PowerShell). Type curl.exe: plain curl in Windows PowerShell is a different command.
# Ask a service for its version. The reply also says which container answered.
curl.exe http://localhost:8080/api/nutrients/version

# Check a service can reach its database. 200 means yes, 503 means no.
#   -i  show the status code as well as the reply
curl.exe -i http://localhost:8080/api/nutrients/ready
```

```bash
# macOS / Linux
curl http://localhost:8080/api/nutrients/version
curl -i http://localhost:8080/api/nutrients/ready
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
