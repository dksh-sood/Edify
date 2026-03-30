from pydantic import BaseModel
import os
from typing import List
from pathlib import Path
from dotenv import load_dotenv

# Ensure backend/.env is loaded even when uvicorn is started from another cwd
_base_dir = Path(__file__).resolve().parents[2]
load_dotenv(_base_dir / ".env")

class Settings(BaseModel):
    env: str = os.getenv("ENV", "development")
    backend_host: str = os.getenv("BACKEND_HOST", "0.0.0.0")
    backend_port: int = int(os.getenv("BACKEND_PORT", "8000"))
    storage_dir: str = os.getenv("STORAGE_DIR", str(_base_dir / "storage"))

    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_db: str = os.getenv("MONGODB_DB", "edify")

    kinde_issuer_url: str = os.getenv("KINDE_ISSUER_URL", "")
    kinde_client_id: str = os.getenv("KINDE_CLIENT_ID", "")
    kinde_audience: str | None = os.getenv("KINDE_AUDIENCE") or None

    google_ai_api_key: str = os.getenv("GOOGLE_AI_API_KEY", "")
    google_ai_model: str = os.getenv("GOOGLE_AI_MODEL", "gemini-2.5-flash")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")

    allowed_origins: List[str] = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

settings = Settings()
