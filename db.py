# db.py — DermaFlow SQLAlchemy engine (Supabase Postgres)
#
# PURPOSE:
# - Create a single SQLAlchemy engine used across routers/DAO layers.
# - Read the DB connection string from environment variables (local .env or Render env vars).
#
# ENV VARS (supported):
# - DATABASE_URL (recommended standard)
# - SUPABASE_DATABASE_URL (your existing naming)
# - DB_URL (fallback)
#
# Notes:
# - In local development, python-dotenv loads variables from .env.
# - In production (Render), variables are set in the Render dashboard.
#
# References:
# - SQLAlchemy Engine: https://docs.sqlalchemy.org/en/20/core/engines.html
# - Supabase Postgres: https://supabase.com/docs/guides/database

import os
from sqlalchemy import create_engine

# Load .env only for local development (Render provides env vars directly).
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # If python-dotenv isn't available or .env isn't present, ignore.
    pass

DATABASE_URL = (
    os.getenv("DATABASE_URL")
    or os.getenv("SUPABASE_DATABASE_URL")
    or os.getenv("DB_URL")
)

if not DATABASE_URL:
    raise RuntimeError(
        "No DB URL set. Add DATABASE_URL (recommended) or SUPABASE_DATABASE_URL in environment variables."
    )

# Create SQLAlchemy engine
# pool_pre_ping helps avoid stale connections in cloud environments.
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
    max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "5")),
)
