from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from fastapi import UploadFile

from app.core.config import settings


async def save_uploaded_file(
    upload: UploadFile,
    *,
    session_id: str,
    category: str,
) -> Dict[str, Any]:
    storage_root = Path(settings.storage_dir)
    target_dir = storage_root / "mock-interviews" / session_id / category
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(upload.filename or "").suffix or ".bin"
    file_name = f"{uuid4().hex}{suffix}"
    target_path = target_dir / file_name

    content = await upload.read()
    target_path.write_bytes(content)

    relative_path = target_path.relative_to(storage_root).as_posix()
    return {
        "fileName": upload.filename or file_name,
        "storedName": file_name,
        "contentType": upload.content_type or "application/octet-stream",
        "size": len(content),
        "relativePath": relative_path,
        "url": f"/storage/{relative_path}",
    }
