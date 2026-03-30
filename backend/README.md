# Edify Backend (FastAPI + MongoDB)

## Setup
1. Create a virtual environment and install deps:

```bash
python -m venv .venv
. .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

2. Create `.env` from `.env.example` and set:
- `MONGODB_URI`
- `MONGODB_DB`
- `KINDE_ISSUER_URL`
- `KINDE_CLIENT_ID`
- `GOOGLE_AI_API_KEY`
- `GOOGLE_AI_MODEL` (optional, defaults to `gemini-2.5-flash`)
- `GROQ_API_KEY`
- `ALLOWED_ORIGINS` (e.g. `http://localhost:3000`)
- `STORAGE_DIR` (optional, defaults to `backend/storage`)

3. Install Playwright browsers (for events/internships scraping):

```bash
python -m playwright install
```

4. Run the server:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Notes
- Socket.IO is served from the same backend at the default `/socket.io` path.
- The frontend should set `NEXT_PUBLIC_BACKEND_URL=http://localhost:8000`.
- The AI interview flow stores uploaded recordings under `backend/storage/mock-interviews/...` and serves them from `/storage/...`.
- Resume upload supports `.pdf`, `.docx`, `.txt`, and `.md`. PDF parsing requires `pypdf`, which is now included in `requirements.txt`.
- New AI interview endpoints live under `/mock-interviews/ai/...` for:
  - company catalog
  - resume upload and question generation
  - AI session creation and listing
  - per-question answer analysis
  - final report generation
