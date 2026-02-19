# routers/routines.py — Routines + steps endpoints (CRUD + ordering/notes)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Manage a user's routines (create/list/rename/delete).
# - Manage ordered steps inside a routine (create/update/delete).
# - Supports Iteration 3+ features:
#     - ordered steps (step_order)
#     - notes per step (notes)
#     - optional step photo (photo_url)
#
# SECURITY MODEL:
# - Every endpoint uses Depends(current_user) so the JWT controls user identity.
# - All write operations validate ownership (routine belongs to user; step belongs to a routine owned by user).
# - Prevents a user from editing/deleting another user’s routines by guessing IDs.
#
# DB NOTES (Supabase / Postgres):
# - Schema is public by default, so queries are written as public.<table>.
# - INSERT uses RETURNING to fetch generated IDs in Postgres.
# - routine_steps are ordered by step_order.
#
# ATTRIBUTION / REFERENCES:
# - FastAPI dependencies + APIRouter:
#   https://fastapi.tiangolo.com/tutorial/bigger-applications/
# - SQLAlchemy text() for raw SQL:
#   https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text
# - Pydantic models:
#   https://docs.pydantic.dev/latest/
# - Postgres RETURNING clause:
#   https://www.postgresql.org/docs/current/dml-returning.html

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth.deps import DBUser, current_user
from db import engine
from schemas import (
    RoutineCreateIn,
    RoutineStepBody,
    RoutineStepCreateIn,
    RoutineStepUpdateIn,
)

router = APIRouter(tags=["routines"])


# -----------------------------------------------------------------------------
# Helpers (ownership checks)
# -----------------------------------------------------------------------------

def _assert_routine_owned(conn, routine_id: int, user_id: int) -> None:
    """Raise 404 if the routine does not exist or is not owned by the user."""
    ok = conn.execute(
        text(
            """
            SELECT 1
            FROM public.routines
            WHERE routine_id = :r AND user_id = :u
            """
        ),
        {"r": routine_id, "u": user_id},
    ).first()
    if not ok:
        raise HTTPException(status_code=404, detail="Routine not found")


def _assert_step_owned(conn, step_id: int, user_id: int) -> None:
    """Raise 404 if the step does not exist or is not owned by the user (via its routine)."""
    ok = conn.execute(
        text(
            """
            SELECT 1
            FROM public.routine_steps rs
            JOIN public.routines r ON r.routine_id = rs.routine_id
            WHERE rs.step_id = :sid AND r.user_id = :u
            """
        ),
        {"sid": step_id, "u": user_id},
    ).first()
    if not ok:
        raise HTTPException(status_code=404, detail="Step not found")


# -----------------------------------------------------------------------------
# ROUTINES (create / list / rename / delete)
# -----------------------------------------------------------------------------

@router.post("/routines")
def create_routine(payload: RoutineCreateIn, user: DBUser = Depends(current_user)):
    """
    Create a new routine for the signed-in user.

    Input:
      { "name": "Evening Routine" }

    Returns:
      { "routine_id": 123, "name": "Evening Routine" }
    """
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")

    with engine.begin() as conn:
        res = conn.execute(
            text(
                """
                INSERT INTO public.routines (user_id, name)
                VALUES (:u, :n)
                RETURNING routine_id
                """
            ),
            {"u": user.user_id, "n": name},
        ).first()

        if not res:
            raise HTTPException(status_code=500, detail="Failed to create routine")

        rid = int(res[0])

    return {"routine_id": rid, "name": name}


@router.get("/routines")
def list_my_routines(user: DBUser = Depends(current_user)):
    """
    List all routines owned by the signed-in user including their steps.

    Design choice:
    - Returns routines + steps in one call to minimise mobile round-trips.
    - Steps returned ordered by step_order so UI can render directly.

    Returns:
      [
        { "routine_id": 1, "name": "...", "steps": [ ... ] },
        ...
      ]
    """
    with engine.connect() as conn:
        routines = conn.execute(
            text(
                """
                SELECT routine_id, name, created_at
                FROM public.routines
                WHERE user_id = :u
                ORDER BY routine_id DESC
                """
            ),
            {"u": user.user_id},
        ).mappings().all()

        out = []
        for r in routines:
            steps = conn.execute(
                text(
                    """
                    SELECT step_id, step_order, step_name, notes, photo_url
                    FROM public.routine_steps
                    WHERE routine_id = :rid
                    ORDER BY step_order
                    """
                ),
                {"rid": r["routine_id"]},
            ).mappings().all()

            out.append(
                {
                    "routine_id": r["routine_id"],
                    "name": r["name"],
                    "steps": [dict(s) for s in steps],
                }
            )

    return out


@router.put("/routines/{routine_id}")
def rename_routine(
    routine_id: int, payload: RoutineCreateIn, user: DBUser = Depends(current_user)
):
    """Rename a routine owned by the current user."""
    final_name = payload.name.strip()
    if not final_name:
        raise HTTPException(status_code=400, detail="name is required")

    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        conn.execute(
            text(
                """
                UPDATE public.routines
                SET name = :n
                WHERE routine_id = :r
                """
            ),
            {"n": final_name, "r": routine_id},
        )

    return {"routine_id": routine_id, "name": final_name}


