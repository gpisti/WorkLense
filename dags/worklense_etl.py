"""
WorkLense ETL DAG
- Scrapes 3 job sources in parallel (Arbeitnow, Adzuna, Findwork)
- Transforms all unprocessed raw jobs after scrapers finish
Schedule is configurable via AIRFLOW_SCHEDULE env var (default: @daily).
"""
import os
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator

PROJECT_DIR = "/opt/airflow/project"

SCHEDULE = os.environ.get("AIRFLOW_SCHEDULE", "@daily")

DEFAULT_ARGS = {
    "owner": "worklense",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}

with DAG(
    dag_id="worklense_etl",
    default_args=DEFAULT_ARGS,
    description="Scrape IT job boards and transform into analytics-ready data",
    schedule=SCHEDULE,
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["worklense", "etl"],
) as dag:

    scrape_arbeitnow = BashOperator(
        task_id="scrape_arbeitnow",
        bash_command=f"cd {PROJECT_DIR} && python -m src.scrapers.arbeitnow_scraper",
    )

    scrape_adzuna = BashOperator(
        task_id="scrape_adzuna",
        bash_command=f"cd {PROJECT_DIR} && python -m src.scrapers.adzuna_scraper",
    )

    scrape_findwork = BashOperator(
        task_id="scrape_findwork",
        bash_command=f"cd {PROJECT_DIR} && python -m src.scrapers.findwork_scraper",
    )

    transform_jobs = BashOperator(
        task_id="transform_jobs",
        bash_command=f"cd {PROJECT_DIR} && python -m src.transformers.job_transformer",
        execution_timeout=timedelta(hours=4),
    )

    [scrape_arbeitnow, scrape_adzuna, scrape_findwork] >> transform_jobs
