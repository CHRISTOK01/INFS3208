"""Settings for the service. They all come from environment variables, so the same image works
in Docker Compose and on Kubernetes."""
import os

SERVICE_NAME = "food-recommender"
API_PREFIX = "/api/recommend"  # the gateway (and later the Ingress) sends this path to us as-is

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://recommender:recommender_pw@localhost:5436/recommender_db")
JWT_SECRET = os.getenv("JWT_SECRET", "")              # signs the tokens our services use with each other
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")  # the Google Cloud project whose logins we accept
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