@router.delete("/routines/{routine_id}")
def delete_routine(routine_id: int, user: DBUser = Depends(current_user)):
    """
    Delete a routine and its steps.

    Current behaviour:
    - Hard delete: steps removed first, then routine.
    - If you later want soft delete/audit, this is where you'd change it.
    """
    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        conn.execute(
            text("DELETE FROM public.routine_steps WHERE routine_id = :r"),
            {"r": routine_id},
        )
        conn.execute(
            text("DELETE FROM public.routines WHERE routine_id = :r"),
            {"r": routine_id},
        )

    return {"ok": True}


# -----------------------------------------------------------------------------
# ROUTINE STEPS (create / update / delete)
# -----------------------------------------------------------------------------

@router.post("/routines/{routine_id}/steps")
def add_routine_step(
    routine_id: int,
    body: RoutineStepBody,
    user: DBUser = Depends(current_user),
):
    """
    Add a step to an existing routine.

    Validates:
    - Routine exists AND belongs to the current user.
    - step_order is an integer (prevents issues like NaN/"" from client input).
    """
    step_name = (body.step_name or "").strip()
    if not step_name:
        raise HTTPException(status_code=400, detail="step_name is required")

    try:
        order_num = int(body.step_order)
    except Exception:
        raise HTTPException(status_code=400, detail="step_order must be an integer")

    notes = body.notes if getattr(body, "notes", None) is not None else None
    photo_url = body.photo_url if getattr(body, "photo_url", None) is not None else None

    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        res = conn.execute(
            text(
                """
                INSERT INTO public.routine_steps (routine_id, step_order, step_name, notes, photo_url)
                VALUES (:rid, :o, :nm, :notes, :photo)
                RETURNING step_id
                """
            ),
            {
                "rid": routine_id,
                "o": order_num,
                "nm": step_name,
                "notes": notes,
                "photo": photo_url,
            },
        ).first()

        if not res:
            raise HTTPException(status_code=500, detail="Failed to add step")

        step_id = int(res[0])

    return {
        "ok": True,
        "step_id": step_id,
        "routine_id": routine_id,
        "step_order": order_num,
        "step_name": step_name,
        "notes": notes,
        "photo_url": photo_url,
    }


@router.put("/steps/{step_id}")
def update_step(
    step_id: int,
    payload: RoutineStepUpdateIn,
    user: DBUser = Depends(current_user),
):
    """
    Update an existing step (owned by user via routine ownership).

    Supports:
    - step_name
    - step_order
    - notes
    - photo_url
    """
    # Normalise fields (only update what is provided)
    step_name = payload.step_name.strip() if payload.step_name is not None else None
    step_order = payload.step_order
    notes = payload.notes if hasattr(payload, "notes") else None
    photo_url = payload.photo_url if hasattr(payload, "photo_url") else None

    if step_name is not None and not step_name:
        raise HTTPException(status_code=400, detail="step_name cannot be empty")

    with engine.begin() as conn:
        _assert_step_owned(conn, step_id, user.user_id)

        conn.execute(
            text(
                """
                UPDATE public.routine_steps
                SET
                  step_name  = COALESCE(:nm, step_name),
                  step_order = COALESCE(:ord, step_order),
                  notes      = COALESCE(:notes, notes),
                  photo_url  = COALESCE(:photo, photo_url)
                WHERE step_id = :sid
                """
            ),
            {"sid": step_id, "nm": step_name, "ord": step_order, "notes": notes, "photo": photo_url},
        )

    return {"ok": True, "step_id": step_id}


@router.delete("/steps/{step_id}")
def delete_step(step_id: int, user: DBUser = Depends(current_user)):
    """Delete a step (owned by user via routine ownership)."""
    with engine.begin() as conn:
        _assert_step_owned(conn, step_id, user.user_id)

        conn.execute(
            text("DELETE FROM public.routine_steps WHERE step_id = :sid"),
            {"sid": step_id},
        )

    return {"ok": True, "step_id": step_id}


# -----------------------------------------------------------------------------
# Optional: reorder endpoint (if your StepList drag/reorder calls it)
# -----------------------------------------------------------------------------

class ReorderItem(BaseModel):
    step_id: int
    step_order: int


@router.put("/routines/{routine_id}/steps/reorder")
def reorder_steps(
    routine_id: int,
    items: List[ReorderItem],
    user: DBUser = Depends(current_user),
):
    """
    Bulk update step_order after drag-and-drop reorder.

    Input example:
      [
        { "step_id": 10, "step_order": 1 },
        { "step_id": 11, "step_order": 2 }
      ]
    """
    if not items:
        return {"ok": True}

    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        # Ensure every step_id belongs to this routine (and therefore this user)
        step_ids = [i.step_id for i in items]
        rows = conn.execute(
            text(
                """
                SELECT step_id
                FROM public.routine_steps
                WHERE routine_id = :rid
                  AND step_id = ANY(:ids)
                """
            ),
            {"rid": routine_id, "ids": step_ids},
        ).fetchall()

        found = {int(r[0]) for r in rows}
        missing = [sid for sid in step_ids if sid not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"Some steps do not belong to this routine: {missing}")

        for it in items:
            conn.execute(
                text(
                    """
                    UPDATE public.routine_steps
                    SET step_order = :ord
                    WHERE step_id = :sid AND routine_id = :rid
                    """
                ),
                {"ord": int(it.step_order), "sid": int(it.step_id), "rid": routine_id},
            )

    return {"ok": True}
