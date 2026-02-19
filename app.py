# app.py — DermaFlow API main entry (modular)
# Student: Catherine Fenton — 122308571
#
# PURPOSE:
# - Central FastAPI entry point that wires up:
#   - CORS (so the Expo app can call the API during development)
#   - /static file serving (step photos live in backend/static/steps)
#   - Modular routers for each feature area (auth, routines, uploads, etc.)
#
# ARCHITECTURE:
# - Each feature lives in a router inside /routers, which keeps app.py clean.
# - DB connection is handled separately in db.py (SQLAlchemy engine).
#
# SECURITY NOTE:
# - allow_origins=["*"] is dev-only. In production, this should be restricted to your
#   deployment domains (Iteration 4 hardening).
#
# References:
# - FastAPI: https://fastapi.tiangolo.com/
# - CORS Middleware: https://fastapi.tiangolo.com/tutorial/cors/
# - StaticFiles: https://fastapi.tiangolo.com/tutorial/static-files/

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers.health import router as health_router
from routers.auth_routes import router as auth_router
from routers.routines import router as routines_router
from routers.uploads import router as uploads_router
from routers.me import router as me_router
from routers.habit_logs import router as habit_router
from routers.step_completions import router as completions_router
from routers.users import router as users_router

app = FastAPI(title="DermaFlow API")


# --- Root route (nice UX for Render) -----------------------------------------
# Render will ping "/" sometimes. Having a simple root route avoids 404s and
# gives a quick "is the API up?" response in a browser.
@app.get("/")
def root():
    return {"name": "DermaFlow API", "status": "running"}


# --- CORS (DEV) --------------------------------------------------------------
# Allows the Expo app (running on phone / simulator) to call the API.
# In production this should be locked down to trusted origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # dev-only wildcard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static hosting for uploaded photos --------------------------------------
# Uploaded step photos are saved in /static/steps and served as:
#   http://<API_HOST>:8000/static/steps/<filename>
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- Routers (feature modules) -----------------------------------------------
app.include_router(health_router)       # /health (sanity check / uptime)
app.include_router(auth_router)         # /auth/login, /auth/register
app.include_router(me_router)           # /me profile
app.include_router(users_router)        # /users (debug/testing)
app.include_router(routines_router)     # /routines + /routine-steps
app.include_router(habit_router)        # /habit-logs
app.include_router(completions_router)  # /step-completions
app.include_router(uploads_router)      # /routine-steps/{id}/photo (POST/DELETE)
