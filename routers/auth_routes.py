# routers/auth_routes.py — Authentication (register + login)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Register new users (store hashed password, store skin type choice).
# - Log users in (verify password hash) and return a JWT bearer token.
#
# DESIGN CHOICES:
# - JWT contains "sub" = email (simple + matches current_user() dependency).
# - Passwords are never stored in plaintext (bcrypt hash only).
# - Register blocks duplicate emails (409 Conflict).
# - Login returns 401 for invalid credentials (don’t reveal if email exists).
#
# References:
# - FastAPI APIRouter: https://fastapi.tiangolo.com/tutorial/bigger-applications/
# - SQLAlchemy text() queries: https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text
# - bcrypt + hashing: https://pypi.org/project/bcrypt/
# - JWT auth (FastAPI): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from db import engine
from schemas import RegisterIn, LoginIn
from auth.security import hash_password, verify_password, create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])


def split_name(full: str | None) -> tuple[str, str]:
    """
    Split a display name into first + last name.

    Examples:
      - "Catherine" -> ("Catherine", "")
      - "Catherine Fenton" -> ("Catherine", "Fenton")
      - "Catherine Mary Fenton" -> ("Catherine", "Mary Fenton")

    Note: This is intentionally simple (no complex name rules).
    """
    if not full:
        return "", ""
    parts = full.strip().split()
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def skin_type_id_for_from_any(
    conn,
    *,
    code: str | None,
    label_or_free_text: str | None,
):
    """
    Resolve skin_type_id from either:
    - a skin type code (e.g. "oily", "dry", "combo", "other")
    - or a label/free-text string (e.g. user selects from UI or types)

    Fallback:
    - if nothing matches, default to the "other" skin type if it exists.
    """
    # 1) Try code match (preferred)
    if code:
        row = conn.execute(
            text("SELECT skin_type_id FROM public.skin_types WHERE LOWER(code)=:v LIMIT 1"),
            {"v": code.strip().lower()},
        ).first()
        if row:
            return int(row[0])

    # 2) Try label match (only if no code match)
    if label_or_free_text:
        v = label_or_free_text.strip().lower()
        if v:
            row = conn.execute(
                text("SELECT skin_type_id FROM public.skin_types WHERE LOWER(label)=:v LIMIT 1"),
                {"v": v},
            ).first()
            if row:
                return int(row[0])

    # 3) Fallback to "other"
    row = conn.execute(
        text("SELECT skin_type_id FROM public.skin_types WHERE code='other' LIMIT 1")
    ).first()
    return int(row[0]) if row else None


@router.post("/register")
def auth_register(data: RegisterIn):
    """
    Create a new user account.

    Steps:
    - Normalise email.
    - Check for duplicate email.
    - Split the provided name into first/last.
    - Resolve skin_type_id from code or label.
    - Hash password (bcrypt).
    - Insert user row.
    - Return JWT bearer token so the app can sign in immediately.
    """
    email = data.email.lower().strip()

    with engine.begin() as conn:
        # Duplicate email protection
        if conn.execute(text("SELECT 1 FROM public.app_users WHERE email=:e"), {"e": email}).first():
            raise HTTPException(status_code=409, detail="Email already exists")

        first, last = split_name(data.name)

        st_id = skin_type_id_for_from_any(
            conn,
            code=(data.skin_type_code or "").strip() or None,
            label_or_free_text=data.skin_type,
        )

        pw_hash = hash_password(data.password)

        conn.execute(
            text(
                """
                INSERT INTO public.app_users (first_name, last_name, email, password_hash, skin_type_id)
                VALUES (:fn, :ln, :em, :ph, :stid)
                """
            ),
            {
                "fn": first or None,
                "ln": last or None,
                "em": email,
                "ph": pw_hash,
                "stid": st_id,
            },
        )

    token = create_access_token(email)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/login")
def auth_login(data: LoginIn):
    """
    Authenticate user and return JWT bearer token.

    - Normalise email.
    - Fetch stored password hash from DB.
    - Verify password using bcrypt.
    - Return signed JWT.

    Security note:
    - Use same error message for "user not found" and "wrong password"
      so we don't leak whether an email exists.
    """
    email = data.email.lower().strip()

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT user_id, email, password_hash FROM public.app_users WHERE email=:e"),
            {"e": email},
        ).first()

        if not row:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        _, _, stored_hash = row

        if not stored_hash or not verify_password(data.password, stored_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(email)
    return {"access_token": token, "token_type": "bearer"}
