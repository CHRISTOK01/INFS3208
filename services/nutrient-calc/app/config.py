"""Settings for the service. They all come from environment variables, so the same image works
in Docker Compose and on Kubernetes."""
import os

SERVICE_NAME = "nutrient-calc"
API_PREFIX = "/api/nutrients"  # the gateway (and later the Ingress) sends this path to us as-is

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://nutrient:nutrient_pw@localhost:5434/nutrient_db")
JWT_SECRET = os.getenv("JWT_SECRET", "")
APP_VERSION = os.getenv("APP_VERSION", "dev")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
