from collections import Counter
from typing import Any, Dict, List

from fastapi import HTTPException

from app.services.ai_client import AIClient
from app.services.resume_intelligence import clamp, dedupe, extract_keywords, normalize_text, tokenize


def _confidence_signal(voice_metrics: Dict[str, Any], speech_rate: float) -> float:
    speaking_score = 1 - min(abs(speech_rate - 145) / 145, 1)
    pause_score = 1 - min(float(voice_metrics.get("pauseFrequency", 0) or 0) / 12, 1)
    volume_score = min(float(voice_metrics.get("averageVolume", 0.4) or 0.4) / 0.18, 1)
    silence_penalty = 1 - min(float(voice_metrics.get("silenceRatio", 0.1) or 0.1), 0.7)
    return clamp((speaking_score + pause_score + volume_score + silence_penalty) / 4, 0, 1)


def _derive_emotion(confidence_ratio: float, eye_contact_ratio: float, cheating_score: float) -> str:
    if confidence_ratio >= 0.74 and eye_contact_ratio >= 0.62:
        return "confident"
    if cheating_score >= 5:
        return "stressed"
    if confidence_ratio < 0.45:
        return "nervous"
    return "neutral"


def _fallback_turn_evaluation(
    *,
    question: str,
    answer_guide: str,
    transcript: str,
    voice_metrics: Dict[str, Any],
    eye_contact_ratio: float,
    posture_score: float,
    cheating_score: float,
    cheating_reasons: List[str],
) -> Dict[str, Any]:
    transcript_words = len(tokenize(transcript))
    expected_keywords = set(extract_keywords(f"{question} {answer_guide}", limit=10))
    actual_keywords = set(extract_keywords(transcript, limit=20))
    coverage_ratio = len(expected_keywords & actual_keywords) / max(len(expected_keywords), 1)

    speech_rate = float(voice_metrics.get("speechRateWpm", 0) or 0)
    confidence_ratio = _confidence_signal(voice_metrics, speech_rate or 140)

    technical_score = round(
        clamp(4.2 + (coverage_ratio * 4.2) + min(transcript_words / 80, 2), 1, 10)
    )
    communication_score = round(
        clamp(
            4.8
            + min(transcript_words / 110, 1.5)
            + (1 - min(abs((speech_rate or 145) - 145) / 145, 1)) * 2.2,
            1,
            10,
        )
    )
    confidence_score = round(
        clamp((eye_contact_ratio * 4) + (posture_score * 3) + (confidence_ratio * 3), 1, 10)
    )
    overall_score = round(
        clamp((technical_score * 0.45) + (communication_score * 0.3) + (confidence_score * 0.25), 1, 10),
        1,
    )

    strengths: List[str] = []
    weaknesses: List[str] = []
    suggestions: List[str] = []

    if coverage_ratio >= 0.35:
        strengths.append("Covered several of the core concepts expected for the question.")
    else:
        weaknesses.append("The answer missed some of the key technical points expected by the prompt.")
        suggestions.append("Structure the answer around the problem, implementation details, and outcome.")

    if 115 <= (speech_rate or 145) <= 175:
        strengths.append("Maintained a reasonable speaking pace.")
    else:
        weaknesses.append("Speaking pace drifted outside a comfortable interview range.")
        suggestions.append("Aim for a steadier pace around 120-170 words per minute.")

    if eye_contact_ratio >= 0.62:
        strengths.append("Maintained good eye contact with the camera.")
    else:
        weaknesses.append("Eye contact dropped too often during the answer.")
        suggestions.append("Keep the camera near your notes and return to it after thinking pauses.")

    if posture_score < 0.55:
        weaknesses.append("Posture and on-camera stability were inconsistent.")
        suggestions.append("Sit upright and reduce unnecessary movement between key points.")

    if cheating_reasons:
        weaknesses.append("Suspicious interview behavior was detected.")
        suggestions.append("Avoid switching tabs or reading from an off-screen prompt during answers.")

    if transcript_words < 35:
        weaknesses.append("The answer was short and likely underdeveloped.")
        suggestions.append("Add one concrete example and one measurable result to each response.")

    emotion = _derive_emotion(confidence_ratio, eye_contact_ratio, cheating_score)
    summary = (
        "The answer showed solid structure and communication."
        if overall_score >= 7
        else "The answer was understandable but would benefit from deeper technical detail and steadier delivery."
    )

    return {
        "technical_score": technical_score,
        "communication_score": communication_score,
        "confidence_score": confidence_score,
        "overall_score": overall_score,
        "strengths": dedupe(strengths)[:4],
        "weaknesses": dedupe(weaknesses)[:4],
        "suggestions": dedupe(suggestions)[:5],
        "summary": summary,
        "emotion": emotion,
    }


