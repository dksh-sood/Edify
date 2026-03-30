from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.core.config import settings
from app.routers import courses, documents, forums, pathways, mock_interviews, events, internships, chat, calculate, run_code
from app.socketio_server import sio
import socketio as socketio_pkg

fastapi_app = FastAPI(title="Edify Backend")

origins = settings.allowed_origins or ["http://localhost:3000"]

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

storage_dir = Path(settings.storage_dir)
storage_dir.mkdir(parents=True, exist_ok=True)
fastapi_app.mount("/storage", StaticFiles(directory=str(storage_dir)), name="storage")

@fastapi_app.get("/")
async def root():
    return {"message": "Edify backend running", "health": "/health"}

@fastapi_app.get("/favicon.ico")
async def favicon():
    return {}

@fastapi_app.get("/health")
async def health():
    return {"status": "ok"}

fastapi_app.include_router(courses.router, prefix="/courses", tags=["courses"])
fastapi_app.include_router(documents.router, prefix="/documents", tags=["documents"])
fastapi_app.include_router(forums.router, prefix="/forums", tags=["forums"])
fastapi_app.include_router(pathways.router, prefix="/pathways", tags=["pathways"])
fastapi_app.include_router(mock_interviews.router, prefix="/mock-interviews", tags=["mock-interviews"])
fastapi_app.include_router(events.router, prefix="/events", tags=["events"])
fastapi_app.include_router(internships.router, prefix="/internships", tags=["internships"])
fastapi_app.include_router(chat.router, prefix="/chat", tags=["chat"])
fastapi_app.include_router(calculate.router, prefix="/calculate", tags=["calculate"])
fastapi_app.include_router(run_code.router, prefix="/run-code", tags=["run-code"])

app = socketio_pkg.ASGIApp(sio, fastapi_app)
