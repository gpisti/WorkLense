import hashlib
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger
from src.database.models import (
    get_session, RawJob, Job, Company, Location
)
from src.transformers.parsers.arbeitnow_parser import ArbeitnowParser
from src.transformers.parsers.adzuna_parser import AdzunaParser
from src.nlp.company_normalizer import CompanyNormalizer


CONTINENT_MAP = {
    'gb': 'Europe', 'at': 'Europe', 'be': 'Europe', 'de': 'Europe',
    'es': 'Europe', 'fr': 'Europe', 'it': 'Europe', 'nl': 'Europe', 'pl': 'Europe',
    'us': 'North America', 'ca': 'North America', 'mx': 'North America',
    'au': 'Asia-Pacific', 'nz': 'Asia-Pacific', 'sg': 'Asia-Pacific', 'in': 'Asia-Pacific',
    'br': 'South America',
    'za': 'Africa'
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
            for raw_job in raw_jobs:
                try:
                    if self._transform_job(session, raw_job):
                        processed += 1
                except Exception as e:
                    self.logger.error(f"Error processing raw_job {raw_job.id}: {e}")
                    raw_job.error_message = str(e)
                    raw_job.processed = True
                    session.commit()
            
            self.logger.info(f"Processed {processed}/{len(raw_jobs)} jobs")
            return processed
    
    def _transform_job(self, session, raw_job: RawJob) -> bool:
        if raw_job.source == 'arbeitnow':
            parsed = ArbeitnowParser.parse(raw_job.raw_data, raw_job)
        elif raw_job.source.startswith('adzuna_'):
            parsed = AdzunaParser.parse(raw_job.raw_data, raw_job)
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
            raw_job.processed = True
            raw_job.processed_at = datetime.now(timezone.utc)
            session.commit()
            return False

        company_id = None
        company_name = parsed.get('company_name')
        if company_name:
            if self._company_cache is None:
                companies = session.query(Company).all()
                self._company_cache = [(c.id, c.name, c.normalized_name) for c in companies]
                self.logger.debug(f"Loaded {len(self._company_cache)} companies into cache")

            similar_id = self.company_normalizer.find_similar_company(company_name, self._company_cache)
            if similar_id:
                company_id = similar_id
            else:
                normalized = self.company_normalizer.normalize(company_name)
                company = Company(name=company_name, normalized_name=normalized)
                session.add(company)
                session.flush()
                self._company_cache.append((company.id, company_name, normalized))
                company_id = company.id

        location_id = None
        country_code = parsed.get('country')
        if country_code:
            city = parsed.get('city')
            location = session.query(Location).filter(
                Location.city == city,
                Location.country == country_code
            ).first()

            if location:
                location_id = location.id
            else:
                try:
                    location = Location(
                        city=city,
                        country=country_code,
                        country_name=parsed.get('country_name') or country_code.upper(),
                        continent=CONTINENT_MAP.get(country_code, 'Unknown')
                    )
                    session.add(location)
                    session.flush()
                    location_id = location.id
                except IntegrityError:
                    session.rollback()
                    location = session.query(Location).filter(
                        Location.city == city,
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
            is_remote=parsed.get('is_remote', False),
            is_hybrid=parsed.get('is_hybrid', False),
            salary_min=parsed.get('salary_min'),
            salary_max=parsed.get('salary_max'),
            salary_currency=parsed.get('salary_currency'),
            salary_period=parsed.get('salary_period'),
            employment_type=parsed.get('employment_type'),
            seniority_level=parsed.get('seniority_level'),
            posted_at=parsed['posted_at'],
            content_hash=content_hash
        )

        session.add(job)
        raw_job.processed = True
        raw_job.processed_at = datetime.now(timezone.utc)
        session.commit()
        return True


if __name__ == "__main__":
    transformer = JobTransformer()
    transformer.run()
