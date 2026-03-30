import json
import random
import re
import zipfile
from collections import Counter
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from fastapi import HTTPException, UploadFile

from app.services.ai_client import AIClient

DATASET_PATH = Path(__file__).resolve().parents[3] / "datasets" / "company_questions.json"

COMMON_TECHNOLOGIES = [
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "Next.js",
    "Node.js",
    "FastAPI",
    "Django",
    "Flask",
    "SQL",
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Docker",
    "Kubernetes",
    "AWS",
    "GCP",
    "Azure",
    "Machine Learning",
    "Deep Learning",
    "TensorFlow",
    "PyTorch",
    "Airflow",
    "Spark",
    "Kafka",
    "GraphQL",
    "REST",
    "CI/CD",
]

STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "have",
    "your",
    "about",
    "into",
    "their",
    "they",
    "them",
    "what",
    "when",
    "where",
    "would",
    "could",
    "should",
    "while",
    "were",
    "been",
    "being",
    "also",
    "than",
    "then",
    "there",
    "which",
    "using",
    "used",
    "across",
    "because",
    "between",
    "during",
}


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "question"


def dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-zA-Z][a-zA-Z0-9\+\#\.-]+", text.lower())
    return [token for token in tokens if token not in STOPWORDS and len(token) > 2]


def extract_keywords(text: str, limit: int = 12) -> List[str]:
    counts = Counter(tokenize(text))
    return [token for token, _ in counts.most_common(limit)]


def _extract_resume_text_from_docx(content: bytes) -> str:
    with zipfile.ZipFile(BytesIO(content)) as archive:
        with archive.open("word/document.xml") as document:
            xml = document.read().decode("utf-8", errors="ignore")
    text = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", " ", text)
    return normalize_text(text.replace("\xa0", " "))


def _extract_resume_text_from_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="PDF resume parsing requires the optional pypdf dependency.",
        ) from exc

    reader = PdfReader(BytesIO(content))
    pages = [page.extract_text() or "" for page in reader.pages]
    return normalize_text("\n".join(pages))


async def extract_resume_text(upload: UploadFile | None) -> str:
    if upload is None:
        return ""

    content = await upload.read()
    if not content:
        return ""

    suffix = Path(upload.filename or "").suffix.lower()
    if suffix == ".pdf":
        return _extract_resume_text_from_pdf(content)
    if suffix == ".docx":
        return _extract_resume_text_from_docx(content)

    return content.decode("utf-8", errors="ignore")


def extract_resume_insights(resume_text: str) -> Dict[str, Any]:
    text = normalize_text(resume_text)
    lines = [line.strip(" -\u2022\t") for line in resume_text.splitlines() if line.strip()]
    lower_text = text.lower()

    technologies = []
    for technology in COMMON_TECHNOLOGIES:
        if technology.lower() in lower_text:
            technologies.append(technology)

    skills = []
    projects = []
    for line in lines:
        lowered = line.lower()
        if any(marker in lowered for marker in ("skills", "tech stack", "technologies", "tools")):
            _, _, trailing = line.partition(":")
            chunk = trailing or line
            parts = [part.strip() for part in re.split(r"[,|/]", chunk) if part.strip()]
            skills.extend(parts[:8])
            continue
        if any(marker in lowered for marker in ("project", "built", "developed", "implemented", "designed", "deployed")):
            if len(line) > 28:
                projects.append(line)

    if not skills:
        skills = technologies[:6]

    if not projects:
        long_lines = [line for line in lines if len(line) > 42]
        projects = long_lines[:4]

    sections = [line for line in lines[:6] if len(line) > 20]
    summary = " ".join(sections)[:420]

    return {
        "skills": dedupe(skills)[:8],
        "projects": dedupe(projects)[:4],
        "technologies": dedupe(technologies)[:10],
        "summary": summary,
        "keywords": extract_keywords(text),
    }


@lru_cache(maxsize=1)
def load_question_bank() -> Dict[str, List[Dict[str, Any]]]:
    with DATASET_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_company_catalog() -> Dict[str, Any]:
    bank = load_question_bank()
    roles = sorted(
        {
            item.get("role", "general")
            for items in bank.values()
            for item in items
            if item.get("role")
        }
    )
    return {
        "companies": sorted(bank.keys()),
        "roles": roles,
        "difficulties": ["easy", "medium", "hard"],
    }


