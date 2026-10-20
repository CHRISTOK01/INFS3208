# Tests, demos and working on the code

> Part of the MacroScope docs. Start at the [README](../README.md), which also lists where everything else is.

These assume the app is running on your computer and the data is loaded (see
[running-locally.md](running-locally.md)). The same demos on GKE are under "Demo commands" in the
[README](../README.md).

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
