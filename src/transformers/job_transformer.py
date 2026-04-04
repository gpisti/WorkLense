import hashlib
import json
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger
from src.database.models import (
    get_session, RawJob, Job, Company, Location, JobTechnology, JobSkill
)
from src.transformers.parsers.arbeitnow_parser import ArbeitnowParser
from src.transformers.parsers.adzuna_parser import AdzunaParser
from src.transformers.parsers.findwork_parser import FindworkParser
from src.nlp.company_normalizer import CompanyNormalizer
from src.nlp.job_extractor import extract_job_structured
from src.nlp.technology_extractor import resolve_technology_pairs_to_ids
from src.nlp.skill_resolver import resolve_skill_pairs_to_ids


CONTINENT_MAP = {
    'gb': 'Europe', 'at': 'Europe', 'be': 'Europe', 'de': 'Europe',
    'es': 'Europe', 'fr': 'Europe', 'it': 'Europe', 'nl': 'Europe', 'pl': 'Europe',
    'us': 'North America', 'ca': 'North America', 'mx': 'North America',
    'au': 'Asia-Pacific', 'nz': 'Asia-Pacific', 'sg': 'Asia-Pacific', 'in': 'Asia-Pacific',
    'br': 'South America',
    'za': 'Africa'
}


def _to_db_null(val):
    if val is None:
        return None
    if isinstance(val, str):
        s = val.strip().lower()
        if s in ('null', 'none', ''):
            return None
    return val


def _normalize_benefits(raw) -> list | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ('null', 'none', ''):
            return None
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    if not isinstance(raw, list):
        return None
    sanitized = [str(x).strip() for x in raw if x is not None and str(x).strip()]
    return sanitized if sanitized else None


_EDUCATION_VALID = {"phd", "masters", "bachelors", "associate", "high_school", "none_required"}

_EDUCATION_ALIASES = {
    "phd": "phd", "ph.d": "phd", "doktor": "phd", "doctorate": "phd",
    "master": "masters", "msc": "masters", "m.sc": "masters", "mba": "masters",
    "diplom": "masters", "postgrad": "masters",
    "bachelor": "bachelors", "bsc": "bachelors", "b.sc": "bachelors",
    "b.a.": "bachelors", "degree": "bachelors", "university": "bachelors",
    "egyetem": "bachelors", "undergraduate": "bachelors", "college": "bachelors",
    "associate": "associate", "vocational": "associate", "szakképz": "associate",
    "technician": "associate",
    "high school": "high_school", "secondary": "high_school", "érettségi": "high_school",
    "erettsegi": "high_school", "abitur": "high_school", "gymnasium": "high_school",
    "none": "none_required", "not required": "none_required", "no formal": "none_required",
    "no degree": "none_required", "keine": "none_required",
}


def _normalize_education(raw) -> str | None:
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    s = raw.strip()
    if not s:
        return None
    low = s.lower()
    if low in ('null', 'none'):
        return None
    if low in _EDUCATION_VALID:
        return low
    for pattern, canonical in _EDUCATION_ALIASES.items():
        if pattern in low:
            return canonical
    return None


