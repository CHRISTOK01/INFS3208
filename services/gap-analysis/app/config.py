"""Settings for the service. They all come from environment variables, so the same image works
in Docker Compose and on Kubernetes."""
import os

SERVICE_NAME = "gap-analysis"
API_PREFIX = "/api/gaps"  # the gateway (and later the Ingress) sends this path to us as-is

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://gap:gap_pw@localhost:5435/gap_db")
JWT_SECRET = os.getenv("JWT_SECRET", "")              # signs the tokens our services use with each other
GOOGLE_PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID", "")  # the Google Cloud project whose logins we accept
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
NUTRIENT_CALC_URL = os.getenv("NUTRIENT_CALC_URL", "http://localhost:8002")
NUTRIENT_CALC_TIMEOUT = float(os.getenv("NUTRIENT_CALC_TIMEOUT", "3"))  # seconds to wait for nutrient-calc
