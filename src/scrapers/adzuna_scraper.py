import requests
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger
from src.database.models import RawJob, get_session
from src.config.settings import settings

_USER_AGENT = "Mozilla/5.0 (compatible; WorkLense/1.0)"
_MIN_SELECTOR_CHARS = 100

_ADZUNA_SELECTOR = (
    "body > div.container.mx-auto.bg-white.font-sans.text-adzuna-gray-900.md\\:px-4 "
    "> main > div > section.lg\\:flex.mb-4 > div.flex-grow > section"
)


def _fetch_full_description(url: str, max_chars: int = 15000, timeout: int = 10) -> str | None:
    if not url or not url.startswith("http"):
        return None
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        text = None
        el = soup.select_one(_ADZUNA_SELECTOR)
        if el:
            text = el.get_text(separator="\n", strip=True)
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not text or len(text) < _MIN_SELECTOR_CHARS:
            text = None

        if text is None:
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

        return text[:max_chars] if text else None
    except Exception as e:
        logger.debug(f"Fetch description from URL failed: {e}")
        return None


class AdzunaScraper:
    
    COUNTRIES = ['gb', 'us', 'at', 'au', 'be', 'br', 'ca', 'ch', 'de', 'es', 'fr', 'in', 'it', 'mx', 'nl', 'nz', 'pl', 'sg', 'za']
    
    def __init__(self):
        self.logger = logger
        self.BASE_URL = "https://api.adzuna.com/v1/api"
        self.SOURCE_NAME = "adzuna"
        self.request_interval = 2.4
        self.last_request = 0
        self.rate_lock = threading.Lock()
        self.app_id = settings.ADZUNA_APP_ID
        self.app_key = settings.ADZUNA_API_KEY
        
        if not self.app_id or not self.app_key:
            raise ValueError("ADZUNA_APP_ID and ADZUNA_API_KEY must be set in settings")
    
    def run(self) -> int:
        self.logger.info(f"Starting {self.SOURCE_NAME} scraper for {len(self.COUNTRIES)} countries (8 parallel)...")
        
        total_saved = 0
        
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(self._fetch_country, country): country for country in self.COUNTRIES}
            
            for future in as_completed(futures):
                country = futures[future]
                try:
                    country_saved = future.result()
                    total_saved += country_saved
                    self.logger.info(f"Country {country}: {country_saved} jobs saved")
                except Exception as e:
                    self.logger.error(f"Error fetching country {country}: {e}")
        
        self.logger.info(f"Finished: {total_saved} total jobs saved")
        return total_saved
    
    def _fetch_country(self, country: str) -> int:
        saved = 0
        page = 1
        
        with get_session() as session:
            while True:
                with self.rate_lock:
                    elapsed = time.time() - self.last_request
                    if elapsed < self.request_interval:
                        time.sleep(self.request_interval - elapsed)
                    self.last_request = time.time()
                
                try:
                    url = f"{self.BASE_URL}/jobs/{country}/search/{page}"
                    response = requests.get(
                        url,
                        params={
                            'app_id': self.app_id,
                            'app_key': self.app_key,
                            'category': 'it-jobs',
                            'results_per_page': 50
                        },
                        timeout=30
                    )
                    
                    if response.status_code == 404:
                        break
                    
                    if response.status_code == 429:
                        self.logger.warning(f"Rate limited on {country} page {page}, waiting 30...")
                        time.sleep(30)
                        continue
                    
                    response.raise_for_status()
                    data = response.json()
                    jobs = data.get('results', [])
                    
                    if not jobs:
                        break
                    
                    for job in jobs:
                        try:
                            url = job.get('redirect_url')
                            if url:
                                full = _fetch_full_description(url)
                                if full:
                                    job = {**job, 'full_description': full}
                            raw_job = RawJob(
                                source=f"{self.SOURCE_NAME}_{country}",
                                external_id=str(job.get('id', '')),
                                raw_data=job
                            )
                            session.add(raw_job)
                            session.flush()
                            saved += 1
                        except IntegrityError:
                            session.rollback()
                            continue
                    
                    self.logger.info(f"{country} page {page}: {len(jobs)} jobs, saved {saved} total")
                    page += 1
                    
                except Exception as e:
                    self.logger.error(f"Error on {country} page {page}: {e}")
                    break
        
        return saved


if __name__ == "__main__":
    scraper = AdzunaScraper()
    scraper.run()

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
