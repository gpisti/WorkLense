from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from rapidfuzz import fuzz, process

from src.database.models import Skill, SessionLocal

_FUZZY_SCORE_CUTOFF = 88
_VALID_TYPES = frozenset({"hard", "soft"})


def _normalize_type(t: str) -> str:
    if not t:
        return "soft"
    v = str(t).lower().strip()
    return v if v in _VALID_TYPES else "soft"


def resolve_skill_pairs_to_ids(session: Session, pairs: list[tuple[str, str]]) -> list[int]:
    skills = session.query(Skill).all()
    name_to_id = {s.name.lower(): s.id for s in skills}
    existing_names = list(name_to_id.keys())

    ids = []
    seen = set()
    for name, stype in pairs:
        if not name or len(name) > 100:
            continue
        stype = _normalize_type(stype)
        k = name.strip().lower()
        if k in name_to_id:
            sid = name_to_id[k]
            if sid not in seen:
                ids.append(sid)
                seen.add(sid)
            continue
        if existing_names:
            best = process.extractOne(k, existing_names, scorer=fuzz.token_sort_ratio, score_cutoff=_FUZZY_SCORE_CUTOFF)
            if best:
                matched_name, _, _ = best
                sid = name_to_id[matched_name]
                if sid not in seen:
                    ids.append(sid)
                    seen.add(sid)
                name_to_id[k] = sid
                continue
        new_session = SessionLocal()
        try:
            skill = Skill(name=name.strip()[:100], type=stype)
            new_session.add(skill)
            new_session.flush()
            new_id = skill.id
            new_session.commit()
            name_to_id[k] = new_id
            existing_names.append(k)
            ids.append(new_id)
            seen.add(new_id)
        except IntegrityError:
            new_session.rollback()
            existing = new_session.query(Skill).filter(Skill.name.ilike(name)).first()
            if existing and existing.id not in seen:
                name_to_id[k] = existing.id
                existing_names.append(k)
                ids.append(existing.id)
                seen.add(existing.id)
        finally:
            new_session.close()
    return ids

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
