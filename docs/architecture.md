# MacroScope architecture notes

## How a request gets around

```
browser ──► gateway (Nginx :8080)   (on GKE this becomes the Ingress)
              ├─ /api/meals/...      ─► meal-logging     (8001) ─► meal-db (meal_db) + redis
              ├─ /api/nutrients/...  ─► nutrient-calc    (8002) ─► nutrient-db (nutrient_db)
              ├─ /api/gaps/...       ─► gap-analysis     (8003) ─► gap-db (gap_db)
              ├─ /api/recommend/...  ─► food-recommender (8004) ─► recommender-db (recommender_db)
              └─ /                   ─► frontend         (Nginx serving the React build)
```

When one service needs something from another, it makes a normal REST call using the other
service's name, for example `http://nutrient-calc:8002`. The addresses come from environment variables.

- meal-logging calls nutrient-calc with `PUT /api/nutrients/daily/{user}/{date}`, sending all of that day's food
- gap-analysis calls nutrient-calc with `GET /api/nutrients/daily/{user}?start&end` to get the recent history
- food-recommender calls gap-analysis with `GET /api/gaps/report/{user}` (the gaps) and `GET /api/gaps/today/{user}` (calories left, today's amounts and limits, diet and pregnancy)

There are no message queues. Every call is a plain request that waits for its answer.

## Design choices, and why we made them

**Every service has its own Postgres container.** A service owns its data. If another service
needs it, it asks through the API rather than reading the database directly.

**Australian food data comes first.** AUSNUT 2023 (FSANZ) has 3,741 foods as Australians eat them,
with every nutrient filled in, including iodine. US foods are fortified differently (US rice and
flour have added iron and folate; Australian bread has iodised salt and folic acid), so US data
would get those wrong for people here. USDA is still loaded as a fallback for foods AUSNUT doesn't
have, and for barcodes.

**Services are linked by IDs, not shared tables.** Foods are matched across services by `fdc_id`
(the USDA ID, or the 8-digit AUSNUT survey ID for Australian foods), and nutrients by a short name
such as `magnesium`. A few columns (like food names) are
copied into more than one database on purpose, so no service has to reach into another's tables.

**Logins are handled by Google, not by us.** See "Logging in" below.

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

**Each daily total also says how much of it we actually know (`coverage_pct`).** Australian foods
have every nutrient (apart from copper, manganese and pantothenic acid for some of them), but USDA's
packaged (Branded) foods only list what's on the label, often just calories, macros, sodium,
calcium and iron.

So `is_complete` on its own is too harsh. One muesli bar with no magnesium on its label would mark
the whole day's magnesium as incomplete. `coverage_pct` is the share of the day's food, by weight,
that had a value. If it's 95%, the total is close to the truth. If it's 20%, the total is only a
"you had at least this much" figure. gap-analysis uses it to decide between "low" and "not
enough data" (see the gap-analysis rules below).

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

People sign up and log in through **Google Cloud Identity Platform**, on the website. Google
checks their password (or their Google account), and gives the browser a login token signed with
Google's private key. The website sends that token with every request, and every service checks it
using Google's public keys. We never see or store anyone's password, and there's no users table.

A service only accepts a Google token if:

- Google really signed it (checked with Google's public keys, which we download and keep for an hour)
- it was made for **our** project (`GOOGLE_PROJECT_ID`), not some other app that uses Google login
- it hasn't expired (Google's tokens last an hour, and the website quietly gets a new one)
- (we allow 30 seconds of difference between Google's clock and ours, because a brand-new token
  can otherwise look like it was made "in the future" and get rejected straight after signing up)

**On the website**, Google's Firebase library does the logging in (email and password, or the
"Continue with Google" button). It keeps the person logged in between visits and hands the website
a fresh token whenever it asks, renewing it before it expires. The website needs the project ID
and the public Web API key to start it, and gets them from `GET /api/meals/auth/config` when it
loads, rather than having them built in. That way the same website image works on any computer or
cluster, just like the services.

The token's `sub` is the person's Google ID (a string like `"Xy7kP2..."`). Every service stores
people's data under that ID, so the `user_id` columns are text.

**Our services also need to talk to each other**, for example meal-logging sending a day's food
to nutrient-calc. No person is involved there, so meal-logging makes its own short-lived (60
second) token, signed with the shared `JWT_SECRET` and marked `role: service`. A service token can
act for any user. To stop the shared secret being used to pretend to be a person, a token signed
with it only counts if it says `role: service`.

The two are easy to tell apart: Google's tokens use RS256 (a private key only Google has), and
ours use HS256 (the shared secret).

