import requests
import time
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger
from src.database.models import RawJob, get_session


class ArbeitnowScraper:
    
    def __init__(self):
        self.logger = logger
        self.API_URL = "https://www.arbeitnow.com/api/job-board-api"
        self.SOURCE_NAME = "arbeitnow"
        self.request_interval = 0.5
        self.last_request = 0
    
    
    def run(self) -> int:
        self.logger.info(f"Starting {self.SOURCE_NAME} scraper...")
        
        saved = 0
        page = 1
        
        with get_session() as session:
            while True:
                elapsed = time.time() - self.last_request
                if elapsed < self.request_interval:
                    time.sleep(self.request_interval - elapsed)
                self.last_request = time.time()
        
                try:
                    response = requests.get(self.API_URL, params={'page': page}, timeout=30)
                    
                    if response.status_code == 404:
                        break
                    
                    if response.status_code == 429:
                        self.logger.warning(f"Rate limited on page {page}, waiting 30s...")
                        time.sleep(30)
                        continue
                    
                    response.raise_for_status()
                    jobs = response.json().get('data', [])
                    
                    if not jobs:
                        break
                    
                    for job in jobs:
                        try:
                            raw_job = RawJob(
                                source=self.SOURCE_NAME,
                                external_id=job.get('slug'),
                                raw_data=job
                            )
                            session.add(raw_job)
                            session.flush()
                            saved += 1
                        except IntegrityError:
                            session.rollback()
                            continue
                    
                    self.logger.info(f"Page {page}: {len(jobs)} jobs, saved {saved} total")
                    page += 1
                    
                except Exception as e:
                    self.logger.error(f"Error on page {page}: {e}")
                    break
        
        self.logger.info(f"Finished: {saved} jobs saved")
        return saved


if __name__ == "__main__":
    scraper = ArbeitnowScraper()
    scraper.run()