async def score_turn_submission(
    *,
    session: Dict[str, Any],
    payload: Dict[str, Any],
    ai_client: AIClient,
) -> Dict[str, Any]:
    question = normalize_text(payload.get("question"))
    transcript = normalize_text(payload.get("transcript"))
    if not question or not transcript:
        raise HTTPException(status_code=400, detail="question and transcript are required")

    question_id = payload.get("questionId") or f"question-{len(session.get('questions', [])) + 1}"
    answer_guide = normalize_text(payload.get("answerGuide"))
    voice_metrics = payload.get("voiceMetrics") or {}
    video_metrics = payload.get("videoMetrics") or {}
    behavior_signals = payload.get("behaviorSignals") or {}

    duration = float(payload.get("answerDurationSec") or voice_metrics.get("durationSec") or 0)
    transcript_words = len(tokenize(transcript))
    if duration and not voice_metrics.get("speechRateWpm"):
        voice_metrics["speechRateWpm"] = round((transcript_words / duration) * 60, 2)

    eye_contact_ratio = float(
        video_metrics.get("eyeContactRatio")
        or video_metrics.get("centeredFaceRatio")
        or video_metrics.get("facePresentRatio")
        or 0.58
    )
    posture_score = float(
        video_metrics.get("postureScore")
        or video_metrics.get("stableFrameRatio")
        or 0.6
    )

    tab_switches = int(behavior_signals.get("tabSwitchCount") or behavior_signals.get("pageHiddenCount") or 0)
    focus_losses = int(behavior_signals.get("windowBlurCount") or 0)
    multiple_faces = int(
        behavior_signals.get("multipleFaceEvents")
        or video_metrics.get("multipleFaceEvents")
        or video_metrics.get("multipleFacesDetected")
        or 0
    )
    distraction_events = int(
        video_metrics.get("distractionEvents")
        or behavior_signals.get("lookAwayEvents")
        or 0
    )

    cheating_reasons: List[str] = []
    cheating_score = 0
    if eye_contact_ratio < 0.42:
        cheating_score += 2
        cheating_reasons.append("frequent gaze away from camera")
    if tab_switches:
        cheating_score += tab_switches * 2
        cheating_reasons.append("tab switched during answer")
    if focus_losses:
        cheating_score += focus_losses
        cheating_reasons.append("browser focus changed during answer")
    if multiple_faces:
        cheating_score += multiple_faces * 3
        cheating_reasons.append("multiple faces detected in frame")
    if distraction_events >= 3:
        cheating_score += 2
        cheating_reasons.append("repeated distraction or look-away events")

    if cheating_score >= 6:
        cheating_risk = "high"
    elif cheating_score >= 3:
        cheating_risk = "medium"
    else:
        cheating_risk = "low"

    fallback = _fallback_turn_evaluation(
        question=question,
        answer_guide=answer_guide,
        transcript=transcript,
        voice_metrics=voice_metrics,
        eye_contact_ratio=eye_contact_ratio,
        posture_score=posture_score,
        cheating_score=cheating_score,
        cheating_reasons=cheating_reasons,
    )

    prompt = f"""
You are scoring a mock interview answer. Return ONLY JSON.
Schema:
{{
  "technical_score": number,
  "communication_score": number,
  "confidence_score": number,
  "overall_score": number,
  "strengths": ["string"],
  "weaknesses": ["string"],
  "suggestions": ["string"],
  "summary": "string",
  "emotion": "confident | nervous | neutral | stressed | happy"
}}

Question: {question}
Expected answer focus: {answer_guide}
Transcript: {transcript}
Voice metrics: {voice_metrics}
Video metrics: {video_metrics}
Behavior signals: {behavior_signals}
Cheating risk: {cheating_risk}
"""
    llm_scoring = await ai_client.generate_json(prompt, fallback)
    evaluation = llm_scoring if isinstance(llm_scoring, dict) else fallback
    evaluation = {
        "technical_score": int(round(clamp(float(evaluation.get("technical_score", fallback["technical_score"])), 1, 10))),
        "communication_score": int(round(clamp(float(evaluation.get("communication_score", fallback["communication_score"])), 1, 10))),
        "confidence_score": int(round(clamp(float(evaluation.get("confidence_score", fallback["confidence_score"])), 1, 10))),
        "overall_score": round(clamp(float(evaluation.get("overall_score", fallback["overall_score"])), 1, 10), 1),
        "strengths": dedupe(list(evaluation.get("strengths") or fallback["strengths"]))[:4],
        "weaknesses": dedupe(list(evaluation.get("weaknesses") or fallback["weaknesses"]))[:4],
        "suggestions": dedupe(list(evaluation.get("suggestions") or fallback["suggestions"]))[:5],
        "summary": normalize_text(evaluation.get("summary") or fallback["summary"]),
        "emotion": (evaluation.get("emotion") or fallback["emotion"]).lower(),
    }

    return {
        "questionId": question_id,
        "question": question,
        "answerGuide": answer_guide,
        "transcript": transcript,
        "voiceMetrics": {
            "durationSec": duration,
            "speechRateWpm": round(float(voice_metrics.get("speechRateWpm") or 0), 2),
            "averagePitchHz": round(float(voice_metrics.get("averagePitchHz") or 0), 2),
            "averageVolume": round(float(voice_metrics.get("averageVolume") or 0), 4),
            "pauseFrequency": round(float(voice_metrics.get("pauseFrequency") or 0), 2),
            "silenceRatio": round(float(voice_metrics.get("silenceRatio") or 0), 4),
            "confidenceIndicator": round(_confidence_signal(voice_metrics, float(voice_metrics.get("speechRateWpm") or 145)), 3),
        },
        "videoMetrics": {
            "eyeContactRatio": round(eye_contact_ratio, 3),
            "postureScore": round(posture_score, 3),
            "distractionEvents": distraction_events,
            "multipleFaceEvents": multiple_faces,
            "facePresentRatio": round(float(video_metrics.get("facePresentRatio") or 0.7), 3),
        },
        "emotion": {
            "dominant": evaluation["emotion"],
        },
        "cheatingDetection": {
            "risk": cheating_risk,
            "reasons": dedupe(cheating_reasons),
            "score": cheating_score,
            "tabSwitchCount": tab_switches,
            "focusLossCount": focus_losses,
        },
        "evaluation": evaluation,
        "rating": evaluation["overall_score"],
        "feedback": evaluation["summary"],
        "userAns": transcript,
        "correctAns": answer_guide,
        "media": payload.get("media") or {},
    }


