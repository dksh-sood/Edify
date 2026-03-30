from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Any, Dict
from bson import ObjectId

from app.core.security import get_current_user
from app.db.mongo import get_db
from app.utils.serialize import serialize_id, serialize_list

router = APIRouter()

@router.get("/topics")
async def list_topics(courseId: str = Query(...)):
    db = await get_db()
    topics = db["forum_topics"]
    items = await topics.find({"courseId": courseId}).sort("createdAt", 1).to_list(200)
    return {"success": True, "data": serialize_list(items)}

@router.post("/topics")
async def create_topic(payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    topics = db["forum_topics"]

    topic = {
        "courseId": payload.get("courseId"),
        "userId": user.get("given_name") or user.get("email"),
        "title": payload.get("title"),
        "content": payload.get("content"),
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }
    if not topic["courseId"] or not topic["title"] or not topic["content"]:
        raise HTTPException(status_code=400, detail="courseId, title, and content are required")

    result = await topics.insert_one(topic)
    topic["id"] = str(result.inserted_id)
    return {"success": True, "data": topic}

@router.get("/topics/{topicId}/replies")
async def list_replies(topicId: str):
    db = await get_db()
    replies = db["forum_replies"]
    items = await replies.find({"topicId": topicId}).sort("createdAt", 1).to_list(500)
    return {"success": True, "data": serialize_list(items)}

@router.post("/topics/{topicId}/replies")
async def create_reply(topicId: str, payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    replies = db["forum_replies"]

    reply = {
        "topicId": topicId,
        "userId": user.get("given_name") or user.get("email"),
        "content": payload.get("content"),
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }
    if not reply["content"]:
        raise HTTPException(status_code=400, detail="content is required")

    result = await replies.insert_one(reply)
    reply["id"] = str(result.inserted_id)
    return {"success": True, "data": reply}
