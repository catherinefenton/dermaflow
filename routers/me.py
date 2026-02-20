# routers/me.py — Profile endpoints for the currently authenticated user
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - GET /me: return the current user profile (id, name, email, created_at, skin_type label).
# - PUT /me: update profile fields (name + skin type).
# - DELETE /me: delete the currently authenticated user (hard delete).
#
# SECURITY:
# - Uses Depends(current_user) so user identity comes from the JWT, not from the client payload.
# - Prevents editing another user’s profile by guessing IDs.
#
# DESIGN NOTES:
# - split_name(): stores first_name + last_name separately in DB (simple parsing).
# - skin_type_id_for_from_any(): accepts either a skin type code or label/free text,
#   and falls back to "other" to avoid null/invalid entries.
# - UPDATE uses COALESCE so missing fields do not overwrite existing values.
# - DELETE is implemented as a hard delete for demo simplicity. Related data is removed via
#   ON DELETE CASCADE foreign keys (verified in Supabase for habit_logs/routines/step_completions).
#
# References:
# - FastAPI dependencies: https://fastapi.tiangolo.com/tutorial/dependencies/
# - SQLAlchemy text() queries: https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text
# - MySQL CONCAT_WS(): https://dev.mysql.com/doc/refman/8.0/en/string-functions.html#function_concat-ws

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from db import engine
from schemas import ProfileUpdateIn
from auth.deps import current_user, DBUser

router = APIRouter(tags=["me"])


def split_name(full: str | None) -> tuple[str, str]:
    """
    Split a full name into first + last.
    This keeps the UI simple (one input) while storing structured fields.

    Examples:
      - "Catherine" -> ("Catherine", "")
      - "Catherine Fenton" -> ("Catherine", "Fenton")
      - "Catherine Mary Fenton" -> ("Catherine", "Mary Fenton")
    """
    if not full:
        return "", ""
    parts = full.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def skin_type_id_for_from_any(conn, *, code: str | None, label_or_free_text: str | None):
    """
    Resolve skin_type_id from either:
    - code (preferred): matches skin_types.code (case-insensitive)
    - label/free text: matches skin_types.label (case-insensitive)

    Fallback:
    - if no match, return the id for code='other' if it exists.
    """
    # 1) Try code match (best case, most consistent)
    if code:
        row = conn.execute(
            text("SELECT skin_type_id FROM skin_types WHERE LOWER(code)=:v LIMIT 1"),
            {"v": code.strip().lower()},
        ).first()
        if row:
            return int(row[0])

    # 2) Try label match (supports UI text values)
    if label_or_free_text:
        v = label_or_free_text.strip().lower()
        if v:
            row = conn.execute(
                text("SELECT skin_type_id FROM skin_types WHERE LOWER(label)=:v LIMIT 1"),
                {"v": v},
            ).first()
            if row:
                return int(row[0])

    # 3) Fallback
    row = conn.execute(
        text("SELECT skin_type_id FROM skin_types WHERE code='other' LIMIT 1")
    ).first()
    return int(row[0]) if row else None


@router.get("/me")
def me_get(user: DBUser = Depends(current_user)):
    """
    Return the logged-in user's profile.

    Output shape (example):
      {
        "id": 1,
        "name": "Catherine Fenton",
        "email": "...",
        "created_at": "...",
        "skin_type": "Other"
      }
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT u.user_id AS id,
                       CONCAT_WS(' ', u.first_name, u.last_name) AS name,
                       u.email,
                       u.created_at,
                       st.label AS skin_type
                FROM public.app_users u
                LEFT JOIN skin_types st ON st.skin_type_id = u.skin_type_id
                WHERE u.user_id = :id
                """
            ),
            {"id": user.user_id},
        ).mappings().first()

    # row should exist if token is valid, but dict(row) is still safe/convenient
    return dict(row)


@router.put("/me")
def me_update(payload: ProfileUpdateIn, user: DBUser = Depends(current_user)):
    """
    Update the current user's profile.

    - Parses payload.name into first/last.
    - Resolves skin_type_id from code or label.
    - COALESCE means if a value is missing/blank, we keep the existing DB value.
    - Returns the updated /me view to keep the client in sync.
    """
    with engine.begin() as conn:
        first, last = split_name(payload.name)

        st_id = skin_type_id_for_from_any(
            conn,
            code=(payload.skin_type_code or "").strip() or None,
            label_or_free_text=payload.skin_type,
        )

        # IMPORTANT: use the correct table name (public.app_users), not "users".
        conn.execute(
            text(
                """
                UPDATE public.app_users
                SET first_name   = COALESCE(:fn, first_name),
                    last_name    = COALESCE(:ln, last_name),
                    skin_type_id = COALESCE(:stid, skin_type_id)
                WHERE user_id = :id
                """
            ),
            {"fn": first or None, "ln": last or None, "stid": st_id, "id": user.user_id},
        )

    return me_get(user)


@router.delete("/me", status_code=204)
def me_delete(user: DBUser = Depends(current_user)):
    """
    Permanently delete the current user's account (hard delete).

    NOTE:
    - This will succeed if dependent tables use ON DELETE CASCADE foreign keys.
      In Supabase, CASCADE was verified for:
        - habit_logs.user_id -> app_users.user_id
        - routines.user_id -> app_users.user_id
        - step_completions.user_id -> app_users.user_id
    - After deletion, the mobile client should clear local auth token and return to Welcome/Login.
    """
    with engine.begin() as conn:
        # Ensure user exists (clean error)
        exists = conn.execute(
            text("SELECT 1 FROM public.app_users WHERE user_id = :id"),
            {"id": user.user_id},
        ).first()

        if not exists:
            raise HTTPException(status_code=404, detail="User not found")

        # Hard delete user row (dependent data removed by FK cascades)
        conn.execute(
            text("DELETE FROM public.app_users WHERE user_id = :id"),
            {"id": user.user_id},
        )

    return