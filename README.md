# Graph of Thoughts (GoT)

University assessment implementation of Besta et al., AAAI 2024 — **Graph of Thoughts**.

- **Backend** (engine + CLI + FastAPI): see [`backend/README.md`](backend/README.md)
- **Frontend** (React + React Flow live visualizer): `frontend/`

Quick start:

```bash
# 1) Backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # Windows
pip install -r requirements.txt
copy .env.example .env         # add GROQ_API_KEY
python run_cli.py --numbers 48 --chunk-size 8

# 2) API + UI
uvicorn api.server:app --reload --port 8000
# other terminal:
cd ../frontend && npm install && npm run dev
```
