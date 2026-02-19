# routers/routines.py — Routines + steps endpoints (CRUD + ordering/notes) + SOFT DELETE
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Manage a user's routines (create/list/rename/delete).
# - Manage ordered steps inside a routine (create/update/delete).
# - Supports Iteration 3+ features:
#     - ordered steps (step_order)
#     - notes per step (notes)
#     - optional step photo (photo_url)
# - Iteration 5 update:
#     - Soft delete routines + steps (deleted_at timestamp)
#     - Ensure list/get endpoints hide deleted rows
#     - Keep step_order unique for ACTIVE rows only (partial unique index in Postgres)
#
# SOFT DELETE BEHAVIOUR:
# - "Delete routine" sets routines.deleted_at and also sets deleted_at on its steps.
# - "Delete step" sets routine_steps.deleted_at.
# - List endpoints filter out deleted rows (deleted_at IS NULL).
# - This keeps an audit trail + enables future "Undo" if you ever want it.
#
# DB NOTES (Supabase / Postgres):
# - Schema is public by default, so queries use public.<table>.
# - INSERT uses RETURNING to fetch generated IDs in Postgres.
# - Step ordering:
#     - We compute the next available step_order for active steps to avoid collisions.
#     - If the client sends step_order that conflicts, we can either:
#         (a) reject with 409
#         (b) auto-pick next order
#       For a smoother mobile UX, we auto-pick next order.
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
# - Postgres NOW():
#   https://www.postgresql.org/docs/current/functions-datetime.html

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from auth.deps import DBUser, current_user
from db import engine
from schemas import RoutineCreateIn, RoutineStepBody, RoutineStepUpdateIn

router = APIRouter(tags=["routines"])


# -----------------------------------------------------------------------------
# Helpers (ownership checks) — ACTIVE rows only
# -----------------------------------------------------------------------------

def _assert_routine_owned(conn, routine_id: int, user_id: int) -> None:
    """
    Raise 404 if the routine does not exist, is deleted, or is not owned by the user.
    """
    ok = conn.execute(
        text(
            """
            SELECT 1
            FROM public.routines
            WHERE routine_id = :r
              AND user_id = :u
              AND deleted_at IS NULL
            """
        ),
        {"r": routine_id, "u": user_id},
    ).first()

    if not ok:
        raise HTTPException(status_code=404, detail="Routine not found")


def _assert_step_owned(conn, step_id: int, user_id: int) -> None:
    """
    Raise 404 if the step does not exist, is deleted, or is not owned by the user (via its routine).
    """
    ok = conn.execute(
        text(
            """
            SELECT 1
            FROM public.routine_steps rs
            JOIN public.routines r ON r.routine_id = rs.routine_id
            WHERE rs.step_id = :sid
              AND rs.deleted_at IS NULL
              AND r.deleted_at IS NULL
              AND r.user_id = :u
            """
        ),
        {"sid": step_id, "u": user_id},
    ).first()

    if not ok:
        raise HTTPException(status_code=404, detail="Step not found")


def _next_step_order(conn, routine_id: int) -> int:
    """
    Compute next step_order for ACTIVE steps in a routine.
    Prevents unique violations on (routine_id, step_order) for active rows.
    """
    row = conn.execute(
        text(
            """
            SELECT COALESCE(MAX(step_order), 0) AS max_order
            FROM public.routine_steps
            WHERE routine_id = :rid
              AND deleted_at IS NULL
            """
        ),
        {"rid": routine_id},
    ).first()

    max_order = int(row[0]) if row else 0
    return max_order + 1


def _step_order_taken(conn, routine_id: int, step_order: int) -> bool:
    """
    Check whether an ACTIVE step already has this order.
    """
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM public.routine_steps
            WHERE routine_id = :rid
              AND step_order = :ord
              AND deleted_at IS NULL
            """
        ),
        {"rid": routine_id, "ord": int(step_order)},
    ).first()
    return bool(row)


# -----------------------------------------------------------------------------
# ROUTINES (create / list / rename / soft delete)
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
    List all ACTIVE routines owned by the signed-in user including their ACTIVE steps.

    Design choice:
    - Returns routines + steps in one call to minimise mobile round-trips.
    - Steps returned ordered by step_order so UI can render directly.
    - Deleted rows are hidden via deleted_at IS NULL filters.

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
                  AND deleted_at IS NULL
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
                      AND deleted_at IS NULL
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
    """
    Rename an ACTIVE routine owned by the current user.
    """
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
    SOFT delete a routine and its steps.

    Behaviour:
    - Sets routines.deleted_at = NOW()
    - Sets routine_steps.deleted_at = NOW() for all steps in that routine
    """
    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        # Soft delete steps first
        conn.execute(
            text(
                """
                UPDATE public.routine_steps
                SET deleted_at = NOW()
                WHERE routine_id = :r
                  AND deleted_at IS NULL
                """
            ),
            {"r": routine_id},
        )

        # Soft delete routine
        conn.execute(
            text(
                """
                UPDATE public.routines
                SET deleted_at = NOW()
                WHERE routine_id = :r
                  AND deleted_at IS NULL
                """
            ),
            {"r": routine_id},
        )

    return {"ok": True, "routine_id": routine_id}


