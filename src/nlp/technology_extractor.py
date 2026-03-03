"""Extract technologies from job text via LLM, map to technologies.id. Unknown names are inserted."""
import json
import re
import time
import requests
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from rapidfuzz import fuzz, process

from src.config.settings import settings
from src.database.models import Technology, SessionLocal
from src.utils.logger import logger

# Canonical categories for technologies (LLM output is normalized to these)
_CATEGORIES = frozenset({"language", "framework", "database", "tool", "other"})
_CATEGORY_ALIASES = {
    "programming language": "language", "languages": "language", "lang": "language",
    "framework": "framework", "frameworks": "framework", "library": "framework", "libraries": "framework",
    "database": "database", "databases": "database", "db": "database",
    "tool": "tool", "tools": "tool", "platform": "tool", "infrastructure": "tool",
}

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
_FUZZY_SCORE_CUTOFF = 88  # e.g. "React" vs "ReactJS" -> use existing


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
    """Call LLM to get tech names by category, map to existing technologies, insert new with category. Return list of ids."""
    text = _pick_tech_relevant_text(title, description)
    prompt = (
        'Extract only concrete, named technologies (programming languages, frameworks, databases, tools/platforms) '
        'that are explicitly mentioned. Return a JSON object with exactly these keys (each value is an array of strings): '
        '"language", "framework", "database", "tool". '
        'Rules: Include only named products or standards (e.g. Python, React, PostgreSQL, Docker, AWS). '
        'Exclude: generic hardware (USB, tablet, laptop); standalone concepts (automation, analytics, security, network, '
        'scripting, logging, version control, SEO, CRM, social media); broad categories (Office, Excel, BI-Tools, '
        'Monitoring-Tools); vague terms (Digitale Tools, workflow, ERP when not a product name). '
        'If in doubt whether something is a concrete technology name, omit it. '
        'Example: {"language": ["Python", "TypeScript"], "framework": ["React", "Django"], "database": ["PostgreSQL"], "tool": ["Docker", "GitHub Actions"]}.\n\n' + text
    )
    logger.debug(f"LLM tech extraction: sending {len(text)} chars")
    t0 = time.monotonic()
    try:
        r = requests.post(
            f"{settings.OLLAMA_URL.rstrip('/')}/api/generate",
            json={"model": settings.OLLAMA_TECH_MODEL, "prompt": prompt, "stream": False},
            timeout=60,
        )
        raw = r.json().get("response", "")
    except Exception as e:
        logger.warning(f"LLM tech extraction request failed: {e}")
        return []

    elapsed = time.monotonic() - t0
    # Parse JSON object from response (brace-count to allow nested arrays)
    pairs = []
    start = raw.find("{")
    if start != -1:
        data = None
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
                        pass
                    break
        if isinstance(data, dict):
            for cat_key, names in data.items():
                c = str(cat_key).lower().strip()
                canonical = _CATEGORY_ALIASES.get(c, c)
                category = canonical if canonical in _CATEGORIES else "other"
                if isinstance(names, list):
                    for n in names:
                        n = str(n).strip()
                        if n:
                            pairs.append((category, n))
    if not pairs:
        logger.debug(f"LLM tech extraction: no categorized JSON in response ({elapsed:.1f}s)")
        return []

    techs = session.query(Technology).all()
    name_to_id = {}
    for t in techs:
        name_to_id[t.name.lower()] = t.id
        for a in (t.aliases or []):
            name_to_id[str(a).lower()] = t.id
    existing_names = list(name_to_id.keys())

    ids = []
    seen = set()
    for category, n in pairs:
        if not n or len(n) > 100:
            continue
        k = n.lower()
        if k in name_to_id:
            tid = name_to_id[k]
            if tid not in seen:
                ids.append(tid)
                seen.add(tid)
            continue
        # No exact match: try fuzzy match to avoid duplicates (e.g. React vs ReactJS)
        if existing_names:
            best = process.extractOne(k, existing_names, scorer=fuzz.token_sort_ratio, score_cutoff=_FUZZY_SCORE_CUTOFF)
            if best:
                matched_name, score, _ = best
                tid = name_to_id[matched_name]
                if tid not in seen:
                    ids.append(tid)
                    seen.add(tid)
                name_to_id[k] = tid
                continue
        new_session = SessionLocal()
        try:
            tech = Technology(name=n.strip()[:100], category=category)
            new_session.add(tech)
            new_session.flush()
            new_id = tech.id
            new_session.commit()
            name_to_id[k] = new_id
            existing_names.append(k)
            ids.append(new_id)
            seen.add(new_id)
        except IntegrityError:
            new_session.rollback()
            existing = new_session.query(Technology).filter(Technology.name.ilike(n)).first()
            if existing and existing.id not in seen:
                name_to_id[k] = existing.id
                existing_names.append(k)
                ids.append(existing.id)
                seen.add(existing.id)
        finally:
            new_session.close()
    logger.info(f"LLM tech extraction: {len(pairs)} names -> {len(ids)} in DB ({elapsed:.1f}s)")
    return ids
