"""Gemini LLM-based job relevance scorer.

Sends your resume + a batch of job descriptions to Gemini and receives
a structured relevance score (1-10) with reasoning for each job.
Batching reduces the number of API requests and overall token usage.
"""

import json
import logging
import time
from typing import List, Dict, Any

from google import genai
from google.genai import types

from config import GEMINI_MODEL, RESUME_TEXT_PATH, FALLBACK_MODELS

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

You will be provided with a batch of jobs.
Evaluate how well this candidate fits each job. Consider:
1. Technical skill overlap (how many required skills does the candidate have?)
2. Experience level match (candidate has ~1 year of experience as an apprentice)
3. Domain relevance (backend, data engineering, AI/LLM, full-stack)
4. Growth potential (can the candidate realistically grow into this role?)
5. Location fit (candidate is based in India)

For EACH job, provide an evaluation.
Respond with ONLY a JSON object (no markdown, no code fences). The keys should be the JOB_ID provided in the input, and the values should be the evaluation object.
Example format:
{{
    "JOB_0": {{
        "score": <1-10 integer>,
        "reasoning": "<2-3 sentence explanation>",
        "matching_skills": ["<skill1>", "<skill2>"],
        "missing_skills": ["<skill1>", "<skill2>"],
        "seniority_fit": "<too_junior|good|stretch|too_senior>"
    }},
    "JOB_1": {{ ... }}
}}

Scoring guide:
- 9-10: Near-perfect match, candidate should apply immediately
- 7-8: Strong match, most skills align, worth applying
- 5-6: Decent match, some skill gaps but learnable
- 3-4: Weak match, significant gaps
- 1-2: Poor match, wrong domain or way too senior

JOBS TO EVALUATE:
{jobs_text}
"""

_resume_text: str | None = None


def _get_resume() -> str:
    """Load and cache the resume text."""
    global _resume_text
    if _resume_text is None:
        _resume_text = RESUME_TEXT_PATH.read_text(encoding="utf-8")
    return _resume_text


def score_jobs_batch(
    jobs_batch: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Scores a batch of up to 25 jobs in a single prompt."""
    if not jobs_batch:
        return {}

    jobs_text_parts = []
    for i, job in enumerate(jobs_batch):
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        location = job.get("location", "Unknown")
        # Cap description aggressively when batching to avoid hitting prompt limits
        # 1500 chars is usually enough to capture core responsibilities/requirements
        desc = job.get("description", "")[:1500]

        jobs_text_parts.append(
            f"--- JOB_{i} ---\nTITLE: {title}\nCOMPANY: {company}\nLOCATION: {location}\nDESCRIPTION:\n{desc}\n"
        )

    jobs_text = "\n".join(jobs_text_parts)

    prompt = SCORING_PROMPT.format(
        resume=_get_resume(), jobs_text=jobs_text
    )

    for model_name in FALLBACK_MODELS:
        try:
            response = _get_client().models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,  # low temp for consistent scoring
                    max_output_tokens=8192,
                ),
            )

            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = (
                    text.split("\n", 1)[1] if "\n" in text else text[3:]
                )
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

            result = json.loads(text)
            return result

        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse Gemini response for batch (Model: %s): %s",
                model_name,
                e,
            )
            return {}  # Parse error is likely prompt related, fallback might not help
        except Exception as e:
            error_msg = str(e).lower()
            logger.warning(
                "Gemini API error with model %s: %s", model_name, e
            )

            # If it's a rate limit or quota issue, we try the next model
            if (
                "429" in error_msg
                or "quota" in error_msg
                or "exhausted" in error_msg
            ):
                logger.info(
                    "Rate limit / quota hit for %s. Retrying with next fallback model...",
                    model_name,
                )
                continue
            else:
                # For other unknown API errors, we also retry just in case it's a temporary model issue
                logger.info("Attempting fallback due to API error...")
                continue

    logger.error("All fallback models failed to score this batch.")
    return {}


def score_jobs(jobs: list[dict], delay: float = 2.0) -> list[dict]:
    """Score a list of jobs in batches, adding score data to each job dict.

    Args:
        jobs: List of job dicts with keys: title, company, location, description
        delay: Seconds to wait between API calls (rate limiting)

    Returns:
        The same list with score, reasoning, matching, missing keys added.
    """
    total = len(jobs)
    logger.info(
        "Scoring %d jobs with Gemini (%s) in batches...",
        total,
        GEMINI_MODEL,
    )

    batch_size = 25
    scored_count = 0

    for i in range(0, total, batch_size):
        batch = jobs[i : i + batch_size]
        batch_results = score_jobs_batch(batch)

        for j, job in enumerate(batch):
            job_key = f"JOB_{j}"
            res = batch_results.get(job_key, {})

            job["score"] = max(1, min(10, int(res.get("score", 0))))
            job["reasoning"] = res.get(
                "reasoning", "Failed to score or parse."
            )
            job["matching"] = ", ".join(
                res.get("matching_skills", [])
                if isinstance(res.get("matching_skills"), list)
                else []
            )
            job["missing"] = ", ".join(
                res.get("missing_skills", [])
                if isinstance(res.get("missing_skills"), list)
                else []
            )
            job["seniority_fit"] = res.get("seniority_fit", "unknown")

        scored_count += len(batch)
        total_batches = (total + batch_size - 1) // batch_size
        current_batch = (i // batch_size) + 1
        logger.info(
            "  Scored batch %d/%d (total %d/%d)",
            current_batch,
            total_batches,
            scored_count,
            total,
        )

        # Wait before next batch to respect rate limits
        if delay > 0 and i + batch_size < total:
            time.sleep(delay)

    return jobs
