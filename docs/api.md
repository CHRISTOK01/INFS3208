# MacroScope API

> Part of the MacroScope docs. Start at the [README](../README.md), which also lists where everything else is.

Every service is reached through the gateway (`http://localhost:8080` on your computer, or
`https://34-120-54-167.nip.io` on GKE). Each one also has a page where you can try its API in the
browser, for example http://localhost:8080/api/nutrients/docs (swap `nutrients` for `meals`, `gaps`
or `recommend`).

## The endpoints

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
