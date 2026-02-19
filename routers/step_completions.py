# routers/step_completions.py — Persist step completion status (Supabase/Postgres)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Stores whether a step was completed on a specific date.
# - Used by Track + Insights screens.
#
# DB (Supabase Postgres):
# Table: step_completions
# Columns:
#   completion_id (bigint)
#   user_id (bigint)
#   step_id (bigint)
#   log_date (date)
#   period (text)
#   completed (boolean)
#   created_at (timestamptz)

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from db import engine
from schemas import StepCompletionIn
from auth.deps import current_user, DBUser

router = APIRouter(tags=["step-completions"])


# -------------------------------------------------------------------------
# GET completed step IDs for a given date
# -------------------------------------------------------------------------
@router.get("/step-completions")
def get_step_completions(
    completion_date: Optional[date] = None,
    user: DBUser = Depends(current_user),
):
    d = completion_date or date.today()

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT step_id
                FROM step_completions
                WHERE user_id = :u
                  AND log_date = :d
                  AND completed = TRUE
                """
            ),
            {"u": user.user_id, "d": d},
        ).fetchall()

    step_ids = [int(r[0]) for r in rows]
    return {"completion_date": d, "step_ids": step_ids}


# -------------------------------------------------------------------------
# GET dates where >=1 step was completed
# -------------------------------------------------------------------------
@router.get("/step-completions/dates")
def get_completion_dates(
    days: int = Query(60, ge=1, le=365),
    user: DBUser = Depends(current_user),
):
    start = date.today() - timedelta(days=days)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT log_date
                FROM step_completions
                WHERE user_id = :u
                  AND log_date >= :start
                  AND completed = TRUE
                ORDER BY log_date DESC
                """
            ),
            {"u": user.user_id, "start": start},
        ).fetchall()

    dates = [r[0].isoformat() for r in rows]
    return {"days": days, "dates": dates}


# -------------------------------------------------------------------------
# UPSERT completion (Postgres style)
# -------------------------------------------------------------------------
@router.post("/step-completions")
def upsert_step_completion(payload: StepCompletionIn, user: DBUser = Depends(current_user)):
    d = payload.completion_date or date.today()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO step_completions (user_id, step_id, log_date, period, completed)
                VALUES (:u, :sid, :d, :p, :done)
                ON CONFLICT (user_id, step_id, log_date)
                DO UPDATE SET completed = EXCLUDED.completed
                """
            ),
            {
                "u": user.user_id,
                "sid": payload.step_id,
                "d": d,
                "p": payload.period or "",
                "done": True if payload.is_done else False,
            },
        )

    return {
        "ok": True,
        "completion_date": d,
        "step_id": payload.step_id,
        "is_done": payload.is_done,
    }
