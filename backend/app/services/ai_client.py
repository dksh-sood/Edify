import asyncio
import json
from typing import Any

import google.generativeai as genai

from app.core.config import settings


def _extract_json_block(text: str) -> str | None:
    first_obj = text.find("{")
    first_arr = text.find("[")
    starts = [index for index in (first_obj, first_arr) if index != -1]
    if not starts:
        return None
    start = min(starts)
    end_obj = text.rfind("}")
    end_arr = text.rfind("]")
    end = max(end_obj, end_arr)
    if end <= start:
        return None
    return text[start : end + 1]


class AIClient:
    def __init__(self) -> None:
        self.enabled = bool(settings.google_ai_api_key)
        self.model = None
        if self.enabled:
            genai.configure(api_key=settings.google_ai_api_key)
            self.model = genai.GenerativeModel(
                settings.google_ai_model or "gemini-2.5-flash"
            )

    async def generate_json(self, prompt: str, fallback: Any) -> Any:
        if not self.enabled or self.model is None:
            return fallback

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = getattr(response, "text", "") or ""
            if not text.strip():
                return fallback

            cleaned = text.replace("```json", "").replace("```", "").strip()
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                extracted = _extract_json_block(cleaned)
                if not extracted:
                    return fallback
                return json.loads(extracted)
        except Exception:
            return fallback

    async def generate_text(self, prompt: str, fallback: str) -> str:
        if not self.enabled or self.model is None:
            return fallback

        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            text = getattr(response, "text", "") or ""
            return text.strip() or fallback
        except Exception:
            return fallback
