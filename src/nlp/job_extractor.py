"""Single LLM call to extract structured job data from full ad text. Returns one JSON blob."""
import json
import time
import requests

from src.config.settings import settings
from src.utils.logger import logger

_MAX_TEXT_CHARS = 20_000
_MAX_RETRIES = 3
_RETRY_DELAY_SEC = 2

_EXTRACTION_PROMPT = """Extract structured data from this job ad. Return only a valid JSON object (no markdown, no code fence). Use exactly this structure; use null for missing values:

{
  "company_name": "string or null",
  "city": "string or null",
  "country": "2-letter ISO code or null",
  "country_name": "string or null",
  "technologies": [ {"name": "string", "category": "language|framework|database|tool"} ],
  "skills": [ {"name": "string", "type": "hard|soft"} ],
  "experience_years_min": number or null,
  "experience_years_max": number or null,
  "education_required": "one of: phd, masters, bachelors, associate, high_school, none_required, or null",
  "benefits": [ "string" ],
  "employment_type": "string or null",
  "seniority_level": "string or null",
  "is_remote": boolean,
  "is_hybrid": boolean,
  "salary_min": number or null,
  "salary_max": number or null,
  "salary_currency": "3-letter code or null",
  "salary_period": "string or null"
}

Rules:
- Extract only what is explicitly stated or clearly implied. Use null when not found.
- Technologies: only concrete named products (Python, React, PostgreSQL, Docker). Exclude generic terms (analytics, security, Excel as category, BI-Tools).
- Skills: soft = communication, teamwork, problem-solving; hard = domain/tool skills that are not technologies. Short names only.
- education_required: use exactly one of the listed values. PhD/doctorate = phd, Master's/MSc/MBA = masters, Bachelor's/BSc/BA/degree = bachelors, Associate/vocational = associate, High school/secondary = high_school, Not required/not mentioned = none_required, Unknown = null.
- employment_type: e.g. full_time, part_time, working_student. seniority_level: e.g. junior, senior, lead.
- benefits: list concrete perks (health insurance, home office, training).
- salary numbers as numbers; currency as EUR, GBP, USD etc.

Job ad:

"""


def _one_extraction_attempt(prompt: str) -> dict | None:
    """Single LLM request and JSON parse. Returns dict or None."""
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": settings.OLLAMA_TECH_MODEL, "prompt": prompt, "stream": False},
            timeout=90,
        )
        raw = r.json().get("response", "")
    except Exception as e:
        logger.warning(f"Job extraction LLM request failed: {e}")
        return None

    start = raw.find("{")
    if start == -1:
        return None

    depth = 0
    for i, c in enumerate(raw[start:], start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(raw[start : i + 1])
                except json.JSONDecodeError:
                    return None
                if isinstance(data, dict):
                    return data
                return None
    return None


def extract_job_structured(title: str, description: str) -> dict | None:
    """Send full job text to LLM; return parsed JSON dict or None on failure. Retries on request or JSON parse failure."""
    text = (title or "") + "\n\n" + (description or "")
    text = text.strip()[: _MAX_TEXT_CHARS]
    if not text:
        return None

    prompt = _EXTRACTION_PROMPT + text
    logger.debug(f"Job extraction: sending {len(text)} chars to LLM")
    t0 = time.monotonic()
    for attempt in range(1, _MAX_RETRIES + 1):
        data = _one_extraction_attempt(prompt)
        if data is not None:
            elapsed = time.monotonic() - t0
            logger.info(f"Job extraction: OK attempt {attempt} ({elapsed:.1f}s)")
            return data
        if attempt < _MAX_RETRIES:
            delay = _RETRY_DELAY_SEC * attempt
            logger.debug(f"Job extraction: no valid JSON, retry in {delay}s (attempt {attempt}/{_MAX_RETRIES})")
            time.sleep(delay)
    elapsed = time.monotonic() - t0
    logger.debug(f"Job extraction: failed after {_MAX_RETRIES} attempts ({elapsed:.1f}s)")
    return None
