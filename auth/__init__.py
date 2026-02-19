"""
auth package — DermaFlow authentication helpers
Student: Catherine Fenton — 122308571

Contains:
- deps.py: FastAPI dependency to resolve the current user from a JWT.
- security.py: password hashing (bcrypt) + JWT creation/verification.

This package is imported by the running API (e.g., routers depend on current_user).
"""
