"""Environment-backed settings for the demo service."""

import os

DATABASE_URL = os.getenv("DEMO_DATABASE_URL", "sqlite:///./demo.db")
SERVICE_NAME = os.getenv("DEMO_SERVICE_NAME", "ProofStack Demo Store")
