"""Load test: lots of people logging meals and working out nutrients at once.

Each simulated user goes round and round doing what people do most:
    1. search for a food                       GET  /api/meals/foods/search   (mostly from the Redis cache)
    2. log a meal of 3 foods                   POST /api/meals/meals          (meal-logging, which then calls nutrient-calc)
    3. work out the nutrients in some food     POST /api/nutrients/calculate  (nutrient-calc)

At the end it prints how many requests worked, how fast they were, and which containers (or
Kubernetes pods) answered them. With several copies of a service running, you can see the work
being shared between them.

It logs in as its own test account (made the first time), and logs its meals on days in the year
2000, so they never mix with real ones. They're deleted again at the end.

Only the Python standard library is used. Run it from the project folder:
    docker compose run --rm loadtest                          # 20 users for 60 seconds
    docker compose run --rm loadtest --users 50 --seconds 120
"""
import argparse
import json
import os
import random
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
API_KEY = os.getenv("GOOGLE_API_KEY", "")
EMAIL = "loadtest@macroscope-demo.test"
PASSWORD = os.getenv("DEMO_PASSWORD", "MacroScope-demo-2026")
FIRST_DAY = date(2000, 1, 1)     # load test meals go on days in 2000, one day per simulated user

SEARCHES = ["banana", "apple", "rice white boiled", "chicken breast", "milk", "bread wholemeal",
            "egg boiled", "broccoli", "salmon", "yoghurt natural", "pasta", "potato"]
# A few everyday AUSNUT foods by survey ID (banana, white bread, cooked rice, chicken breast, milk,
# broccoli, apple, natural yoghurt)
FOODS = [16502001, 12201011, 12102003, 18301010, 19101002, 24202002, 16101015, 19202001]


def call(method, path, body=None, token=None, url=None):
    """Send one request. Returns (status, X-Served-By, seconds taken, reply)."""
    request = urllib.request.Request(url or GATEWAY + path, method=method,
                                     data=json.dumps(body).encode() if body is not None else None)
    request.add_header("Content-Type", "application/json")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            return response.status, response.headers.get("X-Served-By"), time.perf_counter() - start, data
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get("X-Served-By"), time.perf_counter() - start, error.read()
    except OSError:
        return 0, None, time.perf_counter() - start, b""    # couldn't connect at all, or timed out


def login() -> str:
    base = "https://identitytoolkit.googleapis.com/v1/accounts"
    body = {"email": EMAIL, "password": PASSWORD, "returnSecureToken": True}
    status, _, _, data = call("POST", "", body, url=f"{base}:signUp?key={API_KEY}")
    if status == 400 and b"EMAIL_EXISTS" in data:
        status, _, _, data = call("POST", "", body, url=f"{base}:signInWithPassword?key={API_KEY}")
    if status != 200:
        sys.exit(f"Stopping: couldn't log in the load test account: {data[:200]}")
    return json.loads(data)["idToken"]


class Results:
    """Everything the users measured. The lock stops two threads writing at the same moment."""

    def __init__(self):
        self.lock = threading.Lock()
        self.times = defaultdict(list)          # "POST /api/meals/meals" -> [seconds, ...]
        self.statuses = defaultdict(Counter)    # "POST /api/meals/meals" -> {201: 950, 503: 2}
        self.served_by = defaultdict(Counter)   # "meal-logging" -> {"a1b2c3": 480, "d4e5f6": 470}

    def add(self, name, service, status, served_by, seconds):
        with self.lock:
            self.times[name].append(seconds)
            self.statuses[name][status] += 1
            if served_by:
                self.served_by[service][served_by] += 1


def simulated_user(number, token, stop_at, results):
    rng = random.Random(number)
    day = str(FIRST_DAY + timedelta(days=number))
    while time.time() < stop_at:
        status, pod, seconds, _ = call("GET", f"/api/meals/foods/search?q={rng.choice(SEARCHES).replace(' ', '+')}")
        results.add("GET  /api/meals/foods/search", "meal-logging", status, pod, seconds)

        meal = {"meal_date": day, "meal_type": "snack",
                "items": [{"fdc_id": f, "grams": rng.randint(50, 250)} for f in rng.sample(FOODS, 3)]}
        status, pod, seconds, _ = call("POST", "/api/meals/meals", meal, token)
        results.add("POST /api/meals/meals", "meal-logging", status, pod, seconds)

        food = {"items": [{"fdc_id": f, "grams": rng.randint(50, 250)} for f in rng.sample(FOODS, 5)]}
        status, pod, seconds, _ = call("POST", "/api/nutrients/calculate", food, token)
        results.add("POST /api/nutrients/calculate", "nutrient-calc", status, pod, seconds)


def clean_up(token, users):
    """Delete the meals the load test logged."""
    last_day = FIRST_DAY + timedelta(days=users)
    deleted = 0
    while True:
        status, _, _, data = call("GET", f"/api/meals/meals?start={FIRST_DAY}&end={last_day}", token=token)
        meals = json.loads(data) if status == 200 else []
        if not meals:
            break
        for meal in meals:
            call("DELETE", f"/api/meals/meals/{meal['id']}", token=token)
            deleted += 1
    print(f"Cleaned up: deleted {deleted} test meals.")


def report(results, seconds):
    total = sum(len(t) for t in results.times.values())
    print(f"\n{total} requests in {seconds:.0f} s = {total / seconds:.1f} requests a second\n")
    print(f"{'request':32} {'count':>7} {'ok':>7} {'failed':>7} {'median ms':>10} {'95% under ms':>13}")
    for name, times in sorted(results.times.items()):
        ok = sum(n for status, n in results.statuses[name].items() if 200 <= status < 300)
        times_ms = sorted(t * 1000 for t in times)
        p95 = times_ms[int(len(times_ms) * 0.95) - 1] if len(times_ms) >= 20 else max(times_ms)
        print(f"{name:32} {len(times):>7} {ok:>7} {len(times) - ok:>7} {statistics.median(times_ms):>10.0f} {p95:>13.0f}")
    failures = {name: {s: n for s, n in c.items() if not 200 <= s < 300} for name, c in results.statuses.items()}
    for name, codes in failures.items():
        if codes:
            print(f"  {name} failed with: {dict(codes)}  (0 means no answer at all)")
    print("\nWhich containers answered (the X-Served-By header):")
    for service, pods in sorted(results.served_by.items()):
        shares = ", ".join(f"{pod} {n}" for pod, n in pods.most_common())
        print(f"  {service:15} {shares}")


def main():
    parser = argparse.ArgumentParser(description="MacroScope load test")
    parser.add_argument("--users", type=int, default=20, help="how many people at once (default 20)")
    parser.add_argument("--seconds", type=int, default=60, help="how long to run (default 60)")
    args = parser.parse_args()
    if not API_KEY:
        sys.exit("Stopping: set GOOGLE_API_KEY (the Web API key from your .env file)")

    token = login()
    print(f"Load testing {GATEWAY} with {args.users} users for {args.seconds} seconds ...")
    results = Results()
    stop_at = time.time() + args.seconds
    threads = [threading.Thread(target=simulated_user, args=(n, token, stop_at, results)) for n in range(args.users)]
    started = time.time()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    report(results, time.time() - started)
    clean_up(token, args.users)


if __name__ == "__main__":
    main()
