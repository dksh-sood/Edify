from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime
from typing import Any, Dict, List

from app.core.security import get_current_user, get_optional_user
from app.db.mongo import get_db
from app.utils.serialize import serialize_id, serialize_list

router = APIRouter()

@router.post("/")
async def create_course(payload: Dict[str, Any], user=Depends(get_optional_user)):
    db = await get_db()
    courses = db["courses"]
    anon_user = {
        "id": payload.get("createdBy") or payload.get("email") or "anonymous",
        "email": payload.get("createdBy"),
        "given_name": payload.get("username") or "Anonymous",
        "picture": payload.get("userprofileimage"),
    }
    user = user or anon_user

    course = {
        "courseId": payload.get("courseId"),
        "courseName": payload.get("courseName"),
        "category": payload.get("category"),
        "level": payload.get("level"),
        "courseOutput": payload.get("courseOutput"),
        "isVideo": payload.get("isVideo", "Yes"),
        "username": payload.get("username") or user.get("given_name"),
        "userprofileimage": payload.get("userprofileimage") or user.get("picture"),
        "createdBy": user.get("email"),
        "userId": user.get("id"),
        "courseBanner": payload.get("courseBanner"),
        "isPublished": bool(payload.get("isPublished", False)),
        "progress": float(payload.get("progress", 0.0)),
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }

    if not course["courseId"]:
        raise HTTPException(status_code=400, detail="courseId is required")

    try:
        await courses.insert_one(course)
        return {"success": True, "data": serialize_id(course)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create course: {e}")

@router.get("/me")
async def list_my_courses(user=Depends(get_current_user)):
    db = await get_db()
    courses = db["courses"]
    items = await courses.find({"userId": user.get("id")}).sort("createdAt", -1).to_list(200)
    return {"success": True, "data": serialize_list(items)}

@router.get("/")
async def list_courses(page: int = Query(1, ge=1), limit: int = Query(8, ge=1, le=50)):
    db = await get_db()
    courses = db["courses"]
    skip = (page - 1) * limit
    items = await courses.find({}).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
    return {"success": True, "data": serialize_list(items)}

@router.get("/{courseId}")
async def get_course(courseId: str):
    db = await get_db()
    courses = db["courses"]
    course = await courses.find_one({"courseId": courseId})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return {"success": True, "data": serialize_id(course)}

@router.patch("/{courseId}")
async def update_course(courseId: str, payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    courses = db["courses"]

    course = await courses.find_one({"courseId": courseId})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("userId") != user.get("id"):
        raise HTTPException(status_code=403, detail="Forbidden")

    update_fields = {k: v for k, v in payload.items() if k in {
        "courseOutput",
        "courseBanner",
        "isPublished",
        "progress",
        "courseName",
        "category",
        "level",
    }}
    update_fields["updatedAt"] = datetime.utcnow().isoformat()

    await courses.update_one({"courseId": courseId}, {"$set": update_fields})
    updated = await courses.find_one({"courseId": courseId})
    return {"success": True, "data": serialize_id(updated)}

@router.delete("/{courseId}")
async def delete_course(courseId: str, user=Depends(get_current_user)):
    db = await get_db()
    courses = db["courses"]

    course = await courses.find_one({"courseId": courseId})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("userId") != user.get("id"):
        raise HTTPException(status_code=403, detail="Forbidden")

    await courses.delete_one({"courseId": courseId})
    return {"success": True}

@router.post("/{courseId}/chapters")
async def upsert_chapters(courseId: str, payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    chapters_col = db["course_chapters"]
    courses = db["courses"]

    course = await courses.find_one({"courseId": courseId})
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    if course.get("userId") != user.get("id"):
        raise HTTPException(status_code=403, detail="Forbidden")

    chapters: List[Dict[str, Any]] = payload.get("chapters", [])
    if not chapters:
        raise HTTPException(status_code=400, detail="chapters are required")

    for chapter in chapters:
        chapter_doc = {
            "courseId": courseId,
            "chapterId": chapter.get("chapterId"),
            "content": chapter.get("content"),
            "videoId": chapter.get("videoId"),
            "quiz": chapter.get("quiz"),
            "updatedAt": datetime.utcnow().isoformat(),
        }
        if chapter_doc["chapterId"] is None:
            raise HTTPException(status_code=400, detail="chapterId is required")
        await chapters_col.update_one(
            {"courseId": courseId, "chapterId": chapter_doc["chapterId"]},
            {"$set": chapter_doc, "$setOnInsert": {"createdAt": datetime.utcnow().isoformat()}},
            upsert=True,
        )

    return {"success": True}

@router.get("/{courseId}/chapters/{chapterId}")
async def get_chapter(courseId: str, chapterId: int):
    db = await get_db()
    chapters_col = db["course_chapters"]
    chapter = await chapters_col.find_one({"courseId": courseId, "chapterId": chapterId})
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return {"success": True, "data": serialize_id(chapter)}