def _aggregate_top_strings(items: List[str], limit: int) -> List[str]:
    counts = Counter(item for item in items if item)
    return [item for item, _ in counts.most_common(limit)]


async def generate_final_report(
    *,
    session: Dict[str, Any],
    turns: List[Dict[str, Any]],
    ai_client: AIClient,
) -> Dict[str, Any]:
    if not turns:
        raise HTTPException(status_code=404, detail="No interview answers found for this session")

    technical = round(sum(float(turn["evaluation"]["technical_score"]) for turn in turns) / len(turns), 1)
    communication = round(sum(float(turn["evaluation"]["communication_score"]) for turn in turns) / len(turns), 1)
    confidence = round(sum(float(turn["evaluation"]["confidence_score"]) for turn in turns) / len(turns), 1)
    overall = round(sum(float(turn["evaluation"]["overall_score"]) for turn in turns) / len(turns), 1)

    emotion_timeline = [
        {
            "questionId": turn.get("questionId"),
            "question": turn.get("question"),
            "emotion": turn.get("emotion", {}).get("dominant", "neutral"),
            "score": turn.get("evaluation", {}).get("overall_score", 0),
        }
        for turn in turns
    ]
    dominant_emotion = Counter(item["emotion"] for item in emotion_timeline).most_common(1)[0][0]

    eye_contact_graph = [
        {
            "questionId": turn.get("questionId"),
            "value": round(float(turn.get("videoMetrics", {}).get("eyeContactRatio") or 0), 3),
        }
        for turn in turns
    ]
    speech_rate_graph = [
        {
            "questionId": turn.get("questionId"),
            "value": round(float(turn.get("voiceMetrics", {}).get("speechRateWpm") or 0), 2),
        }
        for turn in turns
    ]
    posture_graph = [
        {
            "questionId": turn.get("questionId"),
            "value": round(float(turn.get("videoMetrics", {}).get("postureScore") or 0), 3),
        }
        for turn in turns
    ]

    cheating_levels = {"low": 1, "medium": 2, "high": 3}
    cheating_entry = max(
        (turn.get("cheatingDetection", {}) for turn in turns),
        key=lambda item: cheating_levels.get(item.get("risk", "low"), 1),
    )

    strengths = _aggregate_top_strings(
        [strength for turn in turns for strength in turn.get("evaluation", {}).get("strengths", [])],
        5,
    )
    weaknesses = _aggregate_top_strings(
        [weakness for turn in turns for weakness in turn.get("evaluation", {}).get("weaknesses", [])],
        5,
    )
    suggestions = _aggregate_top_strings(
        [suggestion for turn in turns for suggestion in turn.get("evaluation", {}).get("suggestions", [])],
        6,
    )

    fallback_summary = (
        f"The candidate averaged {overall}/10 overall, with strongest performance in "
        f"{'technical depth' if technical >= communication else 'communication clarity'}. "
        f"Primary improvement areas were eye contact, stability, and answer specificity."
    )
    prompt = f"""
You are summarizing a mock interview report. Return plain text only in 3 short sentences.
Role: {session.get('role')}
Company: {session.get('company')}
Overall: {overall}
Technical: {technical}
Communication: {communication}
Confidence: {confidence}
Dominant emotion: {dominant_emotion}
Top strengths: {strengths}
Top weaknesses: {weaknesses}
Top suggestions: {suggestions}
"""
    summary = await ai_client.generate_text(prompt, fallback_summary)

    return {
        "sessionId": session.get("sessionId"),
        "overall_score": overall,
        "technical_score": technical,
        "communication_score": communication,
        "confidence_score": confidence,
        "confidence_meter": round(confidence * 10, 1),
        "emotion_analysis": {
            "dominant_emotion": dominant_emotion,
            "timeline": emotion_timeline,
        },
        "eye_contact": {
            "average_ratio": round(sum(item["value"] for item in eye_contact_graph) / len(eye_contact_graph), 3),
            "graph": eye_contact_graph,
            "distraction_events": sum(int(turn.get("videoMetrics", {}).get("distractionEvents") or 0) for turn in turns),
        },
        "posture": {
            "average_score": round(sum(item["value"] for item in posture_graph) / len(posture_graph), 3),
            "graph": posture_graph,
        },
        "voice_analysis": {
            "average_speech_rate": round(sum(item["value"] for item in speech_rate_graph) / len(speech_rate_graph), 2),
            "average_pitch": round(
                sum(float(turn.get("voiceMetrics", {}).get("averagePitchHz") or 0) for turn in turns) / len(turns),
                2,
            ),
            "average_pause_frequency": round(
                sum(float(turn.get("voiceMetrics", {}).get("pauseFrequency") or 0) for turn in turns) / len(turns),
                2,
            ),
            "graph": speech_rate_graph,
        },
        "cheating_risk": {
            "risk": cheating_entry.get("risk", "low"),
            "reasons": _aggregate_top_strings(
                [reason for turn in turns for reason in turn.get("cheatingDetection", {}).get("reasons", [])],
                4,
            ),
        },
        "strengths": strengths,
        "weaknesses": weaknesses,
        "suggestions": suggestions,
        "summary": summary,
        "question_breakdown": [
            {
                "questionId": turn.get("questionId"),
                "question": turn.get("question"),
                "transcript": turn.get("transcript"),
                "technical_score": turn.get("evaluation", {}).get("technical_score"),
                "communication_score": turn.get("evaluation", {}).get("communication_score"),
                "confidence_score": turn.get("evaluation", {}).get("confidence_score"),
                "overall_score": turn.get("evaluation", {}).get("overall_score"),
                "emotion": turn.get("emotion", {}).get("dominant"),
                "eye_contact_ratio": turn.get("videoMetrics", {}).get("eyeContactRatio"),
                "speech_rate_wpm": turn.get("voiceMetrics", {}).get("speechRateWpm"),
                "feedback": turn.get("evaluation", {}).get("summary"),
                "suggestions": turn.get("evaluation", {}).get("suggestions"),
            }
            for turn in turns
        ],
    }
