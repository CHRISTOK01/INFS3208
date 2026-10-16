"""Settings for the service. They all come from environment variables, so the same image works
in Docker Compose and on Kubernetes."""
import os

SERVICE_NAME = "meal-logging"
API_PREFIX = "/api/meals"  # the gateway (and later the Ingress) sends this path to us as-is

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meal:meal_pw@localhost:5433/meal_db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
NUTRIENT_CALC_URL = os.getenv("NUTRIENT_CALC_URL", "http://localhost:8002")
JWT_SECRET = os.getenv("JWT_SECRET", "")              # signs the tokens our services use with each other
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")  # the Google Cloud project whose logins we accept
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")        # the public Web API key the website logs in with
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))

SEARCH_CACHE_SECONDS = int(os.getenv("SEARCH_CACHE_SECONDS", "3600"))  # how long search results stay in Redis
NUTRIENT_CALC_TIMEOUT = float(os.getenv("NUTRIENT_CALC_TIMEOUT", "3"))  # seconds to wait for nutrient-calc
