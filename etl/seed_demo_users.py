"""Make 4 demo users with 3 weeks of realistic meals, through the real API (the same way the website
does it), so the dashboard, gaps and suggestions have something to show.

Each one is deliberately short on something:
    alex   eats mostly white bread, rice and chicken       -> short on magnesium, fibre, vitamin C and more
    priya  vegetarian, no legumes or fortified cereal      -> short on iron
    sam    no fish, eggs or mushrooms                      -> short on vitamin D
    jess   22 weeks pregnant, eats well, but no red meat   -> short on iron (pregnancy needs 27 mg a day)

It runs inside the etl container (no Python packages needed, only the standard library). Give it
today's date, because the container's clock is on UTC, which can be a day behind Australia:
    docker compose run --rm -e TODAY=2026-10-17 --entrypoint python etl seed_demo_users.py

Running it again is safe: each user's meals from the last 3 weeks are deleted and logged again.
The demo accounts are real accounts in your Google Identity Platform project, all with the same
password (DEMO_PASSWORD, printed at the end) so you can log in as them on the website.
"""
import json
import os
import random
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.getenv("GOOGLE_API_KEY", "")
PASSWORD = os.getenv("DEMO_PASSWORD", "MacroScope-demo-2026")
TODAY = os.getenv("TODAY")  # YYYY-MM-DD; if it isn't set, the computer's own date
DAYS = 21                 # 3 weeks of history before today
SKIP_CHANCE = 0.1         # now and then someone forgets to log a day

# AUSNUT 2023 foods by survey ID (these IDs never change), so the meals don't depend on search
FOODS = {
    "white bread": 12201011,          # Bread, white, commercial
    "wholemeal bread": 12203001,      # Bread, wholemeal, commercial
    "butter": 14101001,               # Butter, plain, salted
    "jam": 27201001,                  # Jam, berry
    "peanut butter": 22202004,        # Peanut butter, no added sugar or salt
    "flat white": 11202001,           # Coffee, flat white/cappuccino/latte, single shot & regular fat cow's milk
    "tea": 11101001,                  # Tea, black
    "milk": 19101002,                 # Milk, cow, fluid, regular fat (~3.5%)
    "porridge": 12601005,             # Porridge, rolled oats, made with cow's milk
    "muesli": 12511006,               # Muesli, commercial, untoasted or natural, dried fruit
    "ham": 18602001,                  # Ham, leg, lean
    "cheddar": 19401003,              # Cheese, cheddar, natural, plain
    "white rice": 12102003,           # Rice, white, cooked
    "pasta": 12401004,                # Pasta, white, plain, boiled, no added salt
    "chicken breast": 18301010,       # Chicken, breast, lean, baked, roasted, fried, grilled or BBQ'd, no added fat
    "beef mince": 18101013,           # Beef, mince, cooked, no added fat
    "canned tomato": 24602005,        # Tomato, whole, canned in tomato juice, undrained
    "potato": 24101016,               # Potato, peeled, boiled, microwaved or steamed, drained
    "lettuce": 24401006,              # Lettuce, raw
    "tomato": 24601002,               # Tomato, common, raw
    "cucumber": 24705020,             # Cucumber, raw
    "carrot": 24301004,               # Carrot, boiled, microwaved or steamed, drained
    "broccoli": 24202002,             # Broccoli, fresh, boiled, microwaved or steamed, drained
    "pumpkin": 24701004,              # Pumpkin, peeled, boiled, microwaved or steamed, drained
    "mixed veg": 24803008,            # Mixed vegetables, carrot, corn & peas/beans, cooked
    "apple": 16101015,                # Apple, raw, not further defined
    "banana": 16502001,               # Banana, cavendish, peeled, raw
    "orange": 16301001,               # Orange, navel, peeled, raw
    "kiwifruit": 16601005,            # Kiwifruit, green (hayward), peeled, raw
    "natural yoghurt": 19202001,      # Yoghurt, natural, reduced fat (~2%)
    "fruit yoghurt": 19204001,        # Yoghurt, flavoured/added fruit, reduced fat (2%)
    "salmon": 15101039,               # Salmon, boiled, microwaved, steamed or poached
    "tuna": 15401015,                 # Tuna, unflavoured, canned in water, drained
    "sweet potato": 24302027,         # Sweet potato, orange flesh, peeled, boiled, microwaved or steamed, drained
    "spinach": 24401016,              # Spinach, baby, fresh, raw
    "egg": 17101003,                  # Egg, chicken, whole, hard-boiled
}

