"""Job settings. Database values come from environment variables, with the same names as
configuration-service's (it owns the database: this job only reads it)."""

import os

# --- PostgreSQL (configuration-service's database) -----------------------------------------
# Defaults are docker-compose's PostgreSQL as seen from the host (port 5433). In Docker,
# POSTGRES_HOST=postgres and POSTGRES_PORT=5432.
POSTGRES_DB = os.getenv('POSTGRES_DB', 'configuration_service')
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5433'))
# A full SQLAlchemy URL overrides the values above (e.g. Cloud SQL, or SQLite in tests).
DATABASE_URL = os.getenv('DATABASE_URL', '')

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
