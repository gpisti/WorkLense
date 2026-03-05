# WorkLense -- IT Job Market Intelligence Pipeline

End-to-end data pipeline that scrapes global IT job postings from multiple
sources, enriches them with LLM-powered NLP extraction, and exposes
15+ interactive analytics visualizations through a Streamlit dashboard.

---

## Architecture

```
                     ┌──────────────────────────┐
                     │     Apache Airflow        │
                     │   (daily ETL schedule)    │
                     └────────────┬─────────────┘
                                  │
               ┌──────────────────┼──────────────────┐
               ▼                  ▼                  ▼
        ┌─────────────┐  ┌──────────────┐  ┌──────────────┐
        │  Arbeitnow   │  │   Adzuna     │  │  FindWork    │
        │  Scraper     │  │  Scraper     │  │  Scraper     │
        └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
               │                 │                  │
               └────────┬───────┘──────────────────┘
                        ▼
               ┌──────────────────┐
               │   raw_jobs       │  (JSONB staging)
               │   PostgreSQL 16  │
               └────────┬────────┘
                        ▼
              ┌──────────────────────┐
              │  JobTransformer      │
              │  ┌────────────────┐  │
              │  │ Source Parsers │  │  Arbeitnow / Adzuna / FindWork
              │  └────────┬───────┘  │
              │           ▼          │
              │  ┌────────────────┐  │
              │  │ LLM Extractor │  │  Ollama (Qwen 2.5 7B / Mistral 7B)
              │  └────────┬───────┘  │
              │           ▼          │
              │  ┌────────────────┐  │
              │  │ Company Norm.  │  │  Fuzzy + embeddings + LLM verify
              │  │ Tech / Skill   │  │
              │  │ Education Norm.│  │
              │  └────────────────┘  │
              └──────────┬───────────┘
                         ▼
     ┌──────────────────────────────────────┐
     │         PostgreSQL 16                │
     │  jobs, companies, locations,         │
     │  technologies, skills,               │
     │  job_technologies, job_skills        │
     └──────────────────┬───────────────────┘
                        ▼
              ┌──────────────────────┐
              │  Streamlit Dashboard │
              │  15 interactive      │
              │  Plotly charts       │
              └──────────────────────┘
```

---

## Data Sources

| Source     | API                                     | Coverage                         | Rate Limit   |
|------------|-----------------------------------------|----------------------------------|--------------|
| Arbeitnow  | `https://www.arbeitnow.com/api/job-board-api` | EU-wide, remote-friendly   | Unlimited    |
| Adzuna     | `https://api.adzuna.com/v1/api/jobs`    | 19 countries (US, GB, DE, ...)   | 60/min       |
| FindWork   | `https://findwork.dev/api/jobs`         | Global, tech-focused             | 100/hour     |

All three scrapers run in parallel within the Airflow DAG and store raw JSON
into `raw_jobs` (JSONB column) before any transformation.

---

## Tech Stack

| Layer           | Technology                                                                 |
|-----------------|----------------------------------------------------------------------------|
| Orchestration   | Apache Airflow 2.10 (LocalExecutor, Dockerized)                           |
| Database        | PostgreSQL 16 with `pg_trgm` and `btree_gin` extensions                   |
| ORM             | SQLAlchemy 2.0                                                             |
| LLM             | Ollama -- Qwen 2.5 7B Instruct (extraction), Mistral 7B (verification)    |
| Embeddings      | sentence-transformers (`all-MiniLM-L6-v2`)                                 |
| Fuzzy matching  | RapidFuzz                                                                  |
| Dashboard       | Streamlit + Plotly + NetworkX                                              |
| Language        | Python 3.10                                                                |

---

## Project Structure

```
WorkLense/
├── dags/
│   └── worklense_etl.py          # Airflow DAG (scrape x3 parallel -> transform)
├── db/
│   └── init.sql                  # Full schema, indexes, seed data, views
├── src/
│   ├── config/
│   │   └── settings.py           # Centralized env-based configuration
│   ├── database/
│   │   └── models.py             # SQLAlchemy ORM models + session manager
│   ├── scrapers/
│   │   ├── arbeitnow_scraper.py  # Arbeitnow API scraper
│   │   ├── adzuna_scraper.py     # Adzuna API scraper (19 countries, 8 threads)
│   │   └── findwork_scraper.py   # FindWork API scraper (keyword-based)
│   ├── transformers/
│   │   ├── job_transformer.py    # Main ETL transform: parse -> extract -> normalize -> load
│   │   └── parsers/
│   │       ├── arbeitnow_parser.py
│   │       ├── adzuna_parser.py
│   │       └── findwork_parser.py
│   ├── nlp/
│   │   ├── job_extractor.py      # LLM-based structured data extraction (Ollama)
│   │   ├── company_normalizer.py # 3-tier matching: exact -> fuzzy -> embedding+LLM
│   │   ├── technology_extractor.py
│   │   └── skill_resolver.py
│   └── utils/
│       ├── logger.py             # Loguru-based logging
│       └── date_utils.py
├── scripts/
│   ├── run_dashboard.py          # Launch Streamlit dashboard
│   └── dump_findwork.py          # Debug utility: dump FindWork API JSON
├── streamlit_app.py              # Dashboard: 15 interactive charts
├── docker-compose.yaml           # PostgreSQL + Airflow (4 services)
├── airflow.Dockerfile            # Custom Airflow image with ETL deps
├── requirements.txt              # Full local development dependencies
├── requirements-etl.txt          # Minimal deps for Airflow container
└── .env                          # API keys, DB URL, Ollama config
```

