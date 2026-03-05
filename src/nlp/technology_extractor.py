from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from rapidfuzz import fuzz, process

from src.database.models import Technology, SessionLocal

_CATEGORIES = frozenset({"language", "framework", "database", "tool", "other"})
_CATEGORY_ALIASES = {
    "programming language": "language", "languages": "language", "lang": "language",
    "framework": "framework", "frameworks": "framework", "library": "framework", "libraries": "framework",
    "database": "database", "databases": "database", "db": "database",
    "tool": "tool", "tools": "tool", "platform": "tool", "infrastructure": "tool",
}


_FUZZY_SCORE_CUTOFF = 88


def resolve_technology_pairs_to_ids(session: Session, pairs: list[tuple[str, str]]) -> list[int]:
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
        c = str(category or "").lower().strip()
        canonical = _CATEGORY_ALIASES.get(c, c)
        cat = canonical if canonical in _CATEGORIES else "other"
        k = n.lower()
        if k in name_to_id:
            tid = name_to_id[k]
            if tid not in seen:
                ids.append(tid)
                seen.add(tid)
            continue
        if existing_names:
            best = process.extractOne(k, existing_names, scorer=fuzz.token_sort_ratio, score_cutoff=_FUZZY_SCORE_CUTOFF)
            if best:
                matched_name, _, _ = best
                tid = name_to_id[matched_name]
                if tid not in seen:
                    ids.append(tid)
                    seen.add(tid)
                name_to_id[k] = tid
                continue
        new_session = SessionLocal()
        try:
            tech = Technology(name=n.strip()[:100], category=cat)
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
    return ids
