import requests
import time
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger
from src.database.models import RawJob, get_session
from src.config.settings import settings


class FindworkScraper:

    IT_KEYWORDS = [
        # General
        'software', 'backend', 'frontend', 'fullstack', 'devops', 'programmer', 'developer', 'engineer', 'architect', 'cto', 'lead developer', 'principal engineer',
        # Data, AI & ML
        'data engineer', 'machine learning', 'ai', 'artificial intelligence', 'deep learning', 'nlp', 'natural language processing',
        'computer vision', 'data science', 'data scientist', 'data analyst', 'big data', 'cloud', 'cloud engineer', 'cloud architect',
        'aws', 'azure', 'gcp', 'google cloud', 'amazon web services', 'mlops', 'data ops', 'data platform', 'ai engineer', 'ai researcher',
        # Security
        'security', 'cybersecurity', 'information security', 'secops', 'soc', 'infosec', 'network security', 'application security',
        'security engineer', 'security analyst', 'pentester', 'penetration tester', 'devsecops', 'ethical hacker', 'malware', 'vulnerability',
        # Operations & Infrastructure
        'sre', 'site reliability', 'site reliability engineer', 'reliability engineer', 'infrastructure', 'cloud infrastructure', 'network', 'systems administrator', 'sysadmin', 'linux admin', 'windows admin', 'network engineer', 'network admin', 'platform engineer', 'operations engineer',
        # Mobile
        'mobile', 'android', 'ios', 'react native', 'flutter', 'kotlin', 'swift', 'mobile app', 'mobile developer', 'mobile engineer',
        # Web & Frontend/Backend
        'web developer', 'web engineer', 'web designer', 'frontend developer', 'frontend engineer', 'backend developer', 'backend engineer', 'fullstack developer', 'javascript', 'typescript', 'react', 'vue', 'angular', 'svelte', 'nextjs', 'nuxt', 'node', 'nodejs', 'express', 'tailwind', 'html', 'css', 'sass', 'less',
        # Languages & Frameworks
        'java', 'python', 'golang', 'go', 'c#', '.net', 'dotnet', 'c++', 'cpp', 'php', 'ruby', 'rails', 'scala', 'rust', 'perl', 'objective-c', 'elixir', 'clojure', 'haskell', 'erlang', 'matlab', 'r', 'typescript', 'shell', 'bash', 'dart', 'groovy', 'delphi', 'assembly', 'fortran', 'cobol', 'f#',
        # Blockchain & Crypto
        'blockchain', 'crypto', 'solidity', 'web3', 'defi', 'cryptocurrency', 'nft', 'dapp', 'smart contract',
        # QA & Test
        'qa', 'quality assurance', 'test automation', 'automation engineer', 'tester', 'testing', 'manual testing', 'test engineer', 'qa engineer', 'sdet', 'test lead', 'regression testing',
        # Product, Agile, Project, Design
        'product manager', 'scrum master', 'agile', 'project manager', 'project lead', 'product owner', 'delivery manager',
        'ux', 'ui', 'designer', 'product designer', 'ux designer', 'ui designer', 'ux/ui', 'interaction designer', 'user experience', 'user interface', 'visual designer', 'graphic designer',
        # Embedded, Firmware, Hardware
        'embedded', 'firmware', 'hardware', 'iot', 'internet of things', 'robotics', 'electronics', 'microcontroller', 'fpga', 'embedded software', 'rtl', 'pcb', 'asic',
        # Gaming
        'game developer', 'game engineer', 'unity', 'unreal', 'gamedev', 'game designer', 'level designer', 'game programmer',
        # Database, DBA, Data Engineering
        'database', 'dba', 'sql', 'nosql', 'postgres', 'postgresql', 'mysql', 'mongodb', 'cassandra', 'oracle', 'mariadb', 'sql server', 'firebase', 'redshift', 'snowflake', 'data warehouse', 'data lake',
        # APIs, Microservices, Cloud Native, Containers
        'api', 'apis', 'rest', 'restful', 'graphql', 'microservices', 'serverless', 'docker', 'kubernetes', 'container', 'containers', 'openshift', 'helm', 'terraform', 'cloudformation', 'ansible', 'configuration management',
        # AI Frameworks & Tools
        'pytorch', 'tensorflow', 'keras', 'sklearn', 'scikit-learn', 'huggingface', 'openai', 'langchain', 'stable diffusion', 'llm', 'chatgpt',
        # Dev Tools, DevOps, CI/CD
        'ci', 'cd', 'ci/cd', 'jenkins', 'github actions', 'gitlab ci', 'travis', 'circleci', 'git', 'version control', 'sentry', 'monitoring', 'logging', 'prometheus', 'grafana', 'splunk', 'elk', 'elasticsearch', 'logstash', 'kibana',
        # Misc/Other
        'etl', 'business intelligence', 'bi', 'tableau', 'powerbi', 'looker', 'superset', 'superset', 'airflow', 'dagster', 'great expectations', 'dbt', 'data pipeline',
        'api gateway', 'load balancer', 'reverse proxy', 'nginx', 'apache', 'apache spark', 'apache kafka', 'rabbitmq', 'hadoop', 'bigquery', 'data mining', 'data visualization'
    ]

    def __init__(self):
        self.logger = logger
        self.API_URL = "https://findwork.dev/api/jobs/"
        self.SOURCE_NAME = "findwork"
        self.request_interval = 1.1
        self.last_request = 0
        self.api_key = settings.FINDWORK_API_KEY

        if not self.api_key:
            raise ValueError("FINDWORK_API_KEY must be set in settings")

    def run(self) -> int:
        self.logger.info(f"Starting {self.SOURCE_NAME} scraper for {len(self.IT_KEYWORDS)} keyword groups...")

        total_saved = 0

        for keyword in self.IT_KEYWORDS:
            try:
                keyword_saved = self._fetch_keyword(keyword)
                total_saved += keyword_saved
                self.logger.info(f"Keyword '{keyword}': {keyword_saved} jobs saved")
            except Exception as e:
                self.logger.error(f"Error fetching keyword '{keyword}': {e}")

        self.logger.info(f"Finished: {total_saved} total jobs saved")
        return total_saved

    def _fetch_keyword(self, keyword: str) -> int:
        saved = 0
        url = self.API_URL

        with get_session() as session:
            while url:
                elapsed = time.time() - self.last_request
                if elapsed < self.request_interval:
                    time.sleep(self.request_interval - elapsed)
                self.last_request = time.time()

                try:
                    response = requests.get(
                        url,
                        headers={"Authorization": f"Token {self.api_key}"},
                        params={"search": keyword} if url == self.API_URL else None,
                        timeout=30
                    )

                    if response.status_code == 429:
                        self.logger.warning(f"Rate limited on '{keyword}', waiting 30...")
                        time.sleep(30)
                        continue

                    response.raise_for_status()
                    data = response.json()
                    jobs = data.get('results', [])

                    if not jobs:
                        break

                    for job in jobs:
                        try:
                            raw_job = RawJob(
                                source=self.SOURCE_NAME,
                                external_id=str(job.get('id', '')),
                                raw_data=job
                            )
                            session.add(raw_job)
                            session.flush()
                            saved += 1
                        except IntegrityError:
                            session.rollback()
                            continue

                    self.logger.info(f"Keyword '{keyword}' – {len(jobs)} jobs fetched, {saved} saved so far")

                    url = data.get('next')

                except Exception as e:
                    self.logger.error(f"Error fetching '{keyword}': {e}")
                    break

        return saved


if __name__ == "__main__":
    scraper = FindworkScraper()
    scraper.run()

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
