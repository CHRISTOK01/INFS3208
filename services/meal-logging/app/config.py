"""Settings for the service. They all come from environment variables, so the same image works
in Docker Compose and on Kubernetes."""
import os

SERVICE_NAME = "meal-logging"
API_PREFIX = "/api/meals"  # the gateway (and later the Ingress) sends this path to us as-is

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://meal:meal_pw@localhost:5433/meal_db")
JWT_SECRET = os.getenv("JWT_SECRET", "")
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
