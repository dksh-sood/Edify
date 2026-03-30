from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import base64
import json
import google.generativeai as genai

from app.core.config import settings

router = APIRouter()

@router.post("")
async def calculate(payload: Dict[str, Any]):
    if not settings.google_ai_api_key:
        raise HTTPException(status_code=500, detail="GOOGLE_AI_API_KEY not configured")

    image = payload.get("image")
    dict_of_vars = payload.get("dict_of_vars")
    if not image or not dict_of_vars:
        raise HTTPException(status_code=400, detail="Missing required fields")

    try:
        image_data = base64.b64decode(image.split(",")[1])
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image format")

    genai.configure(api_key=settings.google_ai_api_key)
    model = genai.GenerativeModel("gemini-1.5-pro")

    prompt = "Solve the math problems in the image. Return a JSON array of answers with fields: expression, result, assign (bool)."

    response = model.generate_content([prompt, {"mime_type": "image/jpeg", "data": image_data}])
    text = response.text or ""

    try:
        answers = json.loads(text)
        if not isinstance(answers, list):
            raise ValueError("Response is not an array")
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid response from AI model")

    for answer in answers:
        answer["assign"] = bool(answer.get("assign"))

    return {"message": "Image processed", "type": "success", "data": answers}
