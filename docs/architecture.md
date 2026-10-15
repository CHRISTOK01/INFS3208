# MacroScope architecture notes

## How a request gets around

```
browser ──► gateway (Nginx :8080)   (on GKE this becomes the Ingress)
              ├─ /api/meals/...      ─► meal-logging     (8001) ─► meal-db (meal_db) + redis
              ├─ /api/nutrients/...  ─► nutrient-calc    (8002) ─► nutrient-db (nutrient_db)
              ├─ /api/gaps/...       ─► gap-analysis     (8003) ─► gap-db (gap_db)
              ├─ /api/recommend/...  ─► food-recommender (8004) ─► recommender-db (recommender_db)
              └─ /                   ─► frontend (Nginx serving the React build)  [phase 4]
```

When one service needs something from another, it makes a normal REST call using the other
service's name, for example `http://nutrient-calc:8002`. The addresses come from environment variables.

- meal-logging calls nutrient-calc with `PUT /api/nutrients/daily/{user}/{date}`, sending all of that day's food
- gap-analysis will call nutrient-calc with `GET /api/nutrients/daily/{user}?start&end` to get the recent history (not built yet)
- food-recommender will ask gap-analysis for the user's biggest gaps and how many calories they have left (not built yet)

There are no message queues. Every call is a plain request that waits for its answer.

## Design choices, and why we made them

**Every service has its own Postgres container.** A service owns its data. If another service
needs it, it asks through the API rather than reading the database directly.

**Services are linked by IDs, not shared tables.** Foods are matched across services by their USDA
`fdc_id`, and nutrients by a short name such as `magnesium`. A few columns (like food names) are
copied into more than one database on purpose, so no service has to reach into another's tables.

**Each service answers on its own path, like `/api/nutrients/...`.** The GKE Ingress doesn't
rewrite paths, so our local gateway doesn't either. That way the URLs are the same on a laptop and
in the cloud.

**`/health`, `/ready` and `/version` exist twice.** They're at the root so Kubernetes can probe
them, and again under the service's path so you can reach them through the gateway. The frontend
uses the second copy to show the version in its footer.

**`/health` doesn't check the database, but `/ready` does.** If the database goes down, we want
Kubernetes to stop sending traffic to the pod, not to keep restarting a pod that's actually fine.

**Every response has an `X-Served-By` header** holding the container ID (or pod name on Kubernetes).
It shows which copy of a service answered, which makes load balancing visible in the demo.

**nutrient-calc recalculates a whole day at a time.** meal-logging always sends everything eaten
that day, not just the new meal. So if a call is retried, or replayed later to catch up, the total
comes out the same and nothing gets counted twice.

**Unknown values are never treated as zero.** If a food has no value for a nutrient, there's simply
no row for it in `food_nutrient`. Daily totals then show the amount as `NULL` with `is_complete =
false`. Otherwise someone could be told they're low on a nutrient just because the data was missing.

**Each daily total also says how much of it we actually know (`coverage_pct`).** A lot of
nutrients are missing from the data, mostly because packaged (Branded) foods only list a few things
on the label. Here's how many of our 43,593 foods have a value, from the last load:

| Nutrient | Foods with a value |
|---|---|
| energy, protein, carbs, fat, sodium, calcium, iron | about 98 to 100% |
| potassium, vitamin C, vitamin D | about 60 to 70% |
| magnesium, zinc, phosphorus, B vitamins, folate, vitamin A | about 30% (about 90% of generic foods) |
| manganese, pantothenic acid | about 15% |
| iodine | 0.3% |

So `is_complete` on its own is too harsh. One muesli bar with no magnesium on its label would mark
the whole day's magnesium as incomplete. `coverage_pct` is the share of the day's food, by weight,
that had a value. If it's 95%, the total is close to the truth. If it's 20%, the total is only a
"you had at least this much" figure. gap-analysis will use it to decide between "low" and "not
enough data".

**Iodine will be left out of gap analysis and recommendations.** USDA has hardly any iodine data,
so it would show as unknown almost every day. nutrient-calc still stores and reports what there is.

**Plain SQL with psycopg 3, no ORM.** The SQL stays visible and easy to explain, and psycopg's
built-in COPY support makes bulk loading the USDA data fast.

**The gateway looks up service addresses every 10 seconds.** It uses Docker's DNS server and keeps
the service addresses in variables. Because of that, the gateway still starts if a service is down,
and it spreads requests across all the copies when you scale a service up.

**Services don't publish ports to your machine.** Everything goes through the gateway on port 8080.
If each copy of a service tried to grab the same port, `docker compose up --scale` couldn't start
more than one.

**Shutting down cleanly.** uvicorn is the container's main process, so it gets the stop signal
straight away. It finishes the requests it's already handling (for up to 10 seconds), and then the
service closes its database connections.

**All settings come from environment variables.** That means the exact same image runs in Docker
Compose and on Kubernetes, where the settings will come from a ConfigMap and a Secret.

## Logging in (auth)

meal-logging hands out JWTs (JSON Web Tokens), signed with the shared `JWT_SECRET`. The secret has
to be at least 32 characters, and every service gets it from its environment.

A token says three things about whoever holds it:

- `sub`: the user's ID, as a string
- `exp`: when the token stops working
- `role`: either `user` (a person) or `service` (one of our services acting behind the scenes)

People can only see and change their own data. A `service` token is allowed to act for any user.
meal-logging makes a short-lived (60 second) one every time it sends a day's food to nutrient-calc.

Passwords are stored as bcrypt hashes, never as the password itself.

## meal-logging: keeping nutrient-calc up to date

When someone adds or deletes food, meal-logging:

1. saves the change and adds that day to the `pending_days` list, then commits both together
2. sends the whole day to nutrient-calc (`PUT /api/nutrients/daily/{user}/{date}`)
3. if that works, takes the day off the list and marks its items `calc_status = 'done'`

meal-logging doesn't need nutrient-calc to start or to save meals. That's why `docker-compose.yml`
doesn't make it wait for nutrient-calc.

If nutrient-calc is down, step 3 doesn't happen. The meal is still saved, the reply says
`"calc_status": "pending"`, and `POST /api/meals/meals/recalculate-pending` sends the waiting days
later. We need a list of days, not just `calc_status` on each item: if you delete the only meal on
a day, there are no items left to mark, but nutrient-calc still has the old totals.

**One change to a day at a time.** Before changing or sending a day, meal-logging takes a lock
named after that user and day (a Postgres "advisory lock", `pg_advisory_xact_lock`). Without it,
two meals saved at the same moment could each send nutrient-calc a day that's missing the other
one. The lock is kept in the database, so it works however many copies of meal-logging are running.

**Food search is cached in Redis for an hour.** The `X-Cache` header on a search says `HIT` or
`MISS`. If Redis is down, searches go straight to the database. After a Redis error, meal-logging
leaves Redis alone for 30 seconds, so only one search waits for it to fail.

**Search order:** foods matching your raw/cooked choice, then names starting with the first word
you typed, then Foundation, SR Legacy, FNDDS, Branded, then the closest match. Every word you type
has to appear in the name, and the trigram index keeps this to a few milliseconds.

**Barcodes** are compared with leading zeros removed, because USDA stores some with extra zeros
(`0000020048556`) that a scanner wouldn't give you.