# Each person: their profile, and a few choices for each meal as [(food, grams), ...].
# One choice is picked at random each day, and the amounts vary a little, like real eating.
USERS = [
    {
        "name": "alex",
        "email": "alex@macroscope-demo.test",
        "profile": {"sex": "male", "date_of_birth": "1997-03-12", "height_cm": 180, "weight_kg": 82,
                    "lifestyle": "mostly_seated", "exercise_sessions_per_week": 1, "goal": "maintain",
                    "diet": "omnivore"},
        "meals": {
            "breakfast": [
                [("white bread", 80), ("butter", 10), ("jam", 20), ("flat white", 250)],
                [("white bread", 80), ("peanut butter", 20), ("flat white", 250)],
            ],
            "lunch": [
                [("white bread", 80), ("ham", 50), ("cheddar", 25), ("lettuce", 15)],
                [("white rice", 250), ("chicken breast", 150)],
            ],
            "dinner": [
                [("white rice", 300), ("chicken breast", 180), ("carrot", 50)],
                [("pasta", 300), ("beef mince", 150), ("canned tomato", 120)],
                [("potato", 200), ("chicken breast", 200), ("butter", 10)],
            ],
            "snack": [
                [("apple", 150)],
                [("fruit yoghurt", 150)],
            ],
        },
        "recipe": ("Toast and coffee", [("white bread", 80), ("butter", 10), ("jam", 20), ("flat white", 250)]),
    },
    {
        "name": "priya",
        "email": "priya@macroscope-demo.test",
        "profile": {"sex": "female", "date_of_birth": "2001-08-03", "height_cm": 160, "weight_kg": 55,
                    "lifestyle": "seated_some_walking", "exercise_sessions_per_week": 2, "goal": "maintain",
                    "diet": "vegetarian"},
        "meals": {
            "breakfast": [
                [("porridge", 300), ("banana", 120)],
                [("white bread", 70), ("butter", 10), ("jam", 20), ("tea", 250), ("milk", 30)],
            ],
            "lunch": [
                [("white bread", 80), ("cheddar", 40), ("tomato", 60), ("cucumber", 40)],
                [("white rice", 250), ("natural yoghurt", 150), ("cucumber", 50)],
            ],
            "dinner": [
                [("pasta", 300), ("canned tomato", 150), ("cheddar", 30)],
                [("white rice", 300), ("potato", 150), ("pumpkin", 100), ("natural yoghurt", 100)],
            ],
            "snack": [
                [("fruit yoghurt", 170)],
                [("apple", 150)],
                [("milk", 250)],
            ],
        },
        "recipe": ("Porridge with banana", [("porridge", 300), ("banana", 120)]),
    },
    {
        "name": "sam",
        "email": "sam@macroscope-demo.test",
        "profile": {"sex": "female", "date_of_birth": "1990-11-20", "height_cm": 170, "weight_kg": 68,
                    "lifestyle": "standing_walking", "exercise_sessions_per_week": 3, "goal": "lose",
                    "diet": "omnivore"},
        "meals": {
            "breakfast": [
                [("muesli", 60), ("milk", 200), ("banana", 120)],
                [("wholemeal bread", 80), ("peanut butter", 20), ("flat white", 250)],
            ],
            "lunch": [
                [("wholemeal bread", 80), ("chicken breast", 80), ("lettuce", 20), ("tomato", 60)],
                [("white rice", 200), ("chicken breast", 120), ("broccoli", 100)],
            ],
            "dinner": [
                [("potato", 200), ("beef mince", 120), ("broccoli", 100), ("carrot", 80)],
                [("pasta", 250), ("beef mince", 120), ("canned tomato", 150)],
                [("sweet potato", 150), ("chicken breast", 150), ("mixed veg", 120)],
            ],
            "snack": [
                [("apple", 150)],
                [("natural yoghurt", 170)],
                [("orange", 150)],
            ],
        },
        "recipe": ("Muesli and banana", [("muesli", 60), ("milk", 200), ("banana", 120)]),
    },
    {
        "name": "jess",
        "email": "jess@macroscope-demo.test",
        "profile": {"sex": "female", "date_of_birth": "1994-06-15", "height_cm": 165, "weight_kg": 70,
                    "lifestyle": "seated_some_walking", "exercise_sessions_per_week": 2, "goal": "maintain",
                    "diet": "omnivore", "pre_pregnancy_weight_kg": 63},   # due_date is set below
        "meals": {
            "breakfast": [
                [("wholemeal bread", 80), ("peanut butter", 20), ("milk", 250)],
                [("porridge", 300), ("banana", 120)],
            ],
            "lunch": [
                [("wholemeal bread", 80), ("egg", 60), ("lettuce", 20), ("tomato", 60)],
                [("white rice", 200), ("tuna", 95), ("cucumber", 50)],
            ],
            "dinner": [
                [("salmon", 150), ("potato", 200), ("broccoli", 100)],
                [("chicken breast", 150), ("sweet potato", 150), ("spinach", 40)],
                [("pasta", 250), ("canned tomato", 150), ("cheddar", 30), ("mixed veg", 100)],
            ],
            "snack": [
                [("natural yoghurt", 170), ("kiwifruit", 75)],
                [("orange", 150)],
                [("apple", 150), ("cheddar", 25)],
            ],
        },
        "recipe": ("Salmon dinner", [("salmon", 150), ("potato", 200), ("broccoli", 100)]),
    },
]


