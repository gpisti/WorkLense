from src.transformers.parsers.base_parser import BaseParser
from src.database.models import RawJob


class AdzunaParser(BaseParser):
    
    @staticmethod
    def parse(data: dict, raw_job: RawJob) -> dict:
        location = data.get('location', {})
        area = location.get('area', [])
        
        country_code = raw_job.source.split('_')[1] if '_' in raw_job.source else None
        country_name = area[0] if area else None
        
        city = area[-1] if len(area) > 1 else None
        
        return {
            'external_id': str(data.get('id', '')),
            'title': data.get('title', ''),
            'description': data.get('full_description') or data.get('description', ''),
            'url': data.get('redirect_url', ''),
            'company_name': data.get('company', {}).get('display_name', ''),
            'city': city,
            'country': country_code,
            'country_name': country_name,
            'is_remote': False,
            'is_hybrid': False,
            'salary_min': float(data.get('salary_min', 0)) if data.get('salary_min') else None,
            'salary_max': float(data.get('salary_max', 0)) if data.get('salary_max') else None,
            'salary_currency': 'GBP' if country_code == 'gb' else 'USD',
            'salary_period': 'yearly',
            'employment_type': data.get('contract_type', 'full_time'),
            'seniority_level': None,
            'posted_at': AdzunaParser.parse_date(data.get('created'))
        }
