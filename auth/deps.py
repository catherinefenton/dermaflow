# auth/deps.py — FastAPI dependency for "current user" (JWT -> DB user)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Centralises authentication for protected API routes.
# - Decodes JWTs (Bearer token) and converts the token subject ("sub") into a DB user.
# - Used as a dependency: Depends(current_user) on any endpoint that needs a logged-in user.
#
# HOW IT WORKS (high-level):
# 1) OAuth2PasswordBearer reads the Authorization: Bearer <token> header.
# 2) We decode the JWT using SECRET_KEY + ALGORITHM.
# 3) We treat payload["sub"] as the user's email.
# 4) We fetch the user row and return a typed DBUser model.
#
# SECURITY NOTE:
# - A token alone is not enough; we also confirm the user exists in the database.
# - If the user no longer exists, the token is treated as invalid (401).
#
# References:
# - FastAPI Security (OAuth2PasswordBearer): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/
# - python-jose JWT: https://python-jose.readthedocs.io/en/latest/jwt/api.html
# - SQLAlchemy text() queries: https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import text

from db import engine
from auth.security import SECRET_KEY, ALGORITHM

# FastAPI will use this to read bearer tokens from the Authorization header.
# tokenUrl is the login endpoint in auth_routes.py.
oauth2 = OAuth2PasswordBearer(tokenUrl="/auth/login")


class DBUser(BaseModel):
    """
    Minimal user object returned by current_user().
    This is what routes receive when they depend on Depends(current_user).
    """
    user_id: int
    email: EmailStr
    first_name: Optional[str] = ""
    last_name: Optional[str] = ""
    skin_type_id: Optional[int] = None


def fetch_user_by_email(email: str) -> Optional[DBUser]:
    """
    DB lookup used by current_user().
    Returns a DBUser if found, otherwise None.
    """
    with engine.connect() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT user_id, email, first_name, last_name, skin_type_id
                    FROM public.app_users
                    WHERE email = :e
                    """
                ),
                {"e": email},
            )
            .mappings()
            .first()
        )

    return DBUser(**row) if row else None


def current_user(token: str = Depends(oauth2)) -> DBUser:
    """
    FastAPI dependency that returns the logged-in user.

    - Reads a Bearer token from the request.
    - Decodes the JWT and extracts "sub" (subject).
    - "sub" is treated as the user's email.
    - Looks up the user in MySQL and returns DBUser.

    Raises:
      - 401 if token is missing/invalid/expired OR user cannot be found.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if not email:
            # Token structure isn't what we expect (no subject)
            raise HTTPException(
                status_code=401,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except JWTError:
        # JWTError covers invalid signature, malformed token, expired exp, etc.
        raise HTTPException(
            status_code=401,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = fetch_user_by_email(email)
    if not user:
        # User could have been deleted or email changed since token was issued.
        raise HTTPException(
            status_code=401,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user