# -----------------------------------------------------------------------------
# ROUTINE STEPS (create / update / soft delete)
# -----------------------------------------------------------------------------

@router.post("/routines/{routine_id}/steps")
def add_routine_step(
    routine_id: int,
    body: RoutineStepBody,
    user: DBUser = Depends(current_user),
):
    """
    Add a step to an existing routine (ACTIVE only).

    Ordering:
    - If client does NOT send step_order, we assign next available order.
    - If client sends a step_order that is already taken, we auto-assign next order
      (prevents 500 UniqueViolation and improves UX).
    """
    step_name = (body.step_name or "").strip()
    if not step_name:
        raise HTTPException(status_code=400, detail="step_name is required")

    notes = body.notes if getattr(body, "notes", None) is not None else None
    photo_url = body.photo_url if getattr(body, "photo_url", None) is not None else None

    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        # Parse / choose step order safely
        if getattr(body, "step_order", None) is None:
            order_num = _next_step_order(conn, routine_id)
        else:
            try:
                order_num = int(body.step_order)
            except Exception:
                raise HTTPException(status_code=400, detail="step_order must be an integer")

            # If taken, pick next available automatically
            if _step_order_taken(conn, routine_id, order_num):
                order_num = _next_step_order(conn, routine_id)

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
    Update an ACTIVE step (owned by user via routine ownership).

    Supports:
    - step_name
    - step_order
    - notes
    - photo_url
    """
    step_name = payload.step_name.strip() if payload.step_name is not None else None
    step_order = payload.step_order if hasattr(payload, "step_order") else None
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
                  AND deleted_at IS NULL
                """
            ),
            {"sid": step_id, "nm": step_name, "ord": step_order, "notes": notes, "photo": photo_url},
        )

    return {"ok": True, "step_id": step_id}


@router.delete("/steps/{step_id}")
def delete_step(step_id: int, user: DBUser = Depends(current_user)):
    """
    SOFT delete a step (ACTIVE only).
    """
    with engine.begin() as conn:
        _assert_step_owned(conn, step_id, user.user_id)

        conn.execute(
            text(
                """
                UPDATE public.routine_steps
                SET deleted_at = NOW()
                WHERE step_id = :sid
                  AND deleted_at IS NULL
                """
            ),
            {"sid": step_id},
        )

    return {"ok": True, "step_id": step_id}


# -----------------------------------------------------------------------------
# Optional: reorder endpoint (drag/drop) — ACTIVE steps only
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
    Bulk update step_order after reorder.

    Notes:
    - Only affects ACTIVE steps.
    - Assumes client sends a valid unique ordering for the routine’s steps.
    """
    if not items:
        return {"ok": True}

    with engine.begin() as conn:
        _assert_routine_owned(conn, routine_id, user.user_id)

        # Ensure every step_id belongs to this routine and is ACTIVE
        step_ids = [int(i.step_id) for i in items]
        rows = conn.execute(
            text(
                """
                SELECT step_id
                FROM public.routine_steps
                WHERE routine_id = :rid
                  AND deleted_at IS NULL
                  AND step_id = ANY(:ids)
                """
            ),
            {"rid": routine_id, "ids": step_ids},
        ).fetchall()

        found = {int(r[0]) for r in rows}
        missing = [sid for sid in step_ids if sid not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"Some steps do not belong to this routine: {missing}")

        # Apply updates
        for it in items:
            conn.execute(
                text(
                    """
                    UPDATE public.routine_steps
                    SET step_order = :ord
                    WHERE step_id = :sid
                      AND routine_id = :rid
                      AND deleted_at IS NULL
                    """
                ),
                {"ord": int(it.step_order), "sid": int(it.step_id), "rid": routine_id},
            )

    return {"ok": True}
