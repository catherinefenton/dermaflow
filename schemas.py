# schemas.py — Pydantic request/response models (FastAPI)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# Central place for Pydantic models used by the API.
# These models:
# - Validate incoming JSON (types, required fields, basic constraints)
# - Provide clear documentation in Swagger/OpenAPI
# - Keep route files cleaner by removing repeated validation logic
#
# NOTE:
# These are *input* schemas used by routes (Register/Login/Profile updates etc.).
# Database structure is handled separately in MySQL (tables/columns/constraints).

from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, ConfigDict


# -----------------------------------------------------------------------------
# Auth / Profile
# -----------------------------------------------------------------------------

class RegisterIn(BaseModel):
  """
  Register payload used by POST /auth/register

  Why these fields:
  - email/password: required to create credentials
  - name: optional (split into first/last server-side for nicer UX)
  - skin_type / skin_type_code: optional profile attribute captured at signup
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  email: EmailStr = Field(..., description="User email address (unique).")
  password: str = Field(..., min_length=6, description="User password (min 6 chars).")
  name: Optional[str] = Field(None, description="Full name (optional).")
  skin_type: Optional[str] = Field(None, description="Skin type label or free text (optional).")
  skin_type_code: Optional[str] = Field(None, description="Skin type code (e.g., 'dry', 'oily', 'other').")


class LoginIn(BaseModel):
  """
  Login payload used by POST /auth/login
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  email: EmailStr = Field(..., description="User email address.")
  password: str = Field(..., description="User password.")


class ProfileUpdateIn(BaseModel):
  """
  Profile update payload used by PUT /me

  Only fields included are updated; missing fields remain unchanged.
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  name: Optional[str] = Field(None, description="Updated full name (optional).")
  skin_type: Optional[str] = Field(None, description="Updated skin type label/free text (optional).")
  skin_type_code: Optional[str] = Field(None, description="Updated skin type code (optional).")


# -----------------------------------------------------------------------------
# Routines / Steps
# -----------------------------------------------------------------------------

class RoutineCreateIn(BaseModel):
  """
  Create/rename routine payload used by:
  - POST /routines
  - PUT  /routines/{routine_id}
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  name: str = Field(..., min_length=1, max_length=80, description="Routine name (e.g., 'Morning routine').")


class RoutineStepBody(BaseModel):
  """
  Create step payload used by POST /routines/{routine_id}/steps

  Notes:
  - product_id is optional (future-proofing / optional linking to product table)
  - step_order is required to support manual ordering + drag reorder later
  - notes is optional per-step text (Iteration 3 feature)
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  product_id: Optional[int] = Field(None, description="Optional product reference ID.")
  step_order: int = Field(..., ge=1, description="Step order number (1..n).")
  step_name: str = Field(..., min_length=1, max_length=120, description="Step name (e.g., 'Cleanser').")
  notes: Optional[str] = Field(None, max_length=1000, description="Optional notes for this step.")


class RoutineStepCreateIn(RoutineStepBody):
  """
  Alternate create step payload used by POST /routine-steps
  (same fields as RoutineStepBody but includes routine_id)
  """
  routine_id: int = Field(..., ge=1, description="Parent routine ID.")


class RoutineStepUpdateIn(BaseModel):
  """
  Update step payload used by PUT /routine-steps/{step_id}

  All fields optional: routes use COALESCE in SQL so only provided values change.
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  step_order: Optional[int] = Field(None, ge=1, description="New step order number (optional).")
  step_name: Optional[str] = Field(None, min_length=1, max_length=120, description="New step name (optional).")
  notes: Optional[str] = Field(None, max_length=1000, description="New notes text (optional).")


# -----------------------------------------------------------------------------
# Habit Logs (AM/PM tracking)
# -----------------------------------------------------------------------------

class HabitLogIn(BaseModel):
  """
  Habit log payload used by POST /habit-logs

  Supports:
  - AM/PM status per date
  - Optional note
  - Optional routine_id link (kept optional so the log can exist independently)
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  routine_id: Optional[int] = Field(None, ge=1, description="Optional routine ID.")
  log_date: Optional[date] = Field(None, description="Date for the log (defaults to today server-side).")
  period: str = Field(..., description="AM or PM")
  status: str = Field(..., description="Completed or Skipped")
  note: Optional[str] = Field(None, max_length=600, description="Optional free-text note.")


# -----------------------------------------------------------------------------
# Step Completions (per-day tick-off)
# -----------------------------------------------------------------------------

class StepCompletionIn(BaseModel):
  """
  Step completion payload used by POST /step-completions

  Used to persist per-day step completion:
  - completion_date defaults to today server-side if not provided
  - is_done supports toggling on/off without deleting rows
  """
  model_config = ConfigDict(str_strip_whitespace=True)

  step_id: int = Field(..., ge=1, description="Routine step ID.")
  completion_date: Optional[date] = Field(None, description="Date of completion (defaults to today).")
  is_done: bool = Field(..., description="True if completed, false if not completed.")