People can only see and change their own data. If Google's keys can't be downloaded, requests that
need a login get a 503 ("can't check logins right now") rather than a confusing 401.

**On Kubernetes**, `JWT_SECRET` goes into a Kubernetes Secret, and `GOOGLE_PROJECT_ID` and
`GOOGLE_API_KEY` into a ConfigMap. The code doesn't change.

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

**Search tries to find what people mean**, not just names containing the words. The full order
is in `search_foods` in `app/repo.py`. The main ideas:

| Rule | Example |
|---|---|
| Plural endings are cut off, so both data sets match | "strawberries" finds AUSNUT's "Strawberry, raw" and USDA's "Strawberries, raw" |
| Cooking words mean "cooked first" instead of having to be in the name, because AUSNUT and USDA describe cooking differently | "rice white boiled" finds "Rice, white, cooked"; "boiled" doesn't count "parboiled" |
| ...unless the whole search is the start of a name | "baked beans" finds "Baked beans, canned in tomato sauce" |
| Main entries come before things that only mention the food | "banana" finds "Banana, cavendish, raw" before "Banana chip"; "egg" skips "Eggplant" |
| Australian foods first, then USDA | |
| FSANZ's "not further defined" foods, its average of the usual kinds of a food | "apple" finds "Apple, raw, not further defined" |
| Raw before cooked when you haven't said | "potato" finds the raw potato, not chips |

Every remaining word has to appear in the name, and the trigram index keeps this to a few
milliseconds.

**Barcodes** are compared with leading zeros removed, because USDA stores some with extra zeros
(`0000020048556`) that a scanner wouldn't give you.

## gap-analysis: targets and gaps

**Targets are worked out fresh for the day being looked at**, from the profile and the NHMRC
table, rather than stored. That's because they change on their own: age moves on with each
birthday, and pregnancy needs change with each trimester (worked out from the due date). The
profile asks for sex, date of birth, height, weight, a normal day's activity (four choices, each
with an example), how many times a week they exercise, their goal (lose, maintain or gain), their
diet (omnivore, vegetarian or vegan), and, for women, a due date or whether they're breastfeeding.

Every number comes with a note of where it came from. All the rules and their sources are at the
top of `app/targets.py`:

| Target | How it's worked out | Source |
|---|---|---|
| Energy | BMR (Mifflin-St Jeor) x physical activity level, which is NHMRC's own method | NHMRC; Frankenfield 2005 for the equation |
| Activity level | a normal day sets the start: 1.45 mostly sitting, 1.55 sitting with some walking, 1.70 on your feet, 1.90 heavy work (inside FAO's sedentary 1.40-1.69 and moderately active 1.70-1.99 ranges). Each weekly exercise session (45 min) adds about 0.02, because FAO says an hour a day adds about 0.2. Capped at 2.4 | FAO/WHO/UNU 2004 (Table 5.3), which NHMRC's energy values are based on |
| Pregnancy and breastfeeding | +0 / +1.4 / +1.9 MJ a day by trimester, +2.0 MJ breastfeeding; BMR uses the weight before pregnancy | NHMRC |
| Goal | lose: -500 kcal a day (about 0.5 kg a week), gain: +250 kcal; never below BMR; no loss or gain targets while pregnant or breastfeeding | about 7,700 kcal per kg of body fat |
| Protein | the NHMRC RDI per kg (higher in pregnancy and breastfeeding), raised to 1.6 g/kg when losing or gaining and 1.4 g/kg when training 3+ times a week, kept within 15-25% of energy | NHMRC; Morton 2018; ISSN 2017 |
| Fat, carbs | fat 30% of energy (NHMRC range 20-35%), carbs the rest, with a note if carbs fall outside 45-65% | NHMRC |
| Saturated fat, free sugars | each under 10% of energy | NHMRC; WHO 2015 |
| Alcohol | adults at most 10 standard drinks a week (14.3 g a day on average); none under 18, pregnant or breastfeeding | NHMRC 2020 |
| Caffeine | 400 mg adults, 200 mg in pregnancy, 3 mg per kg under 18 | FSANZ; EFSA 2015 |
| Vitamins, minerals, fibre, omega-3 | the NHMRC RDI or AI for the person's age, sex and life stage, plus NHMRC's long-term "aim" where there is one (like 28 g of fibre for women) | NHMRC |
| Iron and zinc for vegetarians and vegans | x 1.8 and x 1.5, because less is absorbed from plants | NHMRC |

Sex is asked as male or female only because the NHMRC tables and the calorie equation are split
that way. Vitamin K and choline aren't tracked: the Australian food data doesn't have them.

**The report** (`GET /api/gaps/report/{user}?date=...`) looks at the 7 full days before the given
date: long enough to see a pattern, short enough to do something about this week. Each day on its
own is handled by `GET /api/gaps/today/...`. Today isn't included, because a half-logged day would make you look short on
everything. Fibre, vitamins, minerals and omega-3 are checked against their targets, and the things
with only a limit (sodium, saturated fat, free sugars, alcohol, caffeine) against that limit.
Calories and macros are a daily budget (`GET /api/gaps/today/...`). For each nutrient:

| Rule | Why |
|---|---|
| Every day with food logged counts | days with nothing logged don't, because not logging isn't the same as not eating |
| At least 3 days with data, or the nutrient is "unknown" | too little to judge |
| Days where we know the nutrient for at least 80% of the food give a real total | if there are 3 or more of those, only they are used |
| Otherwise the partial totals are used as a minimum (`"is_minimum": true`) | the foods with no value could only add to them |
| **gap** if the average is under 70% of the target, from real totals only | a minimum that looks low might not be, so that's "unknown" instead |
| **ok** if the average reaches 70% of the target, even as a minimum | NHMRC targets cover nearly everyone, so a bit under isn't a worry |
| **excess** if the average is above the upper limit, with a count of the days over it | |
| Vitamin A is never called an excess | its 3,000 µg upper limit is for retinol (from animal foods), but our total also counts beta-carotene from plants, which has no limit |
| Sodium has no target, only an upper limit (2,000 mg for adults) | NHMRC only gives a range for the minimum, and the worry with sodium is too much |

It also says how many days met the target, and lists the 5 biggest gaps (lowest % first). The
food-recommender uses those.

**If nutrient-calc is down**, the report sends the last saved results from `gap_results`, marked
`"stale": true`, instead of an error. `GET /today` can't do that (there's nothing saved for today),
so it replies 503.

