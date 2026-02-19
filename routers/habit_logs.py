# routers/habit_logs.py — Habit logging endpoints (AM/PM completion tracking)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Store whether a routine was completed or skipped for a given day + period (AM/PM).
# - Allow the Track screen to fetch recent history (week/month).
#
# DATA MODEL (high-level):
# habit_logs(user_id, routine_id, log_date, period, status, note)
#
# KEY BEHAVIOUR:
# - Uses ON DUPLICATE KEY UPDATE so a user can "change their mind" for a day:
#   e.g., set Skipped -> later set Completed, without creating duplicates.
#
# SECURITY:
# - Requires authentication using Depends(current_user).
# - User_id always comes from the JWT (not from the client payload).
#
# References:
# - FastAPI dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
# - MySQL ON DUPLICATE KEY UPDATE: https://dev.mysql.com/doc/refman/8.0/en/insert-on-duplicate.html
# - datetime date/timedelta: https://docs.python.org/3/library/datetime.html

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from db import engine
from schemas import HabitLogIn
from auth.deps import current_user, DBUser

router = APIRouter(tags=["habit-logs"])


@router.post("/habit-logs")
def create_habit_log(payload: HabitLogIn, user: DBUser = Depends(current_user)):
    """
    Create or update a habit log entry.

    Valid inputs:
    - period: "AM" or "PM"
    - status: "Completed" or "Skipped"
    - log_date: optional (defaults to today)

    Implementation detail:
    - MySQL unique constraint should exist on (user_id, routine_id, log_date, period)
      to make ON DUPLICATE KEY UPDATE behave correctly.
    """
    period = payload.period.upper().strip()
    status_val = payload.status.capitalize().strip()

    # Validation: ensure consistent values in the DB
    if period not in {"AM", "PM"}:
        raise HTTPException(status_code=400, detail="period must be 'AM' or 'PM'")
    if status_val not in {"Completed", "Skipped"}:
        raise HTTPException(status_code=400, detail="status must be 'Completed' or 'Skipped'")

    log_date = payload.log_date or date.today()

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO habit_logs (user_id, routine_id, log_date, period, status, note)
                VALUES (:u, :r, :d, :p, :s, :n)
                ON DUPLICATE KEY UPDATE
                    status = VALUES(status),
                    note   = VALUES(note)
                """
            ),
            {
                "u": user.user_id,                     # always from JWT
                "r": payload.routine_id,               # routine being tracked
                "d": log_date,                         # date being tracked (defaults today)
                "p": period,                           # AM/PM
                "s": status_val,                       # Completed/Skipped
                "n": (payload.note or "").strip() or None,  # optional note
            },
        )

    return {"ok": True, "log_date": log_date, "period": period, "status": status_val}


@router.get("/habit-logs")
def list_habit_logs(window: str = "week", user: DBUser = Depends(current_user)):
    """
    Fetch recent habit logs for the logged-in user.

    Query:
    - window=week  -> last 7 days (today back 6 days)
    - window=month -> last 30 days (today back 29 days)

    Output:
    - start_date / end_date + list of items in descending date order.
    """
    window = window.lower().strip()
    if window not in {"week", "month"}:
        raise HTTPException(status_code=400, detail="window must be 'week' or 'month'")

    days = 6 if window == "week" else 29
    end = date.today()
    start = end - timedelta(days=days)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT log_date, period, status, note, routine_id
                FROM habit_logs
                WHERE user_id = :u
                  AND log_date BETWEEN :start AND :end
                ORDER BY log_date DESC, period
                """
            ),
            {"u": user.user_id, "start": start, "end": end},
        ).mappings().all()

    return {
        "window": window,
        "start_date": start,
        "end_date": end,
        "items": [dict(r) for r in rows],
    }


@router.get("/habit-logs/dates")
def get_habit_log_dates(
    days: int = Query(60, ge=1, le=365),
    user: DBUser = Depends(current_user),
):
    """
    Return UNIQUE dates where the user has any routine completion recorded
    (AM completed OR PM completed) within the last N days.

    Used for Iteration 4 Insights:
    - current streak
    - best streak
    - 7-day consistency
    - number of days logged

    Example:
      GET /habit-logs/dates?days=60

    Returns:
      { "days": 60, "dates": ["2026-02-02", "2026-01-23", ...] }
    """
    start = date.today() - timedelta(days=days)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT DISTINCT log_date
                FROM habit_logs
                WHERE user_id = :u
                  AND log_date >= :start
                  AND status = 'Completed'
                ORDER BY log_date DESC
                """
            ),
            {"u": user.user_id, "start": start},
        ).fetchall()

    dates = [r[0].isoformat() for r in rows]
    return {"days": days, "dates": dates}