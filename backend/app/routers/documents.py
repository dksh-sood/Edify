from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from typing import Any, Dict, List

from app.core.security import get_current_user
from app.db.mongo import get_db
from app.utils.serialize import serialize_id, serialize_list, ensure_item_ids

router = APIRouter()

@router.post("")
async def create_document(payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    documents = db["documents"]

    document_id = payload.get("documentId")
    if not document_id:
        raise HTTPException(status_code=400, detail="documentId is required")

    doc = {
        "documentId": document_id,
        "userId": user.get("id"),
        "title": payload.get("title"),
        "summary": payload.get("summary"),
        "themeColor": payload.get("themeColor", "#7c3aed"),
        "thumbnail": payload.get("thumbnail"),
        "currentPosition": payload.get("currentPosition", 1),
        "status": payload.get("status", "private"),
        "authorName": payload.get("authorName") or f"{user.get('given_name', '')} {user.get('family_name', '')}".strip(),
        "authorEmail": payload.get("authorEmail") or user.get("email"),
        "personalInfo": payload.get("personalInfo"),
        "experiences": ensure_item_ids(payload.get("experience", []) or payload.get("experiences", [])),
        "educations": ensure_item_ids(payload.get("education", []) or payload.get("educations", [])),
        "skills": ensure_item_ids(payload.get("skills", [])),
        "createdAt": datetime.utcnow().isoformat(),
        "updatedAt": datetime.utcnow().isoformat(),
    }

    await documents.insert_one(doc)
    return {"success": "ok", "data": doc}

@router.patch("/update/{documentId}")
async def update_document(documentId: str, payload: Dict[str, Any], user=Depends(get_current_user)):
    db = await get_db()
    documents = db["documents"]

    doc = await documents.find_one({"documentId": documentId, "userId": user.get("id")})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    update_fields: Dict[str, Any] = {}
    for field in ["title", "status", "summary", "thumbnail", "themeColor", "currentPosition"]:
        if field in payload and payload[field] is not None:
            update_fields[field] = payload[field]

    if "personalInfo" in payload and payload["personalInfo"]:
        update_fields["personalInfo"] = payload["personalInfo"]

    if "experience" in payload and isinstance(payload["experience"], list):
        update_fields["experiences"] = ensure_item_ids(payload["experience"])

    if "education" in payload and isinstance(payload["education"], list):
        update_fields["educations"] = ensure_item_ids(payload["education"])

    if "skills" in payload and isinstance(payload["skills"], list):
        update_fields["skills"] = ensure_item_ids(payload["skills"])

    update_fields["updatedAt"] = datetime.utcnow().isoformat()

    await documents.update_one({"documentId": documentId, "userId": user.get("id")}, {"$set": update_fields})
    return {"success": "ok", "message": "Updated successfully"}

@router.patch("/restore")
async def restore_document(payload: Dict[str, Any], user=Depends(get_current_user)):
    documentId = payload.get("documentId")
    status = payload.get("status")
    if not documentId:
        raise HTTPException(status_code=400, detail="documentId is required")
    if status != "archived":
        raise HTTPException(status_code=400, detail="Status must be archived before restore")

    db = await get_db()
    documents = db["documents"]

    doc = await documents.find_one({"documentId": documentId, "userId": user.get("id"), "status": "archived"})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    await documents.update_one({"documentId": documentId}, {"$set": {"status": "private", "updatedAt": datetime.utcnow().isoformat()}})
    updated = await documents.find_one({"documentId": documentId})
    return {"success": "ok", "message": "Updated successfully", "data": serialize_id(updated)}

@router.get("")
async def list_documents(user=Depends(get_current_user)):
    db = await get_db()
    documents = db["documents"]
    items = await documents.find({"userId": user.get("id"), "status": {"$ne": "archived"}}).sort("updatedAt", -1).to_list(200)
    return {"success": True, "data": serialize_list(items)}

@router.get("/trash")
async def list_trash(user=Depends(get_current_user)):
    db = await get_db()
    documents = db["documents"]
    items = await documents.find({"userId": user.get("id"), "status": "archived"}).to_list(200)
    return {"success": True, "data": serialize_list(items)}

@router.get("/{documentId}")
async def get_document(documentId: str, user=Depends(get_current_user)):
    db = await get_db()
    documents = db["documents"]
    doc = await documents.find_one({"documentId": documentId, "userId": user.get("id")})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "data": serialize_id(doc)}

@router.get("/public/{documentId}")
async def get_public_document(documentId: str):
    db = await get_db()
    documents = db["documents"]
    doc = await documents.find_one({"documentId": documentId, "status": "public"})
    if not doc:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"success": True, "data": serialize_id(doc)}