def select_company_questions(
    company: str,
    role: str,
    difficulty: str,
    count: int,
) -> List[Dict[str, Any]]:
    bank = load_question_bank()
    company_items = bank.get(company) or []
    if not company_items:
        company_items = [item for items in bank.values() for item in items]

    role_tokens = set(tokenize(role))
    difficulty = (difficulty or "medium").lower()

    def matches_role(item: Dict[str, Any]) -> bool:
        item_role_tokens = set(tokenize(item.get("role", "")))
        return not role_tokens or bool(role_tokens & item_role_tokens)

    primary = [
        item
        for item in company_items
        if item.get("difficulty", "medium").lower() == difficulty and matches_role(item)
    ]
    secondary = [
        item
        for item in company_items
        if item.get("difficulty", "medium").lower() == difficulty and item not in primary
    ]
    tertiary = [item for item in company_items if item not in primary and item not in secondary]

    ordered = primary + secondary + tertiary
    random.Random(f"{company}:{role}:{difficulty}:{count}").shuffle(ordered)
    return ordered[:count]


def build_resume_questions(
    role: str,
    insights: Dict[str, Any],
    count: int,
) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    for project in insights.get("projects", []):
        questions.append(
            {
                "question": f"Walk me through the project where you {project[:80].rstrip('.')}. What tradeoffs did you make?",
                "answerGuide": "Explain scope, architecture, tradeoffs, challenges, and measurable outcome.",
                "category": "resume-project",
                "difficulty": "medium",
                "source": "resume",
            }
        )

    for skill in insights.get("skills", []):
        questions.append(
            {
                "question": f"How have you applied {skill} in a real {role or 'technical'} project, and how did you measure success?",
                "answerGuide": "Give concrete context, the implementation details, and business or engineering impact.",
                "category": "resume-skill",
                "difficulty": "medium",
                "source": "resume",
            }
        )

    for technology in insights.get("technologies", []):
        questions.append(
            {
                "question": f"What design or debugging challenges have you faced while working with {technology}?",
                "answerGuide": "Describe root cause analysis, decisions made, and the final outcome.",
                "category": "technology",
                "difficulty": "medium",
                "source": "resume",
            }
        )

    return questions[:count]


def normalize_questions(questions: List[Dict[str, Any]], count: int | None = None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(questions):
        question = normalize_text(item.get("question"))
        if not question:
            continue
        normalized.append(
            {
                "id": item.get("id") or f"{slugify(question)}-{index + 1}",
                "question": question,
                "answerGuide": normalize_text(item.get("answerGuide") or item.get("answer_focus") or ""),
                "category": item.get("category") or "technical",
                "difficulty": (item.get("difficulty") or "medium").lower(),
                "source": item.get("source") or "generated",
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in normalized:
        key = item["question"].lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped[:count] if count else deduped


async def generate_questions(
    *,
    company: str,
    role: str,
    difficulty: str,
    total_questions: int,
    resume_text: str,
    resume_insights: Dict[str, Any],
    job_description: str,
    ai_client: AIClient,
) -> List[Dict[str, Any]]:
    total_questions = int(clamp(total_questions or 6, 5, 10))
    company_questions = select_company_questions(
        company=company,
        role=role,
        difficulty=difficulty,
        count=max(3, total_questions // 2),
    )
    resume_questions = build_resume_questions(
        role=role,
        insights=resume_insights,
        count=total_questions,
    )

    deterministic = normalize_questions(company_questions + resume_questions, count=total_questions)
    prompt = f"""
You are creating a realistic mock interview plan.
Return ONLY JSON with this schema:
{{
  "questions": [
    {{
      "id": "string",
      "question": "string",
      "answerGuide": "string",
      "category": "technical | behavioral | resume-project | system-design",
      "difficulty": "easy | medium | hard",
      "source": "company-dataset | resume | generated"
    }}
  ]
}}

Role: {role}
Company: {company}
Difficulty: {difficulty}
Job description: {job_description}
Resume summary: {resume_insights.get("summary", "")}
Resume skills: {resume_insights.get("skills", [])}
Resume projects: {resume_insights.get("projects", [])}
Suggested company questions: {company_questions}

Generate exactly {total_questions} questions. Blend company-specific and resume-specific questions.
"""
    llm_result = await ai_client.generate_json(prompt, {"questions": deterministic})
    llm_questions = llm_result.get("questions") if isinstance(llm_result, dict) else llm_result
    normalized = normalize_questions(llm_questions or deterministic, count=total_questions)
    return normalized or deterministic


async def build_resume_upload_response(
    *,
    upload: UploadFile | None,
    company: str,
    role: str,
    difficulty: str,
    total_questions: int,
    job_description: str,
    ai_client: AIClient,
) -> Dict[str, Any]:
    resume_text = await extract_resume_text(upload)
    insights = extract_resume_insights(resume_text)
    questions = await generate_questions(
        company=company,
        role=role,
        difficulty=difficulty,
        total_questions=total_questions,
        resume_text=resume_text,
        resume_insights=insights,
        job_description=job_description,
        ai_client=ai_client,
    )
    company_samples = select_company_questions(company, role, difficulty, count=4)
    return {
        "resumeText": resume_text,
        "resumeInsights": insights,
        "suggestedQuestions": questions,
        "companyQuestionSamples": normalize_questions(company_samples),
    }
