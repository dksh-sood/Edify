from datetime import datetime
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.security import get_optional_user
from app.db.mongo import get_db
from app.services import (
    AIClient,
    build_resume_upload_response,
    generate_final_report,
    generate_questions,
    get_company_catalog,
    normalize_questions,
    save_uploaded_file,
    score_turn_submission,
)
from app.utils.serialize import serialize_id, serialize_list

router = APIRouter()
ai_client = AIClient()


def _resolve_identity(user: Dict[str, Any] | None, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    payload = payload or {}
    if user:
        return {
            "id": user.get("id"),
            "email": user.get("email"),
        }
    return {
        "id": payload.get("createdBy") or payload.get("email") or "anonymous",
        "email": payload.get("createdBy") or payload.get("email"),
    }


async def _get_ai_session_or_404(session_id: str, user: Dict[str, Any] | None) -> Dict[str, Any]:
    db = await get_db()
    sessions = db["ai_mock_interview_sessions"]
    user_id = user.get("id") if user else "anonymous"
    doc = await sessions.find_one({"sessionId": session_id, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="AI interview session not found")
    return doc


@router.get("/ai/companies")
async def list_ai_companies():
    return {"success": True, "data": get_company_catalog()}


@router.post("/ai/resume/upload")
async def upload_resume(
    file: UploadFile | None = File(default=None),
    company: str = Form(default="Amazon"),
    role: str = Form(default="Software Engineer"),
    difficulty: str = Form(default="medium"),
    totalQuestions: int = Form(default=6),
    jobDescription: str = Form(default=""),
):
    data = await build_resume_upload_response(
        upload=file,
        company=company,
        role=role,
        difficulty=difficulty,
        total_questions=totalQuestions,
        job_description=jobDescription,
        ai_client=ai_client,
    )
    return {"success": True, "data": data}


@router.post("/ai/sessions")
async def create_ai_session(payload: Dict[str, Any], user=Depends(get_optional_user)):
    identity = _resolve_identity(user, payload)
    db = await get_db()
    sessions = db["ai_mock_interview_sessions"]

    session_id = payload.get("sessionId") or uuid4().hex
    role = payload.get("role") or payload.get("jobPosition") or "Software Engineer"
    company = payload.get("company") or "Amazon"
    difficulty = (payload.get("difficulty") or "medium").lower()
    total_questions = int(payload.get("totalQuestions") or 6)
    job_description = payload.get("jobDescription") or payload.get("jobDesc") or ""
    resume_text = payload.get("resumeText") or ""
    resume_insights = payload.get("resumeInsights") or {}

    questions = normalize_questions(payload.get("questions") or [], count=total_questions)
    if not questions:
        questions = await generate_questions(
            company=company,
            role=role,
            difficulty=difficulty,
            total_questions=total_questions,
            resume_text=resume_text,
            resume_insights=resume_insights,
            job_description=job_description,
            ai_client=ai_client,
        )

    now = datetime.utcnow().isoformat()
    doc = {
        "sessionId": session_id,
        "role": role,
        "company": company,
        "difficulty": difficulty,
        "experienceLevel": payload.get("experienceLevel") or payload.get("jobExperience") or "",
        "jobDescription": job_description,
        "resumeText": resume_text,
        "resumeInsights": resume_insights,
        "questions": questions,
        "questionCount": len(questions),
        "avatarConfig": {
            "name": payload.get("avatarName") or "Ava",
            "voice": payload.get("voice") or "en-US",
        },
        "status": "ready",
        "createdBy": identity.get("email"),
        "userId": identity.get("id"),
        "createdAt": payload.get("createdAt") or now,
        "updatedAt": now,
    }

    await sessions.insert_one(doc)
    return {"success": True, "data": serialize_id(doc)}


@router.get("/ai/sessions")
async def list_ai_sessions(user=Depends(get_optional_user)):
    db = await get_db()
    sessions = db["ai_mock_interview_sessions"]
    user_id = user.get("id") if user else "anonymous"
    items = await sessions.find({"userId": user_id}).sort("createdAt", -1).to_list(100)
    return {"success": True, "data": serialize_list(items)}


@router.get("/ai/sessions/{sessionId}")
async def get_ai_session(sessionId: str, user=Depends(get_optional_user)):
    db = await get_db()
    turns = db["ai_mock_interview_turns"]
    session = await _get_ai_session_or_404(sessionId, user)
    user_id = user.get("id") if user else "anonymous"
    turn_items = await turns.find({"sessionId": sessionId, "userId": user_id}).sort("createdAt", 1).to_list(200)
    return {
        "success": True,
        "data": {
            "session": serialize_id(session),
            "turns": serialize_list(turn_items),
        },
    }


@router.post("/ai/upload-video")
async def upload_ai_video(
    sessionId: str = Form(...),
    file: UploadFile = File(...),
    category: str = Form(default="recordings"),
):
    metadata = await save_uploaded_file(file, session_id=sessionId, category=category)
    return {"success": True, "data": metadata}


@router.post("/ai/sessions/{sessionId}/turns")
async def create_ai_turn(sessionId: str, payload: Dict[str, Any], user=Depends(get_optional_user)):
    db = await get_db()
    sessions = db["ai_mock_interview_sessions"]
    turns = db["ai_mock_interview_turns"]
    session = await _get_ai_session_or_404(sessionId, user)

    identity = _resolve_identity(user, payload)
    turn_doc = await score_turn_submission(session=session, payload=payload, ai_client=ai_client)
    now = datetime.utcnow().isoformat()
    turn_doc.update(
        {
            "sessionId": sessionId,
            "userId": identity.get("id"),
            "userEmail": identity.get("email"),
            "createdAt": payload.get("createdAt") or now,
            "updatedAt": now,
        }
    )

    existing = await turns.find_one(
        {
            "sessionId": sessionId,
            "questionId": turn_doc["questionId"],
            "userId": identity.get("id"),
        }
    )
    if existing:
        turn_doc["_id"] = existing["_id"]
        await turns.replace_one({"_id": existing["_id"]}, turn_doc)
    else:
        insert_result = await turns.insert_one(turn_doc)
        turn_doc["_id"] = insert_result.inserted_id

    answered_count = await turns.count_documents({"sessionId": sessionId, "userId": identity.get("id")})
    next_status = "completed" if answered_count >= int(session.get("questionCount") or 0) else "in_progress"
    await sessions.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "status": next_status,
                "updatedAt": now,
                "answeredCount": answered_count,
            }
        },
    )

    return {"success": True, "data": serialize_id(turn_doc)}


