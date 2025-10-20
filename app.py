import os, json
from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("DB_URL not set in .env")

engine = create_engine(DB_URL, pool_pre_ping=True)
app = FastAPI(title="DermaFlow API")

@app.get("/health")
def health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"status": "ok"}

class UserIn(BaseModel):
    email: str
    name: Optional[str] = None
    skin_type: Optional[str] = None

@app.post("/users")
def create_user(user: UserIn):
    with engine.begin() as conn:
        res = conn.execute(
            text("""INSERT INTO users(email, name, skin_type)
                    VALUES (:e,:n,:s)"""),
            {"e": user.email, "n": user.name, "s": user.skin_type}
        )
        user_id = res.lastrowid
    return {"id": user_id, **user.model_dump()}

@app.get("/users/{user_id}")
def get_user(user_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text("""SELECT id,email,name,skin_type,created_at
                    FROM users WHERE id=:id"""),
            {"id": user_id}
        ).m.fetchone()
    if not row:
        raise HTTPException(404, "User not found")
    return dict(row._mapping)

class RoutineIn(BaseModel):
    user_id: int
    name: str
    period: str  # AM, PM, CUSTOM
    steps: List[str]

@app.post("/routines")
def create_routine(r: RoutineIn):
    steps_json = json.dumps(r.steps)
    with engine.begin() as conn:
        res = conn.execute(
            text("""INSERT INTO routines(user_id,name,period,steps)
                    VALUES (:u,:n,:p,:s)"""),
            {"u": r.user_id, "n": r.name, "p": r.period, "s": steps_json}
        )
        rid = res.lastrowid
    return {"id": rid, **r.model_dump()}

@app.get("/routines/{routine_id}")
def get_routine(routine_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text("""SELECT id,user_id,name,period,steps
                    FROM routines WHERE id=:id"""),
            {"id": routine_id}
        ).m.fetchone()
    if not row:
        raise HTTPException(404, "Routine not found")
    data = dict(row._mapping)
    data["steps"] = json.loads(data["steps"])
    return data

@app.post("/progress/log")
def log_progress(user_id: int, routine_id: int, notes: Optional[str] = None):
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO progress_logs(user_id,routine_id,completed_at,notes)
                    VALUES (:u,:r,:t,:n)"""),
            {"u": user_id, "r": routine_id, "t": datetime.utcnow(), "n": notes}
        )
    return {"ok": True}
