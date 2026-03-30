from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import asyncio
import tempfile
import os

router = APIRouter()

@router.post("")
async def run_code(payload: Dict[str, Any]):
    code = payload.get("code")
    language = payload.get("language")
    if not code or not language:
        raise HTTPException(status_code=400, detail="Code and language are required")

    if language not in {"python", "javascript", "js"}:
        raise HTTPException(status_code=400, detail="Unsupported language")

    suffix = ".py" if language == "python" else ".js"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as f:
        f.write(code.encode("utf-8"))
        file_path = f.name

    try:
        cmd = ["python", file_path] if language == "python" else ["node", file_path]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            raise HTTPException(status_code=500, detail="Execution timed out")

        output = (stdout or b"") + (stderr or b"")
        return {"output": output.decode("utf-8")}
    except Exception:
        raise HTTPException(status_code=500, detail="Error executing code")
    finally:
        try:
            os.unlink(file_path)
        except Exception:
            pass