@router.get("/ai/sessions/{sessionId}/report")
async def get_ai_report(sessionId: str, user=Depends(get_optional_user)):
    db = await get_db()
    sessions = db["ai_mock_interview_sessions"]
    turns = db["ai_mock_interview_turns"]
    session = await _get_ai_session_or_404(sessionId, user)
    user_id = user.get("id") if user else "anonymous"
    turn_items = await turns.find({"sessionId": sessionId, "userId": user_id}).sort("createdAt", 1).to_list(200)

    report = await generate_final_report(session=session, turns=turn_items, ai_client=ai_client)
    now = datetime.utcnow().isoformat()
    await sessions.update_one(
        {"_id": session["_id"]},
        {
            "$set": {
                "status": "completed",
                "updatedAt": now,
                "completedAt": now,
                "reportSummary": {
                    "overall_score": report["overall_score"],
                    "summary": report["summary"],
                },
            }
        },
    )
    return {"success": True, "data": report}


@router.post("")
async def create_mock_interview(payload: Dict[str, Any], user=Depends(get_optional_user)):
    db = await get_db()
    interviews = db["mock_interviews"]

    mock_id = payload.get("mockId")
    if not mock_id:
        raise HTTPException(status_code=400, detail="mockId is required")

    identity = _resolve_identity(user, payload)
    doc = {
        "mockId": mock_id,
        "jsonMockResp": payload.get("jsonMockResp"),
        "jobPosition": payload.get("jobPosition"),
        "jobDesc": payload.get("jobDesc"),
        "jobExperience": payload.get("jobExperience"),
        "createdBy": identity.get("email"),
        "userId": identity.get("id"),
        "createdAt": payload.get("createdAt") or datetime.utcnow().isoformat(),
    }

    await interviews.insert_one(doc)
    return {"success": True, "data": serialize_id(doc)}


@router.get("")
async def list_mock_interviews(user=Depends(get_optional_user)):
    db = await get_db()
    interviews = db["mock_interviews"]
    user_id = user.get("id") if user else "anonymous"
    items = await interviews.find({"userId": user_id}).sort("createdAt", -1).to_list(200)
    return {"success": True, "data": serialize_list(items)}


@router.get("/{mockId}")
async def get_mock_interview(mockId: str, user=Depends(get_optional_user)):
    db = await get_db()
    interviews = db["mock_interviews"]
    user_id = user.get("id") if user else "anonymous"
    doc = await interviews.find_one({"mockId": mockId, "userId": user_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Interview not found")
    return {"success": True, "data": serialize_id(doc)}


@router.post("/{mockId}/answers")
async def create_answer(mockId: str, payload: Dict[str, Any], user=Depends(get_optional_user)):
    db = await get_db()
    answers = db["user_answers"]
    identity = _resolve_identity(user, payload)

    doc = {
        "mockIdRef": mockId,
        "question": payload.get("question"),
        "correctAns": payload.get("correctAns"),
        "userAns": payload.get("userAns"),
        "feedback": payload.get("feedback"),
        "rating": payload.get("rating"),
        "userEmail": identity.get("email"),
        "userId": identity.get("id"),
        "createdAt": payload.get("createdAt") or datetime.utcnow().isoformat(),
    }

    await answers.insert_one(doc)
    return {"success": True, "data": serialize_id(doc)}


@router.get("/{mockId}/answers")
async def list_answers(mockId: str, user=Depends(get_optional_user)):
    db = await get_db()
    answers = db["user_answers"]
    user_id = user.get("id") if user else "anonymous"
    items = await answers.find({"mockIdRef": mockId, "userId": user_id}).sort("createdAt", 1).to_list(500)
    return {"success": True, "data": serialize_list(items)}
