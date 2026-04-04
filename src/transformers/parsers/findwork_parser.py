import re

from src.utils.date_utils import parse_date
from src.database.models import RawJob


class FindworkParser:

    _REMOTE_PATTERN = re.compile(r'\bremote\b', re.IGNORECASE)
    _HYBRID_PATTERN = re.compile(r'\bhybrid\b', re.IGNORECASE)

    @staticmethod
    def parse(data: dict, raw_job: RawJob) -> dict:
        title = data.get('role', '') or ''
        location_raw = data.get('location', '') or ''

        city, country, country_name = FindworkParser._parse_location(location_raw)

        is_remote = bool(data.get('remote'))
        if not is_remote and FindworkParser._REMOTE_PATTERN.search(location_raw):
            is_remote = True
        is_hybrid = bool(FindworkParser._HYBRID_PATTERN.search(location_raw))

        emp_type = data.get('employment_type') or None
        if emp_type:
            emp_type = emp_type.strip().lower().replace('-', '_').replace(' ', '_')

        seniority = FindworkParser._extract_seniority(title)

        return {
            'external_id': raw_job.external_id,
            'title': title,
            'description': data.get('text', ''),
            'url': data.get('url', ''),
            'company_name': data.get('company_name', ''),
            'city': city,
            'country': country,
            'country_name': country_name,
            'is_remote': is_remote,
            'is_hybrid': is_hybrid,
            'salary_min': None,
            'salary_max': None,
            'salary_currency': None,
            'salary_period': None,
            'employment_type': emp_type,
            'seniority_level': seniority,
            'posted_at': parse_date(data.get('date_posted')),
        }

    @staticmethod
    def _extract_seniority(title: str) -> str | None:
        t = title.lower()
        if 'principal' in t or 'staff' in t:
            return 'principal'
        if 'senior' in t or 'sr.' in t or 'sr ' in t:
            return 'senior'
        if 'lead' in t or 'head of' in t:
            return 'lead'
        if 'junior' in t or 'jr.' in t or 'jr ' in t or 'entry' in t or 'intern' in t:
            return 'junior'
        if 'mid' in t and ('level' in t or '-level' in t):
            return 'mid'
        return None

    _COUNTRY_HINTS: dict[str, tuple[str, str]] = {
        'germany': ('de', 'Germany'), 'deutschland': ('de', 'Germany'),
        'united states': ('us', 'United States'), 'usa': ('us', 'United States'),
        'united kingdom': ('gb', 'United Kingdom'), 'uk': ('gb', 'United Kingdom'),
        'canada': ('ca', 'Canada'),
        'france': ('fr', 'France'),
        'netherlands': ('nl', 'Netherlands'),
        'spain': ('es', 'Spain'),
        'italy': ('it', 'Italy'),
        'poland': ('pl', 'Poland'),
        'austria': ('at', 'Austria'),
        'switzerland': ('ch', 'Switzerland'),
        'sweden': ('se', 'Sweden'),
        'norway': ('no', 'Norway'),
        'denmark': ('dk', 'Denmark'),
        'finland': ('fi', 'Finland'),
        'belgium': ('be', 'Belgium'),
        'ireland': ('ie', 'Ireland'),
        'portugal': ('pt', 'Portugal'),
        'australia': ('au', 'Australia'),
        'india': ('in', 'India'),
        'singapore': ('sg', 'Singapore'),
        'japan': ('jp', 'Japan'),
        'brazil': ('br', 'Brazil'),
        'israel': ('il', 'Israel'),
        'europe': (None, None),
    }

    @staticmethod
    def _parse_location(location: str) -> tuple[str | None, str | None, str | None]:
        """Best-effort city / country extraction from free-text location."""
        if not location:
            return None, None, None

        parts = [p.strip() for p in re.split(r'[,/|]', location) if p.strip()]
        noise = {'or', 'and', 'remote', 'hybrid', 'onsite', 'on-site', 'in'}
        cleaned = [p for p in parts if p.lower() not in noise]

        country_code, country_name = None, None
        loc_lower = location.lower()
        for hint, (cc, cn) in FindworkParser._COUNTRY_HINTS.items():
            if hint in loc_lower and cc:
                country_code, country_name = cc, cn
                break

        city = None
        if cleaned:
            candidate = cleaned[0]
            if len(candidate) < 60 and candidate.lower() not in FindworkParser._COUNTRY_HINTS:
                city = candidate

        return city, country_code, country_name

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
