"""Extract technologies from job text via LLM, map to technologies.id."""
import json
import re
import time
import requests
from sqlalchemy.orm import Session

from src.config.settings import settings
from src.database.models import Technology
from src.utils.logger import logger

# Headers that usually introduce tech/requirements (EN + DE)
_TECH_SECTION_HEADERS = re.compile(
    r'(?:^|\n)\s*(?:'
    r'requirements?|qualifications?|tech(nology)?\s*[- ]?stack|stack|tools?|skills?|'
    r'(?:programming\s+)?languages?|we\s+use|you\s+have|must\s+have|nice\s+to\s+have|'
    r'anforderungen|qualifikation|tech[- ]stack|kenntnisse|erfahrung|du\s+bringst|wir\s+setzen'
    r')[\s:]',
    re.IGNORECASE
)
_MAX_TEXT_CHARS = 2500


def _pick_tech_relevant_text(title: str, description: str) -> str:
    """Take title + sections that look like requirements/tech stack, so we don't cut the list off."""
    if not description:
        return title
    # Split into sections: block of text that starts with a header line (short line ending with colon)
    sections = re.split(r'\n\s*(?=[^\n]{1,50}:\s*\n)', '\n' + description.strip())
    chosen = []
    for block in sections:
        block = block.strip()
        if not block or len(block) < 20:
            continue
        first_line = block.split('\n')[0].lower()
        if _TECH_SECTION_HEADERS.search(first_line) or _TECH_SECTION_HEADERS.search(block[:200]):
            chosen.append(block)
    if chosen:
        out = title + '\n\n' + '\n\n'.join(chosen)
    else:
        out = title + '\n\n' + description
    return out[:_MAX_TEXT_CHARS]


def extract_technology_ids(session: Session, title: str, description: str) -> list[int]:
    """Call LLM to get tech names, map to existing technologies, return list of ids."""
    text = _pick_tech_relevant_text(title, description)
    prompt = (
        'Extract all technologies (languages, frameworks, databases, tools) explicitly mentioned. '
        'Return only a JSON array of strings, e.g. ["Python", "React"].\n\n' + text
    )
    logger.debug(f"LLM tech extraction: sending {len(text)} chars")
    t0 = time.monotonic()
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        raw = r.json().get("response", "")
    except Exception as e:
        logger.warning(f"LLM tech extraction request failed: {e}")
        return []

    elapsed = time.monotonic() - t0
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        logger.debug(f"LLM tech extraction: no JSON array in response ({elapsed:.1f}s)")
        return []
    try:
        names = json.loads(match.group())
    except json.JSONDecodeError:
        logger.debug(f"LLM tech extraction: JSON parse failed ({elapsed:.1f}s)")
        return []
    if not isinstance(names, list):
        return []
    names = [str(n).strip() for n in names if n]

    techs = session.query(Technology).all()
    name_to_id = {}
    for t in techs:
        name_to_id[t.name.lower()] = t.id
        for a in (t.aliases or []):
            name_to_id[str(a).lower()] = t.id

    ids = []
    seen = set()
    for n in names:
        k = n.lower()
        if k in name_to_id and name_to_id[k] not in seen:
            ids.append(name_to_id[k])
            seen.add(name_to_id[k])
    logger.info(f"LLM tech extraction: {len(names)} names -> {len(ids)} matched in DB ({elapsed:.1f}s)")
    return ids