def _merge_extracted_parsed(extracted: dict | None, parsed: dict) -> dict:
    n = _to_db_null

    if not extracted:
        cc = n(parsed.get('country'))
        return {
            'company_name': n(parsed.get('company_name')),
            'city': n(parsed.get('city')),
            'country_code': cc,
            'country_name': n(parsed.get('country_name')) or (cc.upper() if cc else None),
            'is_remote': bool(parsed.get('is_remote')),
            'is_hybrid': bool(parsed.get('is_hybrid')),
            'salary_min': n(parsed.get('salary_min')),
            'salary_max': n(parsed.get('salary_max')),
            'salary_currency': n(parsed.get('salary_currency')),
            'salary_period': n(parsed.get('salary_period')),
            'employment_type': n(parsed.get('employment_type')),
            'seniority_level': n(parsed.get('seniority_level')),
            'experience_years_min': None,
            'experience_years_max': None,
            'education_required': None,
            'raw_benefits': None,
            'tech_list': [],
            'skill_list': [],
        }
    cc = n(extracted.get('country')) or n(parsed.get('country'))
    raw_tech = extracted.get('technologies') or []
    raw_skill = extracted.get('skills') or []
    tech_list = [{k: n(v) for k, v in t.items()} for t in raw_tech if isinstance(t, dict)]
    skill_list = [{k: n(v) for k, v in s.items()} for s in raw_skill if isinstance(s, dict)]

    raw_remote = extracted.get('is_remote') if extracted.get('is_remote') is not None else parsed.get('is_remote', False)
    raw_hybrid = extracted.get('is_hybrid') if extracted.get('is_hybrid') is not None else parsed.get('is_hybrid', False)

    return {
        'company_name': n(extracted.get('company_name')) or n(parsed.get('company_name')),
        'city': n(extracted.get('city')) if extracted.get('city') is not None else n(parsed.get('city')),
        'country_code': cc,
        'country_name': n(extracted.get('country_name')) or n(parsed.get('country_name')) or (cc.upper() if cc else None),
        'is_remote': bool(raw_remote),
        'is_hybrid': bool(raw_hybrid),
        'salary_min': n(extracted['salary_min']) if 'salary_min' in extracted else n(parsed.get('salary_min')),
        'salary_max': n(extracted['salary_max']) if 'salary_max' in extracted else n(parsed.get('salary_max')),
        'salary_currency': n(extracted.get('salary_currency')) or n(parsed.get('salary_currency')),
        'salary_period': n(extracted.get('salary_period')) or n(parsed.get('salary_period')),
        'employment_type': n(extracted.get('employment_type')) or n(parsed.get('employment_type')),
        'seniority_level': n(extracted.get('seniority_level')) or n(parsed.get('seniority_level')),
        'experience_years_min': n(extracted.get('experience_years_min')),
        'experience_years_max': n(extracted.get('experience_years_max')),
        'education_required': _normalize_education(n(extracted.get('education_required'))),
        'raw_benefits': extracted.get('benefits'),
        'tech_list': tech_list,
        'skill_list': skill_list,
    }


