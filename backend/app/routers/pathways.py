from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Any, Dict

from app.core.security import get_current_user
from app.db.mongo import get_db
from app.utils.serialize import serialize_id, serialize_list

router = APIRouter()

@router.post("")
async def create_pathway(payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    pathways = db["pathways"]

    pathway = {
        "slug": payload.get("slug"),
        "title": payload.get("title"),
        "description": payload.get("description"),
        "estimatedTime": payload.get("estimatedTime"),
        "difficulty": payload.get("difficulty"),
        "prerequisites": payload.get("prerequisites", []),
        "steps": payload.get("steps", []),
        "createdBy": user.get("id"),
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }
    if not pathway["slug"]:
        raise HTTPException(status_code=400, detail="slug is required")

    await pathways.insert_one(pathway)
    return {"success": True, "data": pathway}

@router.get("")
async def list_pathways():
    db = await get_db()
    pathways = db["pathways"]
    items = await pathways.find({}).sort("createdAt", -1).to_list(200)
    return {"success": True, "data": serialize_list(items)}

@router.get("/{slug}")
async def get_pathway(slug: str):
    db = await get_db()
    pathways = db["pathways"]
    pathway = await pathways.find_one({"slug": slug})
    if not pathway:
        raise HTTPException(status_code=404, detail="Pathway not found")
    return {"success": True, "data": serialize_id(pathway)}

@router.post("/progress")
async def update_progress(payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    progress_col = db["user_progress"]

    pathway_id = payload.get("pathwayId")
    completed_steps = payload.get("completedSteps")
    if pathway_id is None:
        raise HTTPException(status_code=400, detail="pathwayId is required")

    await progress_col.update_one(
        {"userId": user.get("id"), "pathwayId": pathway_id},
        {"$set": {"completedSteps": completed_steps, "updatedAt": datetime.utcnow().isoformat()}, "$setOnInsert": {"createdAt": datetime.utcnow().isoformat()}},
        upsert=True,
    )
    return {"success": True}

@router.get("/progress/me")
async def get_progress(pathwayId: int = Query(...), user=Depends(get_current_user)):
    db = await get_db()
    progress_col = db["user_progress"]
    progress = await progress_col.find_one({"userId": user.get("id"), "pathwayId": pathwayId})
    return {"success": True, "data": progress.get("completedSteps", 0) if progress else 0}
