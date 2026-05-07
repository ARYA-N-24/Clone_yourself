"""
Demo seed script for the Clone Yourself Platform.

Creates a synchronous DB session and inserts deterministic demo data.

Usage:
    python backend/seed.py

Requires DATABASE_URL to be set in the environment (or .env file).
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is not set.", file=sys.stderr)
    sys.exit(1)

# Convert asyncpg URL to psycopg2-compatible URL for synchronous seeding
SYNC_URL = (
    DATABASE_URL
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("asyncpg://", "postgresql://")
)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.models.db_models import Base
from backend.utils.mock_data import seed_demo_data

engine = create_engine(SYNC_URL, echo=False)

# Create all tables if they don't exist yet (useful for fresh environments)
Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

with Session() as session:
    summary = seed_demo_data(session)

print("Demo seed data inserted successfully!")
print()
for key, count in summary.items():
    print(f"  {key:20s}: {count}")
print()
print("Demo user credentials:")
print("  Email: 1ms24ci402@msrit.edu")
print("  (Sign in via Google OAuth with this email to see demo data)")