**gap-analysis asks nutrient-calc with a service token**, after checking the person is allowed to
see that user's data. That way the user's own login token doesn't need to be passed along.

## food-recommender: suggesting foods

`GET /api/recommend/foods/{user}?date=...&period=today|week` works in one of two ways, because the
aim is to hit your targets every day, with a weekly view for catching up:

| `period` | What it fills | Where the "shortfall" comes from |
|---|---|---|
| `today` (the default) | everything you haven't reached yet today | target minus what you've eaten today, for protein, carbs, fat, fibre and every vitamin, mineral and omega-3 below its target, using the foods that have a value for each. Energy isn't filled: it's the budget no suggestion may go over |
| `week` | what you've been short on lately | target minus your daily average over the last 7 days, for the biggest gaps in the report (needs 3 days logged) |

Either way it asks gap-analysis for today (the calories left, what's been eaten so far against
each limit, and the person's diet and pregnancy), and for `week` the 7-day report as well. It then
picks foods from its own copy of the food data. All the rules are in `app/rules.py`. Each
suggestion lists the 4 nutrients it helps most with, but its score counts all of them.

**Only Australian (AUSNUT) foods are suggested.** FSANZ tags every AUSNUT food with its Australian
Dietary Guidelines food group code (like 301 "Fresh/canned fruit") and says whether it's a
"discretionary" (sometimes) food. That lets us stick to everyday foods using FSANZ's own judgement
rather than a list we made up. They also have a value for nearly every nutrient, so the scores are
fair.

**Everything is worked out on one standard serve** from the dietary guidelines: 75 g of
vegetables, 150 g of fruit, a 40 g slice of bread, 65 g of cooked red meat, 80 g of poultry, 100 g
of fish, 2 eggs (120 g), 30 g of nuts, 170 g of tofu, a 250 ml cup of milk, 40 g of cheese, 200 g of
yoghurt, and so on (the full list is `STANDARD_SERVES` in `rules.py`, from eatforhealth.gov.au). We
tried the first portion size AUSNUT lists for each food first, but that's often the whole thing
("1 whole duck (730 g)", "1 cabbage (1.4 kg)"), so the scores were silly.

| Rule | Why |
|---|---|
| Only non-discretionary foods with a standard serve | so no cake for iron, and no mixed dishes, juice, dried fruit (the guidelines say only occasionally), flour or oils |
| No foods for babies or toddlers, medical drinks, or wild-harvested and game foods | real foods, but odd to suggest to most people |
| No ingredients or concentrated forms (dried mushroom, garlic, egg yolk, wheat germ, popcorn...) | nobody eats a whole standard serve of them; dried seeds are fine |
| No raw or dry forms of foods you'd cook (raw chicken, dry rice, dried lentils, raw potato) | raw fruit, vegetables, nuts and seeds are fine |
| Vegetarians get no meat or fish; vegans also no eggs or dairy (plant milks are fine) | worked out from the food group code, e.g. 5011 is meat and 4037 is calcium-enriched plant milk |
| In pregnancy, nothing FSANZ advises against: soft cheeses, pate, smoked seafood, sprouts, rockmelon (listeria), and shark, billfish, orange roughy and catfish (mercury) | FSANZ listeria and mercury-in-fish advice |
| A serve can't take today's total over a limit (sodium, caffeine, iron's upper limit...). Once you're already over, a serve with up to 10% of the limit is still fine | otherwise one salty meal would rule out nearly every food for the rest of the day. A limit of zero (alcohol in pregnancy) still allows none. The vitamin A limit is only checked for animal foods, because it's for retinol and plants have beta-carotene instead |
| A serve can't have more energy than is left today (but 150 kcal is always allowed) | so there's still something to suggest once the day's energy is used up |
| It has to make up at least 10% of one shortfall | otherwise it's not really helping |

**The score:** for each gap, how much of the daily shortfall (target minus average) one serve makes
up, counted up to 100%, all added together. A food that helps with two gaps beats one that helps
with one, and going far past what's needed doesn't earn extra. Ties go to the food with less
energy. If a food has no value for a nutrient, that nutrient just doesn't count for it; unknown is
never zero.

**For variety**, only the best food of each kind is kept (the part of the name before the first
comma, so one "Beef" not five cuts of it), and at most 3 come from each food group.

Each suggestion explains itself, like "A standard serve (100 g) gives 8.8 ug of vitamin B12 (100%
of what you're short each day), 114 ug of selenium (100%) and 5 ug of vitamin D (99%), for 124
kcal." (that one is cooked sardines).

**If nothing fits**, the first note says why, using the most common reason that's about today (like "most foods would take you over your limit for sodium today").

**If gap-analysis is down** it replies 503, and 404 if the person hasn't filled in their profile.
Adding `&nutrient=iron` skips the gaps and finds good sources of that nutrient, with the whole daily
target as the "shortfall".

## The website

The website (`frontend/`) is a React app built with Vite. It's kept simple: plain React hooks for
state, and one small `fetch` wrapper (`src/api.js`) that adds the login token to each request and
turns errors into readable messages. The only libraries are Chart.js (for the charts), Firebase
(for logging in) and two font packages, which are bundled into the build so the site never calls
Google Fonts.

**The look** comes from one stylesheet (`src/styles.css`). Every colour, size and shadow is a
variable set once at the top, and dark mode just gives those variables different values. Each macro
has one colour used everywhere (protein is always blue, for example), coral always means "short
on", and amber means "near a limit". The small shared pieces (icons, meters, the energy ring,
segmented controls, pop-up notices, loading placeholders) are in `src/components/`.

**Every API address is relative** (`/api/meals/...`, with no server name), so the browser sends it
to whatever served the page: the gateway here, the Ingress on Kubernetes. The same build works in
both, and there's no CORS to set up, because the page and the API come from the same place.

**It's built into plain files** in a two-stage Docker build: a Node image runs `npm ci` and
`vite build`, then only the built files are copied into a small Nginx image. Nginx sends any
unknown path back to `index.html`, so reloading the page anywhere still works. `index.html` is
never cached and the other files have a fingerprint in their names, so a new version shows up
straight away after a rolling update.

**It copes with parts of the app being down.** The dashboard asks for today and the 7-day report
separately, so if one fails the other still shows. A meal saved while nutrient-calc is down shows
"totals pending", with a button to catch up. A report sent from the last saved results says it's
out of date.

**The footer** checks each service's `/version` every 30 seconds and shows the `X-Served-By` header
from the last answer, so you can watch load balancing, a rolling update or a rollback happen.

## Demo users and the load test

`etl/seed_demo_users.py` makes 4 demo users through the real API, exactly as the website would:
it logs in through Google's login API (making the account the first time), saves a profile, and
logs 3 weeks of meals with `POST /api/meals/meals`. Each person's meals are chosen to leave a
specific gap (magnesium, iron, vitamin D, and iron in pregnancy). It uses fixed AUSNUT food IDs,
and the same random seed each time, so running it again gives the same results.

`loadtest/loadtest.py` runs any number of simulated people at once (one thread each), each
searching, logging a meal (which makes meal-logging call nutrient-calc) and asking nutrient-calc to
add up some food. It reports requests a second, median and 95th percentile times, failures, and how
the requests were shared between copies of each service. Both scripts only use Python's standard
library.

**The load test's compose entry has no `depends_on` on purpose.** `docker compose run` starts the
dependencies of what it runs, and starting the services puts any you've scaled up back to one
copy, which would spoil a load-balancing demo.
