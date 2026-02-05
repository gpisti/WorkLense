from src.transformers.parsers.base_parser import BaseParser
from src.database.models import RawJob


class ArbeitnowParser(BaseParser):
    
    @staticmethod
    def parse(data: dict, raw_job: RawJob) -> dict:
        """Parse Arbeitnow job data."""
        return {
            'external_id': raw_job.external_id,
            'title': data.get('title', ''),
            'description': data.get('description', ''),
            'url': data.get('url', ''),
            'company_name': data.get('company', {}).get('name', ''),
            'city': None,
            'country': None,
            'country_name': None,
            'is_remote': data.get('remote', False),
            'is_hybrid': False,
            'salary_min': None,
            'salary_max': None,
            'salary_currency': None,
            'salary_period': None,
            'employment_type': 'full_time',
            'seniority_level': None,
            'posted_at': ArbeitnowParser.parse_date(data.get('created_at'))
        }
