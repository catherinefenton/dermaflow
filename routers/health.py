# routers/health.py — Health check endpoint
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Simple endpoint to confirm the API process is running AND can reach the database.
# - Used when debugging mobile “cannot reach API” issues (separates network vs DB failure).
#
# WHY IT MATTERS:
# - If /health fails → backend or networking issue (API not reachable).
# - If /health returns ok but other endpoints fail → likely auth, routing, or payload issue.
#
# DESIGN:
# - Performs a lightweight "SELECT 1" so we confirm DB connectivity without touching app tables.
#
# References:
# - FastAPI routing: https://fastapi.tiangolo.com/tutorial/bigger-applications/
# - SQLAlchemy text(): https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text

from fastapi import APIRouter
from sqlalchemy import text

from db import engine

router = APIRouter()


@router.get("/health")
def health():
    """
    Health check:
    - Connects to DB and runs a trivial query.
    - Returns {"status": "ok"} if DB is reachable.
    """
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}