class JobTransformer:
    
    def __init__(self, use_llm: bool = True, use_embeddings: bool = True):
        self.logger = logger
        self.company_normalizer = CompanyNormalizer(use_llm=use_llm, use_embeddings=use_embeddings)
        self._company_cache = None
    
    def run(self, limit: int = None) -> int:
        self.logger.info("Starting job transformation...")
        
        with get_session() as session:
            query = session.query(RawJob).filter(~RawJob.processed)
            if limit:
                query = query.limit(limit)
            
            raw_jobs = query.all()
            self.logger.info(f"Found {len(raw_jobs)} unprocessed jobs")
            
            processed = 0
            for i, raw_job in enumerate(raw_jobs, 1):
                raw_job_id = raw_job.id
                self.logger.info(f"[{i}/{len(raw_jobs)}] raw_job id={raw_job_id} source={raw_job.source}")
                try:
                    if self._transform_job(session, raw_job):
                        processed += 1
                except Exception as e:
                    session.rollback()
                    self.logger.error(f"Error processing raw_job {raw_job_id}: {e}")
                    rj = session.get(RawJob, raw_job_id)
                    if rj:
                        rj.error_message = str(e)
                        rj.processed = True
                        session.commit()
            
            self.logger.info(f"Processed {processed}/{len(raw_jobs)} jobs")
            return processed
    
    def _transform_job(self, session, raw_job: RawJob) -> bool:
        if raw_job.source == 'arbeitnow':
            parsed = ArbeitnowParser.parse(raw_job.raw_data, raw_job)
        elif raw_job.source.startswith('adzuna_'):
            parsed = AdzunaParser.parse(raw_job.raw_data, raw_job)
        elif raw_job.source == 'findwork':
            parsed = FindworkParser.parse(raw_job.raw_data, raw_job)
        else:
            self.logger.warning(f"Unknown source: {raw_job.source}")
            return False

        content = (
            parsed['title'].lower().strip() +
            parsed.get('company_name', '').lower().strip() +
            parsed.get('description', '')[:500].lower().strip()
        )
        content_hash = hashlib.sha256(content.encode()).hexdigest()

        if session.query(Job).filter(Job.content_hash == content_hash).first():
            self.logger.debug("Duplicate (content_hash), skip")
            raw_job.processed = True
            raw_job.processed_at = datetime.now(timezone.utc)
            session.commit()
            return False

        extracted = extract_job_structured(parsed['title'], parsed['description'])
        merged = _merge_extracted_parsed(extracted, parsed)
        benefits_for_job = _normalize_benefits(merged['raw_benefits'])

        country_code = merged['country_code']
        if isinstance(country_code, str):
            country_code = country_code.strip().lower()
            if len(country_code) != 2:
                country_code = None

        company_id = None
        if merged['company_name']:
            if self._company_cache is None:
                companies = session.query(Company).all()
                self._company_cache = [(c.id, c.name, c.normalized_name) for c in companies]
                self.logger.debug(f"Loaded {len(self._company_cache)} companies into cache")

            similar_id = self.company_normalizer.find_similar_company(merged['company_name'], self._company_cache)
            if similar_id:
                company_id = similar_id
            else:
                normalized = self.company_normalizer.normalize(merged['company_name'])
                company = Company(name=merged['company_name'], normalized_name=normalized)
                session.add(company)
                session.flush()
                self._company_cache.append((company.id, merged['company_name'], normalized))
                company_id = company.id

        location_id = None
        if country_code:
            location = session.query(Location).filter(
                Location.city == merged['city'],
                Location.country == country_code
            ).first()

            if location:
                location_id = location.id
            else:
                try:
                    location = Location(
                        city=merged['city'],
                        country=country_code,
                        country_name=merged['country_name'] or country_code.upper(),
                        continent=CONTINENT_MAP.get(country_code, 'Unknown')
                    )
                    session.add(location)
                    session.flush()
                    location_id = location.id
                except IntegrityError:
                    session.rollback()
                    location = session.query(Location).filter(
                        Location.city == merged['city'],
                        Location.country == country_code
                    ).first()
                    location_id = location.id if location else None

        job = Job(
            external_id=parsed['external_id'],
            source=raw_job.source,
            title=parsed['title'],
            normalized_title=parsed['title'].lower().strip()[:200],
            description=parsed['description'],
            url=parsed['url'],
            company_id=company_id,
            location_id=location_id,
            raw_job_id=raw_job.id,
            is_remote=merged['is_remote'],
            is_hybrid=merged['is_hybrid'],
            salary_min=merged['salary_min'],
            salary_max=merged['salary_max'],
            salary_currency=merged['salary_currency'],
            salary_period=merged['salary_period'],
            employment_type=merged['employment_type'],
            seniority_level=merged['seniority_level'],
            experience_years_min=merged['experience_years_min'],
            experience_years_max=merged['experience_years_max'],
            education_required=merged['education_required'],
            benefits=benefits_for_job,
            posted_at=parsed['posted_at'],
            content_hash=content_hash
        )

        session.add(job)
        session.flush()

        try:
            tech_pairs = [(t.get('category') or 'other', t.get('name')) for t in merged['tech_list'] if isinstance(t, dict) and t.get('name')]
            tech_ids = resolve_technology_pairs_to_ids(session, tech_pairs) if tech_pairs else []
            for tech_id in tech_ids:
                session.add(JobTechnology(job_id=job.id, technology_id=tech_id))
            if tech_ids:
                self.logger.info(f"Job id={job.id}: {len(tech_ids)} technologies linked")

            skill_pairs = [(s.get('name'), s.get('type')) for s in merged['skill_list'] if isinstance(s, dict) and s.get('name')]
            skill_ids = resolve_skill_pairs_to_ids(session, skill_pairs) if skill_pairs else []
            for skill_id in skill_ids:
                session.add(JobSkill(job_id=job.id, skill_id=skill_id))
            if skill_ids:
                self.logger.info(f"Job id={job.id}: {len(skill_ids)} skills linked")
        except Exception as e:
            self.logger.warning(f"Tech/skill resolution failed for job id={job.id}: {e}")
            session.rollback()
            raise

        raw_job.processed = True
        raw_job.processed_at = datetime.now(timezone.utc)
        session.commit()
        return True


if __name__ == "__main__":
    transformer = JobTransformer()
    transformer.run()

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
