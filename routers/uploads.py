# routers/uploads.py — Step photo upload/delete endpoints
# Student: Catherine Fenton — 122308571
#
# PURPOSE (Iteration 3):
# - Allow the user to attach a photo to a routine step (persisted in routine_steps.photo_url).
# - Allow the user to remove that photo (set photo_url = NULL).
# - Optional cleanup: delete the old file on disk after a successful DB update (prevents storage build-up).
#
# SECURITY MODEL:
# - Requires JWT (Depends(current_user)).
# - Ownership is enforced via JOIN routine_steps -> routines where routines.user_id = current user.
#   This prevents ID-guessing attacks (users cannot upload/delete photos for steps they don’t own).
#
# FILE SYSTEM SAFETY:
# - _safe_delete_file() only deletes files inside /static/steps/ and inside UPLOAD_DIR.
# - This prevents path traversal or accidental deletion outside the app directory.
#
# References:
# - FastAPI UploadFile: https://fastapi.tiangolo.com/tutorial/request-files/
# - Pathlib safe path operations: https://docs.python.org/3/library/pathlib.html
# - SQLAlchemy text(): https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.text

from pathlib import Path
import shutil
import uuid

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from sqlalchemy import text

from db import engine
from auth.deps import current_user, DBUser

router = APIRouter(tags=["uploads"])

# Store uploaded step photos under backend/static/steps/
UPLOAD_DIR = Path(__file__).resolve().parents[1] / "static" / "steps"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _safe_delete_file(photo_url: str | None) -> None:
    """
    Deletes a file from disk ONLY if it:
    - matches expected URL format: /static/steps/<filename>
    - resolves inside UPLOAD_DIR
    This prevents deleting random paths if photo_url is tampered with.
    """
    if not photo_url:
        return
    if not photo_url.startswith("/static/steps/"):
        return

    filename = photo_url.split("/static/steps/", 1)[-1]
    path = (UPLOAD_DIR / filename).resolve()

    # Hard safety: only allow deletion inside UPLOAD_DIR
    if UPLOAD_DIR.resolve() not in path.parents:
        return

    if path.exists() and path.is_file():
        try:
            path.unlink()
        except Exception:
            # Non-fatal: if delete fails, app still works and DB is correct.
            pass


@router.post("/routine-steps/{step_id}/photo")
def upload_step_photo(
    step_id: int,
    file: UploadFile = File(...),
    user: DBUser = Depends(current_user),
):
    """
    Upload / replace a step photo.

    Flow:
    1) Validate file is an image.
    2) Confirm step belongs to user (JOIN ownership check).
    3) Save the file to disk with a unique filename.
    4) Update routine_steps.photo_url.
    5) Delete old file from disk (optional cleanup).
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # Default extension; allow safe known extensions
    ext = ".jpg"
    if file.filename and "." in file.filename:
        raw_ext = "." + file.filename.rsplit(".", 1)[-1].lower()
        if raw_ext in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = raw_ext

    old_photo_url: str | None = None
    photo_url: str

    with engine.begin() as conn:
        # IMPORTANT: use .mappings() so we can access row["photo_url"] safely
        row = (
            conn.execute(
                text(
                    """
                    SELECT rs.step_id, rs.photo_url
                    FROM routine_steps rs
                    JOIN public.routines r ON r.routine_id = rs.routine_id
                    WHERE rs.step_id = :sid AND r.user_id = :u
                    """
                ),
                {"sid": step_id, "u": user.user_id},
            )
            .mappings()
            .first()
        )

        if not row:
            raise HTTPException(status_code=404, detail="Step not found")

        old_photo_url = row["photo_url"]

        # Unique filename: ties file to user + step + uuid (prevents collisions)
        filename = f"{user.user_id}_{step_id}_{uuid.uuid4().hex}{ext}"
        save_path = UPLOAD_DIR / filename

        try:
            with save_path.open("wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()

        photo_url = f"/static/steps/{filename}"

        # Persist the new URL in MySQL (frontend can render this via BASE + photo_url)
        conn.execute(
            text("UPDATE routine_steps SET photo_url = :p WHERE step_id = :sid"),
            {"p": photo_url, "sid": step_id},
        )

    # Cleanup happens AFTER DB update succeeds (so we never delete the only photo by accident)
    _safe_delete_file(old_photo_url)

    return {"photo_url": photo_url}


@router.delete("/routine-steps/{step_id}/photo")
def delete_step_photo(
    step_id: int,
    user: DBUser = Depends(current_user),
):
    """
    Remove a step photo.

    Behaviour:
    - Sets routine_steps.photo_url = NULL
    - Deletes the file from disk (optional cleanup)
    """
    old_photo_url: str | None = None

    with engine.begin() as conn:
        row = (
            conn.execute(
                text(
                    """
                    SELECT rs.step_id, rs.photo_url
                    FROM routine_steps rs
                    JOIN public.routines r ON r.routine_id = rs.routine_id
                    WHERE rs.step_id = :sid AND r.user_id = :u
                    """
                ),
                {"sid": step_id, "u": user.user_id},
            )
            .mappings()
            .first()
        )

        if not row:
            raise HTTPException(status_code=404, detail="Step not found")

        old_photo_url = row["photo_url"]

        conn.execute(
            text("UPDATE routine_steps SET photo_url = NULL WHERE step_id = :sid"),
            {"sid": step_id},
        )

    _safe_delete_file(old_photo_url)

    return {"ok": True}
