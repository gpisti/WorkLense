from datetime import datetime, timezone

from src.transformers.parsers.base_parser import BaseParser
from src.database.models import RawJob


class ArbeitnowParser(BaseParser):
    
    @staticmethod
    def parse(data: dict, raw_job: RawJob) -> dict:
        company_name = data.get('company_name') or data.get('company', {}).get('name', '')
        city = data.get('location') or None

        job_types = data.get('job_types') or []
        jt_text = ' '.join([jt.lower() for jt in job_types])

        if 'working student' in jt_text or 'werkstudent' in jt_text:
            employment_type = 'working_student'
        elif 'teilzeit' in jt_text or 'part-time' in jt_text:
            employment_type = 'part_time'
        elif 'vollzeit' in jt_text or 'full-time' in jt_text:
            employment_type = 'full_time'
        else:
            employment_type = 'full_time'

        title = data.get('title', '') or ''
        title_lower = title.lower()

        seniority = None
        if 'senior' in title_lower:
            seniority = 'senior'
        elif 'junior' in title_lower or 'werkstudent' in title_lower or 'working student' in title_lower:
            seniority = 'junior'
        elif 'lead' in title_lower or 'leitung' in title_lower:
            seniority = 'lead'

        created_at = data.get('created_at')
        if isinstance(created_at, (int, float)):
            posted_at = datetime.fromtimestamp(created_at, tz=timezone.utc)
        else:
            posted_at = ArbeitnowParser.parse_date(created_at)

        return {
            'external_id': raw_job.external_id,
            'title': title,
            'description': data.get('description', ''),
            'url': data.get('url', ''),
            'company_name': company_name,
            'city': city,
            'country': 'de',
            'country_name': 'Germany',
            'is_remote': data.get('remote', False),
            'is_hybrid': False,
            'salary_min': None,
            'salary_max': None,
            'salary_currency': None,
            'salary_period': None,
            'employment_type': employment_type,
            'seniority_level': seniority,
            'posted_at': posted_at
        }
