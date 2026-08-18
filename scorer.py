"""Gemini LLM-based job relevance scorer.

Sends your resume + each job description to Gemini and receives
a structured relevance score (1-10) with reasoning.
"""

import json
import logging
import time

from google import genai
from google.genai import types

from config import GEMINI_MODEL, RESUME_TEXT_PATH

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> genai.Client:
    """Lazy-initialize the Gemini client (avoids import-time crashes)."""
    global _client
    if _client is None:
        from config import GEMINI_API_KEY
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client

SCORING_PROMPT = """
You are a job-fit evaluator for a software engineering candidate.

CANDIDATE RESUME:
{resume}

JOB TITLE: {title}
COMPANY: {company}
LOCATION: {location}

JOB DESCRIPTION:
{description}

Evaluate how well this candidate fits this job. Consider:
1. Technical skill overlap (how many required skills does the candidate have?)
2. Experience level match (candidate has ~1 year of experience as an apprentice)
3. Domain relevance (backend, data engineering, AI/LLM, full-stack)
4. Growth potential (can the candidate realistically grow into this role?)
5. Location fit (candidate is based in India)

Respond with ONLY a JSON object (no markdown, no code fences):
{{
    "score": <1-10 integer>,
    "reasoning": "<2-3 sentence explanation>",
    "matching_skills": ["<skill1>", "<skill2>", ...],
    "missing_skills": ["<skill1>", "<skill2>", ...],
    "seniority_fit": "<too_junior|good|stretch|too_senior>"
}}

Scoring guide:
- 9-10: Near-perfect match, candidate should apply immediately
- 7-8: Strong match, most skills align, worth applying
- 5-6: Decent match, some skill gaps but learnable
- 3-4: Weak match, significant gaps
- 1-2: Poor match, wrong domain or way too senior
"""

_resume_text: str | None = None


def _get_resume() -> str:
    """Load and cache the resume text."""
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_TEXT_PATH.read_text(encoding="utf-8")
    return _resume_text


def score_job(title: str, company: str, location: str, description: str) -> dict:
    """Score a single job against the candidate's resume using Gemini.

    Args:
        title: Job title
        company: Company name
        location: Job location
        description: Full job description text

    Returns:
        Dict with keys: score, reasoning, matching_skills, missing_skills, seniority_fit.
        On failure, returns a dict with score=0.
    """
    if not description or not description.strip():
        return {
            "score": 0,
            "reasoning": "No job description available for scoring.",
            "matching_skills": [],
            "missing_skills": [],
            "seniority_fit": "unknown",
        }

    prompt = SCORING_PROMPT.format(
        resume=_get_resume(),
        title=title or "Unknown",
        company=company or "Unknown",
        location=location or "Unknown",
        description=description[:4000],  # cap to avoid token limits
    )

    try:
        response = _get_client().models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,  # low temp for consistent scoring
                max_output_tokens=500,
            ),
        )

        text = response.text.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        result = json.loads(text)

        # Validate and normalize
        result["score"] = max(1, min(10, int(result.get("score", 0))))
        result.setdefault("reasoning", "")
        result.setdefault("matching_skills", [])
        result.setdefault("missing_skills", [])
        result.setdefault("seniority_fit", "unknown")

        return result

    except json.JSONDecodeError as e:
        logger.warning("Failed to parse Gemini response for '%s': %s", title, e)
        return {"score": 0, "reasoning": f"Parse error: {e}", "matching_skills": [], "missing_skills": [], "seniority_fit": "unknown"}
    except Exception as e:
        logger.warning("Gemini API error for '%s': %s", title, e)
        return {"score": 0, "reasoning": f"API error: {e}", "matching_skills": [], "missing_skills": [], "seniority_fit": "unknown"}


def score_jobs(jobs: list[dict], delay: float = 0.5) -> list[dict]:
    """Score a batch of jobs, adding score data to each job dict.

    Args:
        jobs: List of job dicts with keys: title, company, location, description
        delay: Seconds to wait between API calls (rate limiting)

    Returns:
        The same list with score, reasoning, matching, missing keys added.
    """
    total = len(jobs)
    logger.info("Scoring %d jobs with Gemini (%s)...", total, GEMINI_MODEL)

    for i, job in enumerate(jobs, 1):
        result = score_job(
            title=job.get("title", ""),
            company=job.get("company", ""),
            location=job.get("location", ""),
            description=job.get("description", ""),
        )

        job["score"] = result["score"]
        job["reasoning"] = result["reasoning"]
        job["matching"] = ", ".join(result.get("matching_skills", []))
        job["missing"] = ", ".join(result.get("missing_skills", []))
        job["seniority_fit"] = result.get("seniority_fit", "unknown")

        if i % 10 == 0 or i == total:
            logger.info("  Scored %d/%d (latest: '%s' → %d/10)", i, total, job.get("title", "")[:40], result["score"])

        if delay > 0 and i < total:
            time.sleep(delay)

    return jobs
