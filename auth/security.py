# auth/security.py — Password hashing + JWT helpers
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Hash/verify passwords safely using bcrypt.
# - Create signed JWT access tokens for login.
#
# NOTES:
# - SECRET_KEY should be set in the backend .env for real use.
# - If SECRET_KEY is missing, this file falls back to a dev value for local testing.
#
# References:
# - bcrypt (Python): https://pypi.org/project/bcrypt/
# - python-jose JWT encode: https://python-jose.readthedocs.io/en/latest/jwt/api.html
# - JWT "sub" and "exp" claim conventions: https://www.rfc-editor.org/rfc/rfc7519

import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt

# ⚠️ In production, always set SECRET_KEY in .env (never commit real secrets).
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"

# Token lifetime in minutes (e.g., 720 = 12 hours)
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "720"))


def hash_password(pw: Optional[str]) -> Optional[str]:
    """
    Hash a plaintext password using bcrypt.

    Returns:
      - hashed password string (utf-8) if pw exists
      - None if pw is None/empty (defensive)
    """
    if not pw:
        return None

    # bcrypt.gensalt() generates a random salt each time (good: prevents rainbow-table reuse).
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """
    Compare a plaintext password against a stored bcrypt hash.

    Returns True if match, False otherwise.
    """
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        # Defensive: if the stored hash is malformed, treat as non-match.
        return False


def create_access_token(sub: str) -> str:
    """
    Create a signed JWT access token.

    Claims:
      - sub: subject (in this project, the user's email)
      - exp: expiry timestamp (UTC)

    Returns: JWT string
    """
    exp = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    # jwt.encode returns a signed string token.
    return jwt.encode(
        {"sub": sub, "exp": exp},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
