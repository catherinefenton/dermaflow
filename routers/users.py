# routers/users.py — User creation + listing endpoints
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Create users (non-auth endpoint used in some flows / admin testing).
# - List users (mainly for testing / debug).
#
# NOTE:
# - You already use /auth/register and /auth/login for real authentication.
# - If this /users endpoint is still enabled in production, consider locking it down
#   or removing it before final deployment (Iteration 4 hardening).
#
# References:
# - Pydantic BaseModel: https://docs.pydantic.dev/latest/
# - SQLAlchemy text(): https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from db import engine
from auth.security import hash_password

router = APIRouter(tags=["users"])


class UserIn(BaseModel):
    email: str
    name: Optional[str] = None
    skin_type: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    location: Optional[str] = None
    password: Optional[str] = Field(default=None)
    skin_type_code: Optional[str] = None
    skin_type_other: Optional[str] = None


def split_name(full: str | None) -> tuple[str, str]:
    """Split a full name into (first, last). If only one word, last name is blank."""
    if not full:
        return "", ""
    parts = full.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def skin_type_id_for_from_any(conn, *, code: str | None, label_or_free_text: str | None):
    """
    Resolve a skin_type_id using either:
    - a short code (preferred), or
    - a label / free text match, or
    - fallback to 'other'
    """
    if code:
        row = conn.execute(
            text("SELECT skin_type_id FROM skin_types WHERE LOWER(code)=:v LIMIT 1"),
            {"v": code.strip().lower()},
        ).first()
        if row:
            return int(row[0])

    if label_or_free_text:
        v = label_or_free_text.strip().lower()
        if v:
            row = conn.execute(
                text("SELECT skin_type_id FROM skin_types WHERE LOWER(label)=:v LIMIT 1"),
                {"v": v},
            ).first()
            if row:
                return int(row[0])

    row = conn.execute(
        text("SELECT skin_type_id FROM skin_types WHERE code='other' LIMIT 1")
    ).first()
    return int(row[0]) if row else None


@router.post("/users")
def create_user(user: UserIn):
    """
    Create a user record (mostly used for testing / admin flows).
    If you’re using /auth/register for real usage, consider removing this later.
    """
    email = (user.email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    fn = (user.first_name or "").strip()
    ln = (user.last_name or "").strip()
    if not (fn or ln):
        fn, ln = split_name(user.name)

    pw_hash = hash_password(user.password)
    loc = (user.location or "").strip() or None

    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM public.app_users WHERE email=:e"), {"e": email}).first():
            raise HTTPException(status_code=400, detail="Email already exists")

        st_id = skin_type_id_for_from_any(
            conn,
            code=user.skin_type_code,
            label_or_free_text=user.skin_type or user.skin_type_other,
        )

        res = conn.execute(
            text(
                """
                INSERT INTO public.app_users (first_name, last_name, email, password_hash, skin_type_id)
                VALUES (:fn,:ln,:em,:ph,:stid)
                """
            ),
            {
                "fn": fn or None,
                "ln": ln or None,
                "em": email,
                "ph": pw_hash,
                "loc": loc,
                "stid": st_id,
            },
        )
        new_id = res.lastrowid

        row = conn.execute(
            text(
                """
                SELECT u.user_id AS id,
                       CONCAT_WS(' ', u.first_name, u.last_name) AS name,
                       u.email, u.location, u.created_at,
                       st.label AS skin_type
                FROM public.app_users u
                LEFT JOIN skin_types st ON st.skin_type_id = u.skin_type_id
                WHERE u.user_id = :id
                """
            ),
            {"id": new_id},
        ).mappings().first()

    return dict(row)


@router.get("/users")
def get_all_users():
    """List users (primarily for debugging/testing)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT u.user_id AS id,
                       CONCAT_WS(' ', u.first_name, u.last_name) AS name,
                       u.email, u.location, u.created_at,
                       st.label AS skin_type
                FROM public.app_users u
                LEFT JOIN skin_types st ON st.skin_type_id = u.skin_type_id
                ORDER BY u.user_id DESC
                """
            )
        ).mappings().all()

    return [dict(r) for r in rows]
