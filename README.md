# DermaFlow — Personal Skincare Routine Tracker

Mobile app (Expo/React Native) + FastAPI backend + MySQL. Users can register/login, save a profile (skin type), create routines, and add ordered steps. Only the signed-in user can see or change their own data.

## What this folder is
Backend (FastAPI) with:
- SQLAlchemy Engine (`pool_pre_ping=True`) to avoid stale connections. [D4]
- JWT auth with `python-jose`; passwords hashed with `bcrypt`.         [L1][L2]
- Environment variables loaded from `.env` using `python-dotenv` in `db.py`
  (the API reads secrets/settings via `os.getenv`).                    [D5]

## Quick start

```bash
# 1) Python venv (I used 3.13 locally)
python -m venv .venv
source .venv/bin/activate

# 2) Install deps
pip install -r requirements.txt

# 3) Create .env (never commit secrets)
cat > .env << 'EOF'
DB_URL=mysql+pymysql://derma:DermaPass123!@127.0.0.1:3306/dermaflow
SECRET_KEY=change-me-in-dev
ACCESS_TOKEN_EXPIRE_MINUTES=720
EOF

# 4) Run the API
uvicorn app:app --reload
# (or) uvicorn app:app --host 0.0.0.0 --port 8000 --reload