---

## Database Schema

Star-schema design with dimension tables, a staging table, a fact table, and
junction tables for many-to-many technology/skill relationships.

**Dimension tables:** `companies`, `locations`, `technologies`, `skills`

**Staging:** `raw_jobs` -- stores raw JSONB from each scraper, tracks processing
status and errors.

**Fact table:** `jobs` -- normalized job postings with salary, seniority,
education, remote/hybrid flags, content-hash deduplication, and foreign keys
into all dimension tables.

**Junction tables:** `job_technologies`, `job_skills`

**Key indexes:** trigram GIN on company names and job titles for fuzzy search,
partial indexes on active jobs, composite indexes for common query patterns.

The schema is initialized automatically via `db/init.sql` on first
`docker compose up` and includes seed data for 40+ common technologies.

---

## NLP Pipeline

Each raw job goes through a multi-stage enrichment process:

1. **Source-specific parsing** -- Dedicated parsers for each API source extract
   structured fields (title, location, salary, remote flags) from the raw JSON.

2. **LLM extraction** (Ollama / Qwen 2.5 7B Instruct) -- A single prompt
   extracts technologies, skills, experience requirements, education level,
   benefits, seniority, salary, and employment type as structured JSON.
   Includes retry logic with up to 3 attempts.

3. **Company normalization** -- Three-tier deduplication:
   - Exact match on normalized name (lowercase, stripped suffixes like Inc/GmbH/Ltd)
   - Substring match verified by LLM (Mistral 7B)
   - Fuzzy match (RapidFuzz token_sort_ratio >= 65) verified by
     sentence-transformer embeddings (cosine >= 0.80) or LLM

4. **Education normalization** -- Free-text education values are mapped to a
   canonical set (`phd`, `masters`, `bachelors`, `associate`, `high_school`,
   `none_required`) using alias matching.

5. **Technology and skill resolution** -- Extracted names are fuzzy-matched
   against the database catalog; new entries are auto-created.

6. **Content deduplication** -- SHA-256 hash of `title + company + description`
   prevents duplicate job entries.

---

## Dashboard

The Streamlit dashboard (`streamlit_app.py`) provides 15 interactive Plotly
visualizations on a single scrollable dark-themed page:

1. **Skill Combo Heatmap** -- Co-occurrence matrix of top skills
2. **Technology Trends** -- Multi-line chart of monthly job counts per technology
3. **Skill Network Graph** -- Force-directed graph of skill co-occurrences
4. **Skill Salary Premium** -- Horizontal bar chart of salary premiums by skill
5. **Remote Premium Map** -- Choropleth + grouped bar (remote vs on-site salary)
6. **Experience ROI** -- Dual-axis chart: salary vs marginal ROI per experience year
7. **Hiring Velocity Bubbles** -- Posting lifespan vs frequency by company/industry
8. **Industry-Seniority Mix** -- Stacked 100% bar chart
9. **Company Tech Radar** -- Radar or stacked bar of tech stack per company
10. **Salary Range Explorer** -- Horizontal range bars ordered by spread ratio
11. **City Job Map** -- Interactive dot map colored by dominant tech category
12. **Education vs Salary** -- Grouped bar chart with median reference line
13. **Unicorn Jobs** -- Rare skill combo table with sparklines
14. **Source Quality** -- Conditional-format table of data completeness per source
15. **Zombie Jobs** -- Donut chart + Gantt-style timeline of stale postings

---

## Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.10+ (for local development and dashboard)
- Ollama running locally with `qwen2.5:7b-instruct` and `mistral:7b` models
- API keys for Adzuna and FindWork (free tier)

### 1. Environment variables

Copy and fill in your API keys in `.env`:

```
ADZUNA_API_KEY=your_key
ADZUNA_APP_ID=your_app_id
FINDWORK_API_KEY=your_key
DATABASE_URL=postgresql://worklense:worklense@localhost:5432/worklense
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=mistral:7b
OLLAMA_TECH_MODEL=qwen2.5:7b-instruct
AIRFLOW_SCHEDULE=@daily
```

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** (port 5432) -- main data store, auto-initialized with schema
- **Airflow PostgreSQL** (port 5433) -- Airflow metadata store
- **Airflow Webserver** (port 8080) -- DAG management UI (admin/admin)
- **Airflow Scheduler** -- executes the ETL DAG on schedule

### 3. Install Python dependencies (local development)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Pull Ollama models

```bash
ollama pull qwen2.5:7b-instruct
ollama pull mistral:7b
```

### 5. Run the ETL manually (optional)

```bash
# Scrape all sources
python -m src.scrapers.arbeitnow_scraper
python -m src.scrapers.adzuna_scraper
python -m src.scrapers.findwork_scraper

# Transform raw data
python -m src.transformers.job_transformer
```

Or trigger it from the Airflow UI at `http://localhost:8080`.

### 6. Launch the dashboard

```bash
python scripts/run_dashboard.py
```

The dashboard is available at `http://localhost:8501`.

---

## Airflow DAG

The single `worklense_etl` DAG runs on a configurable schedule (default:
`@daily`) and executes four tasks:

```
scrape_arbeitnow ─┐
scrape_adzuna    ─┼──► transform_jobs
scrape_findwork  ─┘
```

The three scraper tasks run in parallel. Once all succeed, the transformer
processes all unprocessed `raw_jobs` rows through the full NLP pipeline.

---

## License

Private project.