# ---------------------------------------------------------------- talking to the API

def call(method: str, url: str, body=None, token: str | None = None):
    """Send one request and return (status, reply as JSON)."""
    request = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"null")


def login(email: str) -> str:
    """Log in to the demo account (making it first if it's new) and return a login token."""
    base = "https://identitytoolkit.googleapis.com/v1/accounts"
    body = {"email": email, "password": PASSWORD, "returnSecureToken": True}
    status, reply = call("POST", f"{base}:signUp?key={API_KEY}", body)
    if status == 400 and reply["error"]["message"] == "EMAIL_EXISTS":
        status, reply = call("POST", f"{base}:signInWithPassword?key={API_KEY}", body)
    if status != 200:
        sys.exit(f"Stopping: couldn't log in as {email}: {reply}")
    return reply["idToken"]


def items_for(choice, rng: random.Random) -> list[dict]:
    """The foods for one meal, with the amounts varied by up to 15% either way."""
    return [{"fdc_id": FOODS[food], "grams": round(grams * rng.uniform(0.85, 1.15))} for food, grams in choice]


def seed_user(user: dict, today: date):
    token = login(user["email"])
    _, me = call("GET", f"{GATEWAY}/api/meals/auth/me", token=token)
    uid = me["user_id"]

    profile = dict(user["profile"])
    if user["name"] == "jess":
        profile["due_date"] = str(today + timedelta(weeks=18))      # so she's 22 weeks along
    status, reply = call("PUT", f"{GATEWAY}/api/gaps/profile/{uid}", profile, token)
    if status != 200:
        sys.exit(f"Stopping: couldn't save {user['name']}'s profile: {reply}")

    # Start again from a clean slate, so running this twice doesn't double everything
    start = today - timedelta(days=DAYS)
    _, old_meals = call("GET", f"{GATEWAY}/api/meals/meals?start={start}&end={today}", token=token)
    for meal in old_meals:
        call("DELETE", f"{GATEWAY}/api/meals/meals/{meal['id']}", token=token)

    rng = random.Random(user["name"])     # the same "random" meals every time it's run
    logged_days = 0
    for offset in range(DAYS, -1, -1):
        day = today - timedelta(days=offset)
        if offset > 0 and rng.random() < SKIP_CHANCE:
            continue
        # Today only has breakfast and lunch so far, so the dashboard has something left to eat
        meal_types = ["breakfast", "lunch"] if offset == 0 else ["breakfast", "lunch", "dinner", "snack"]
        for meal_type in meal_types:
            choice = rng.choice(user["meals"][meal_type])
            status, reply = call("POST", f"{GATEWAY}/api/meals/meals",
                                 {"meal_date": str(day), "meal_type": meal_type, "items": items_for(choice, rng)}, token)
            if status != 201:
                sys.exit(f"Stopping: couldn't log a meal for {user['name']}: {reply}")
        logged_days += 1

    # One saved recipe each, so "log again in one click" has something to show
    recipe_name, recipe_items = user["recipe"]
    _, recipes = call("GET", f"{GATEWAY}/api/meals/recipes", token=token)
    if not any(r["name"] == recipe_name for r in recipes):
        call("POST", f"{GATEWAY}/api/meals/recipes",
             {"name": recipe_name, "items": [{"fdc_id": FOODS[f], "grams": g} for f, g in recipe_items]}, token)

    # What gap-analysis makes of it
    _, report = call("GET", f"{GATEWAY}/api/gaps/report/{uid}?date={today}", token=token)
    week = report["windows"][0]       # the last 7 days
    print(f"  {user['email']:30} {logged_days} days logged, gaps this week: {', '.join(week['top_gaps']) or 'none'}")


def main():
    if not API_KEY:
        sys.exit("Stopping: set GOOGLE_API_KEY (the Web API key from your .env file)")
    today = date.fromisoformat(TODAY) if TODAY else date.today()
    print(f"Making demo users through {GATEWAY}, with today as {today} ...")
    for user in USERS:
        seed_user(user, today)
    print(f"\nDone. Log in on the website as any of them with the password: {PASSWORD}")


if __name__ == "__main__":
    main()
