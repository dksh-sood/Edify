from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from groq import Groq

from app.core.config import settings

router = APIRouter()

@router.post("")
async def chat(payload: Dict[str, Any]):
    if not settings.groq_api_key:
        raise HTTPException(status_code=500, detail="GROQ_API_KEY not configured")

    input_text = payload.get("input")
    course = payload.get("course")
    if not input_text or not course:
        raise HTTPException(status_code=400, detail="input and course are required")

    course_output = course.get("courseOutput", {})
    category = course_output.get("category", "")
    chapters = course_output.get("chapters", [])

    description = f"Course: {course.get('courseName')} ({category})\n\n"
    for idx, chapter in enumerate(chapters):
        description += f"{idx + 1}. {chapter.get('chapter_name')}\n"
        description += f"   Description: {chapter.get('description')}\n"
        description += f"   Duration: {chapter.get('duration')}\n\n"

    client = Groq(api_key=settings.groq_api_key)
    completion = client.chat.completions.create(
        messages=[
            {"role": "system", "content": f"You are a helpful assistant for a course. Use the following course description to answer questions:\n\n{description}"},
            {"role": "user", "content": input_text},
        ],
        model="Llama3-8b-8192",
        temperature=0.5,
        max_tokens=1000,
        top_p=1,
        stream=False,
    )

    result = completion.choices[0].message.content if completion.choices else ""
    return {"result": result}
