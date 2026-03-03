---

# 🏗️ WorkLense - Global IT Job Market Intelligence Pipeline

## Architecture Overview

┌────────────────────────────────────────────────────────────────────┐
│                        ORCHESTRATION LAYER                         │
│                    Apache Airflow (Scheduler)                      │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│   │  Scrape DAG  │  │ Transform DAG│  │ Analytics DAG│             │
│   │ (2x daily)   │  │  (continuous)│  │   (hourly)   │             │
│   └──────────────┘  └──────────────┘  └──────────────┘             │
└────────────────────────────┬───────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   SCRAPING   │    │ TRANSFORMATION│    │  ANALYTICS  │
│   LAYER      │    │    LAYER      │    │    LAYER    │
├──────────────┤    ├──────────────┤    ├──────────────┤
│ • Scrapy     │───▶│ • Deduper    │───▶│ •TimescaleDB│
│ • Playwright │    │ • Validator  │    │ •Materialized│
│ • Celery     │    │ • NLP Engine │    │   Views      │
│ • Proxies    │    │ • Enrichment │    │ • OLAP Cubes │
└──────┬───────┘    └──────┬───────┘    └──────────────┘
       │                   │
       ▼                   ▼
┌──────────────────────────────────────┐
│         STORAGE LAYER                │
├──────────────────────────────────────┤
│ PostgreSQL 16 + Extensions:          │
│  • TimescaleDB (time-series)         │
│  • PostGIS (geospatial)              │
│  • pg_trgm (fuzzy search)            │
│  • pg_stat_statements (monitoring)   │
├──────────────────────────────────────┤
│ Redis (cache + queue)                │
├──────────────────────────────────────┤
│ Meilisearch (full-text search)       │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│          API & VIZ LAYER             │
├──────────────────────────────────────┤
│ • FastAPI (REST API)                 │
│ • Grafana (dashboards)               │
│ • Metabase (ad-hoc analytics)        │
└──────────────────────────────────────┘

---

## 1. Data Sources Strategy (Free & Global)

### Tier 1: Free APIs (High Reliability)
SOURCES = {
    # Global aggregators
    'adzuna': {
        'api': 'https://api.adzuna.com/v1/api/jobs',
        'countries': ['us', 'gb', 'au', 'ca', 'de', 'fr', 'nl', 'br', 'in', 'sg'],
        'rate_limit': '60/min',
        'coverage': 'Excellent'
    },
    'arbeitnow': {
        'api': 'https://www.arbeitnow.com/api/job-board-api',
        'countries': ['EU-wide'],
        'rate_limit': 'Unlimited',
        'coverage': 'Good for Europe'
    },
    'remotive': {
        'api': 'https://remotive.com/api/remote-jobs',
        'countries': ['Global'],
        'rate_limit': 'Fair use',
        'coverage': 'Remote-first roles'
    },
    'findwork': {
        'api': 'https://findwork.dev/api/jobs',
        'countries': ['Global'],
        'rate_limit': '100/hour',
        'coverage': 'Tech-focused'
    },
    'himalayas': {
        'api': 'https://himalayas.app/api/jobs',
        'countries': ['Global'],
        'rate_limit': 'Fair use',
        'coverage': 'Remote tech jobs'
    },
    'reed_uk': {
        'api': 'https://www.reed.co.uk/api',
        'countries': ['GB'],
        'rate_limit': '300/hour',
        'coverage': 'UK-focused'
    },
    'usajobs': {
        'api': 'https://data.usajobs.gov/api',
        'countries': ['US'],
        'rate_limit': 'Generous',
        'coverage': 'US Gov IT jobs'
    }
}

### Tier 2: Scraping Targets (Rotating Strategy)
SCRAPING_TARGETS = {
    # Rotate daily to avoid detection
    'indeed': ['us', 'uk', 'de', 'ca', 'au', 'in', 'fr', 'nl', 'jp', 'br'],
    'linkedin': ['limited_scraping_with_caution'],  # Very aggressive anti-bot
    'weworkremotely': ['global'],
    'remoteok': ['global'],  # Also has API fallback
    'stackoverflow_jobs': ['alternative_needed'],  # Closed in 2022
    'glassdoor': ['us', 'uk'],  # Secondary priority
    'angellist': ['us', 'global_startups'],
    'eucareers': ['eu'],
    'seek_au': ['au', 'nz'],
    'jora': ['global']
}

### Geographic Coverage Strategy:
- *North America*: Indeed, LinkedIn, Dice (scrape), USAJOBS
- *Europe*: Arbeitnow, Reed, Indeed EU, EUcareers
- *Asia-Pacific*: Seek, Indeed APAC, Jora
- *Latin America*: Indeed BR, Adzuna BR
- *Remote-First*: Remotive, WeWorkRemotely, Himalayas, RemoteOK, Findwork
- *Startups*: AngelList, Y Combinator jobs

---

## 2. Database Schema Design

### Core Schema (PostgreSQL 16 + TimescaleDB)

-- ============================================
-- DIMENSION TABLES (SCD Type 2 where needed)
-- ============================================

CREATE TABLE companies (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL,  -- For deduplication
    website VARCHAR(500),
    industry VARCHAR(100),
    company_size VARCHAR(50),  -- '1-10', '11-50', '51-200', etc.
    headquarters_country VARCHAR(2),
    logo_url VARCHAR(500),
    description TEXT,
    glassdoor_rating DECIMAL(2,1),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_normalized_name UNIQUE(normalized_name)
);
CREATE INDEX idx_companies_name ON companies USING gin(name gin_trgm_ops);

-- ============================================

CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    city VARCHAR(100),
    state_province VARCHAR(100),
    country VARCHAR(2) NOT NULL,  -- ISO 3166-1 alpha-2
    country_name VARCHAR(100) NOT NULL,
    continent VARCHAR(50) NOT NULL,
    coordinates GEOGRAPHY(POINT, 4326),  -- PostGIS
    timezone VARCHAR(50),
    cost_of_living_index DECIMAL(5,2),  -- For PPP adjustments
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_locations_geo ON locations USING GIST(coordinates);
CREATE INDEX idx_locations_country ON locations(country);

-- ============================================

CREATE TABLE technologies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,  -- 'language', 'framework', 'database', 'cloud', 'tool'
    aliases TEXT[],  -- ['React', 'ReactJS', 'React.js']
    popularity_score INTEGER DEFAULT 0,  -- Updated periodically
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_technologies_category ON technologies(category);

-- ============================================

CREATE TABLE skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(20) NOT NULL,  -- 'hard', 'soft'
    category VARCHAR(50),  -- 'leadership', 'communication', 'technical'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- FACT TABLE (Hypertable for TimescaleDB)
-- ============================================

CREATE TABLE jobs (
    id BIGSERIAL NOT NULL,
    external_id VARCHAR(255) NOT NULL,  -- Source's job ID
    source VARCHAR(50) NOT NULL,  -- 'indeed_us', 'adzuna_uk', etc.
    
    -- Basic Info
    title VARCHAR(500) NOT NULL,
    normalized_title VARCHAR(200),  -- Standardized title
    description TEXT NOT NULL,
    url VARCHAR(1000) NOT NULL,
    
    -- Company
    company_id BIGINT REFERENCES companies(id),
    
    -- Location
    location_id INTEGER REFERENCES locations(id),
    is_remote BOOLEAN DEFAULT FALSE,
    is_hybrid BOOLEAN DEFAULT FALSE,
    
    -- Compensation
    salary_min DECIMAL(12,2),
    salary_max DECIMAL(12,2),
    salary_currency VARCHAR(3),  -- ISO 4217
    salary_period VARCHAR(20),  -- 'yearly', 'monthly', 'hourly'
    salary_ppp_adjusted DECIMAL(12,2),  -- Normalized to USD PPP
    
    -- Job Details
    employment_type VARCHAR(20),  -- 'full_time', 'part_time', 'contract', 'internship'
    seniority_level VARCHAR(20),  -- 'entry', 'mid', 'senior', 'lead', 'executive'
    experience_years_min INTEGER,
    experience_years_max INTEGER,
    education_required VARCHAR(50),  -- 'high_school', 'bachelor', 'master', 'phd'
    
    -- Extracted Features (NLP)
    benefits TEXT[],  -- ['health_insurance', 'remote_work', '401k', 'unlimited_pto']
    responsibilities TEXT[],
    requirements TEXT[],
    
    -- ML/Analytics
    description_sentiment DECIMAL(3,2),  -- -1 to 1
    automation_risk_score DECIMAL(3,2),  -- 0 to 1 (for Automation Vulnerability Index)
    quality_score INTEGER,  -- 0-100 based on description completeness
    
    -- Metadata
    posted_at TIMESTAMPTZ NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Deduplication
    content_hash VARCHAR(64) NOT NULL,  -- SHA256 of normalized content
    
    PRIMARY KEY (id, posted_at)  -- Composite for TimescaleDB partitioning
);

-- Convert to hypertable (TimescaleDB)
SELECT create_hypertable('jobs', 'posted_at', 
    chunk_time_interval => INTERVAL '1 week',
    if_not_exists => TRUE
);

-- Indexes for performance
CREATE INDEX idx_jobs_company ON jobs(company_id, posted_at DESC);
CREATE INDEX idx_jobs_location ON jobs(location_id, posted_at DESC);
CREATE INDEX idx_jobs_source ON jobs(source, posted_at DESC);
CREATE INDEX idx_jobs_active ON jobs(is_active, posted_at DESC) WHERE is_active = TRUE;
CREATE INDEX idx_jobs_hash ON jobs(content_hash);  -- Deduplication
CREATE INDEX idx_jobs_title ON jobs USING gin(normalized_title gin_trgm_ops);
CREATE INDEX idx_jobs_seniority ON jobs(seniority_level, posted_at DESC);

-- Retention policy: Drop chunks older than 1 year
SELECT add_retention_policy('jobs', INTERVAL '1 year');

-- ============================================
-- JUNCTION TABLES
-- ============================================

CREATE TABLE job_technologies (
    job_id BIGINT NOT NULL,
    job_posted_at TIMESTAMPTZ NOT NULL,
    technology_id INTEGER NOT NULL REFERENCES technologies(id),
    is_required BOOLEAN DEFAULT TRUE,
    proficiency_level VARCHAR(20),  -- 'beginner', 'intermediate', 'expert'
    PRIMARY KEY (job_id, job_posted_at, technology_id),
    FOREIGN KEY (job_id, job_posted_at) REFERENCES jobs(id, posted_at) ON DELETE CASCADE
);
CREATE INDEX idx_job_tech_tech ON job_technologies(technology_id, job_posted_at DESC);

-- ============================================

CREATE TABLE job_skills (
    job_id BIGINT NOT NULL,
    job_posted_at TIMESTAMPTZ NOT NULL,
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    is_required BOOLEAN DEFAULT TRUE,
    PRIMARY KEY (job_id, job_posted_at, skill_id),
    FOREIGN KEY (job_id, job_posted_at) REFERENCES jobs(id, posted_at) ON DELETE CASCADE
);
CREATE INDEX idx_job_skills_skill ON job_skills(skill_id, job_posted_at DESC);

-- ============================================
-- ANALYTICS MATERIALIZED VIEWS
-- ============================================

-- Daily aggregations for fast analytics
CREATE MATERIALIZED VIEW mv_daily_job_stats AS
SELECT 
    time_bucket('1 day', posted_at) AS day,
    source,
    location_id,
    company_id,
    seniority_level,
    COUNT(*) as job_count,
    AVG(salary_ppp_adjusted) as avg_salary,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY salary_ppp_adjusted) as median_salary,
    COUNT(*) FILTER (WHERE is_remote) as remote_count,
    AVG(automation_risk_score) as avg_automation_risk
FROM jobs
WHERE is_active = TRUE
GROUP BY 1, 2, 3, 4, 5;

CREATE UNIQUE INDEX ON mv_daily_job_stats (day, source, location_id, company_id, seniority_level);

-- Technology trends
CREATE MATERIALIZED VIEW mv_technology_trends AS
SELECT 
    time_bucket('1 week', j.posted_at) AS week,
    t.id as technology_id,
    t.name as technology_name,
    t.category,
    COUNT(DISTINCT jt.job_id) as job_count,
    AVG(j.salary_ppp_adjusted) as avg_salary,
    COUNT(DISTINCT jt.job_id) FILTER (WHERE jt.is_required) as required_count
FROM job_technologies jt
JOIN technologies t ON jt.technology_id = t.id
JOIN jobs j ON jt.job_id = j.id AND jt.job_posted_at = j.posted_at
WHERE j.is_active = TRUE
GROUP BY 1, 2, 3, 4;

CREATE UNIQUE INDEX ON mv_technology_trends (week, technology_id);

-- Refresh policy (automatically refresh every hour)
-- This would be managed by Airflow in practice

---

## 3. NLP Pipeline (RTX 4060 Optimized)

### Model Stack:
nlp_pipeline:
  preprocessing:
    tool: spaCy
    model: en_core_web_lg
    tasks:
      - sentence_segmentation
      - tokenization
      - named_entity_recognition (ORG, GPE, MONEY)
      - POS tagging
    
  entity_extraction:
    technology_extraction:
      method: hybrid
      components:
        - regex_patterns  # Fast pre-filter
        - custom_ner_model  # Fine-tuned spaCy NER
        - keyword_matching  # Against technologies table
        
    skill_extraction:
      tool: skillNer  # Open-source library
      fallback: custom_patterns
      
    salary_extraction:
      tool: regex + NER
      normalization: convert_to_usd_ppp
      
  semantic_understanding:
    model: llama-3.1-8b-instruct (quantized 4-bit)
    runtime: llama.cpp / ollama
    vram_usage: ~6GB
    tasks:
      - seniority_classification
      - job_type_classification
      - responsibility_extraction
      - requirement_extraction
      - benefits_extraction
      - sentiment_analysis
    batch_size: 4
    inference_time: ~2-3s per job
    
  quality_scoring:
    method: rule_based
    factors:
      - description_length
      - structured_data_completeness
      - contact_info_presence
      - salary_transparency

### NLP Processing Flow:
# Pseudo-code for NLP pipeline
def process_job_description(raw_job):
    # Stage 1: Fast extraction (spaCy)
    doc = nlp(raw_job['description'])
    
    extracted = {
        'technologies': extract_technologies(doc),  # ~10ms
        'skills': extract_skills(doc),  # ~10ms
        'salary': extract_salary(doc),  # ~5ms
        'location': extract_location(doc),  # ~5ms
        'entities': extract_entities(doc)  # ~10ms
    }
    
    # Stage 2: LLM enrichment (batched)
    llm_prompt = f"""
    Analyze this IT job posting and extract:
    1. Seniority level (entry/mid/senior/lead/executive)
    2. Employment type (full_time/part_time/contract/internship)
    3. Required years of experience (min-max)
    4. Education requirement
    5. Top 5 responsibilities
    6. Top 5 requirements
    7. Benefits offered
    8. Remote work policy
    9. Automation risk (0-1 scale)
    10. Overall sentiment (-1 to 1)
    
    Job: {raw_job['title']} at {raw_job['company']}
    Description: {raw_job['description'][:1500]}...
    
    Return JSON only.
    """
    
    llm_output = llm_inference(llm_prompt)  # Batched, ~2-3s
    
    return {**extracted, **llm_output}

---

## 4. Docker Compose Architecture

version: '3.9'

services:
  # =================
  # ORCHESTRATION
  # =================
  airflow-postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow
    volumes:
      - airflow-postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "airflow"]
      
  airflow-init:
    image: apache/airflow:2.8-python3.11
    depends_on:
      - airflow-postgres
      - redis
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
      - AIRFLOW__CELERY__RESULT_BACKEND=db+postgresql://airflow:airflow@airflow-postgres/airflow
    command: version

  airflow-webserver:
    image: apache/airflow:2.8-python3.11
    depends_on:
      - airflow-postgres
      - redis
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
    ports:
      - "8080:8080"
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
      - ./airflow/plugins:/opt/airflow/plugins
    command: webserver

  airflow-scheduler:
    image: apache/airflow:2.8-python3.11
    depends_on:
      - airflow-postgres
      - redis
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
    command: scheduler

  airflow-worker:
    image: apache/airflow:2.8-python3.11
    depends_on:
      - airflow-postgres
      - redis
    environment:
      - AIRFLOW__CORE__EXECUTOR=CeleryExecutor
      - AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow
      - AIRFLOW__CELERY__BROKER_URL=redis://redis:6379/0
    volumes:
      - ./airflow/dags:/opt/airflow/dags
      - ./airflow/logs:/opt/airflow/logs
    command: celery worker
    deploy:
      replicas: 3  # Scale based on load

  # =================
  # DATA STORAGE
  # =================
  postgres:
    image: timescale/timescaledb:latest-pg16
    environment:
      POSTGRES_USER: worklense
      POSTGRES_PASSWORD: worklense
      POSTGRES_DB: worklense
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql
    command: postgres -c shared_preload_libraries=timescaledb,pg_stat_statements
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U worklense"]

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes

  meilisearch:
    image: getmeili/meilisearch:v1.6
    ports:
      - "7700:7700"
    volumes:
      - meilisearch-data:/meili_data
    environment:
      MEILI_ENV: production
      MEILI_MASTER_KEY: changeme

  # =================
  # NLP SERVICES
  # =================
  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama-models:/root/.ollama
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
    environment:
      - OLLAMA_HOST=0.0.0.0
    command: serve

  nlp-processor:
    build: ./services/nlp
    depends_on:
      - ollama
      - redis
    environment:
      - OLLAMA_URL=http://ollama:11434
      - REDIS_URL=redis://redis:6379/1
      - MODEL_NAME=llama3.1:8b
    volumes:
      - ./services/nlp:/app
    deploy:
      replicas: 2

  # =================
  # SCRAPING SERVICES
  # =================
  scraper-api:
    build: ./services/scraper
    depends_on:
      - redis
      - postgres
    environment:
      - DATABASE_URL=postgresql://worklense:worklense@postgres:5432/worklense
      - REDIS_URL=redis://redis:6379/2
      - PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
    volumes:
      - ./services/scraper:/app
      - playwright-cache:/ms-playwright
    deploy:
      replicas: 5  # Scale for parallel scraping

  # =================
  # API & ANALYTICS
  # =================
  api:
    build: ./services/api
    depends_on:
      - postgres
      - redis
      - meilisearch
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://worklense:worklense@postgres:5432/worklense
      - REDIS_URL=redis://redis:6379/3
      - MEILISEARCH_URL=http://meilisearch:7700
    volumes:
      - ./services/api:/app

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    depends_on:
      - postgres
    volumes:
      - grafana-data:/var/lib/grafana
      - ./monitoring/grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./monitoring/grafana/datasources:/etc/grafana/provisioning/datasources
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
      - GF_INSTALL_PLUGINS=grafana-worldmap-panel

  metabase:
    image: metabase/metabase:latest
    ports:
      - "3001:3000"
    depends_on:
      - postgres
    volumes:
      - metabase-data:/metabase-data
    environment:
      MB_DB_TYPE: postgres
      MB_DB_DBNAME: metabase
      MB_DB_PORT: 5432
      MB_DB_USER: worklense
      MB_DB_PASS: worklense
      MB_DB_HOST: postgres

volumes:
  airflow-postgres-data:
  postgres-data:
  redis-data:
  meilisearch-data:
  ollama-models:
  playwright-cache:
  grafana-data:
  metabase-data:

networks:
  default:
    name: worklense-network

---

## 5. Airflow DAG Structure

### Main DAGs:

# dag_scrape_jobs.py - Runs 2x daily
"""
scrape_global_jobs_dag
├── start
├── scrape_tier1_apis [parallel]
│   ├── scrape_adzuna_[us,uk,de,...]
│   ├── scrape_arbeitnow
│   ├── scrape_remotive
│   ├── scrape_findwork
│   └── scrape_himalayas
├── scrape_tier2_websites [parallel]
│   ├── scrape_indeed_[us,uk,...]
│   ├── scrape_weworkremotely
│   ├── scrape_remoteok
│   └── scrape_angellist
├── validate_raw_data
├── deduplicate_batch
└── trigger_transform_dag
"""

# dag_transform_jobs.py - Continuous (sensor-triggered)
"""
transform_jobs_dag
├── fetch_new_raw_jobs
├── clean_and_normalize
├── enrich_companies [external API lookups]
├── geocode_locations [PostGIS]
├── nlp_batch_processing [GPU]
│   ├── extract_technologies
│   ├── extract_skills
│   ├── classify_seniority
│   ├── extract_requirements
│   └── sentiment_analysis
├── calculate_derived_fields
│   ├── ppp_adjustment
│   ├── automation_risk
│   └── quality_score
├── load_to_warehouse
└── index_to_meilisearch
"""

# dag_analytics_refresh.py - Hourly
"""
analytics_refresh_dag
├── refresh_materialized_views
├── update_technology_popularity
├── calculate_location_quotients
├── update_company_rankings
└── generate_trend_reports
"""

# dag_maintenance.py - Daily at 3 AM
"""
maintenance_dag
├── vacuum_analyze_tables
├── rebuild_indexes
├── clean_expired_jobs
├── backup_database
└── generate_data_quality_report
"""

---

## 6. Project Structure

WorkLense/
├── docker-compose.yml
├── .env
├── README.md
│
├── airflow/
│   ├── dags/
│   │   ├── dag_scrape_jobs.py
│   │   ├── dag_transform_jobs.py
│   │   ├── dag_analytics_refresh.py
│   │   └── dag_maintenance.py
│   ├── plugins/
│   │   ├── operators/
│   │   └── sensors/
│   └── config/
│       └── airflow.cfg
│
├── services/
│   ├── scraper/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── scrapers/
│   │   │   ├── base_scraper.py
│   │   │   ├── adzuna_scraper.py
│   │   │   ├── indeed_scraper.py
│   │   │   └── ...
│   │   ├── parsers/
│   │   └── utils/
│   │
│   ├── nlp/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── models/
│   │   │   ├── technology_extractor.py
│   │   │   ├── skill_extractor.py
│   │   │   ├── llm_processor.py
│   │   │   └── sentiment_analyzer.py
│   │   └── utils/
│   │
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── jobs.py
│   │   │   ├── analytics.py
│   │   │   └── search.py
│   │   └── models/
│   │
│   └── transformer/
│       ├── deduplicator.py
│       ├── normalizer.py
│       ├── enricher.py
│       └── validator.py
│
├── db/
│   ├── init.sql
│   ├── migrations/
│   └── seeds/
│
├── monitoring/
│   ├── grafana/
│   │   ├── dashboards/
│   │   └── datasources/
│   └── prometheus/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
└── scripts/
    ├── setup.sh
    ├── seed_technologies.py
    └── benchmark.py

---

## 7. Analytics Implementation Examples

### Location Quotient Analysis:
-- Stored procedure for LQ calculation
CREATE OR REPLACE FUNCTION calculate_location_quotient(
    p_technology_id INT,
    p_location_id INT,
    p_start_date TIMESTAMPTZ,
    p_end_date TIMESTAMPTZ
) RETURNS DECIMAL AS $$
DECLARE
    local_jobs DECIMAL;
    total_local DECIMAL;
    national_jobs DECIMAL;
    total_national DECIMAL;
    lq DECIMAL;
BEGIN
    -- Local tech jobs / Total local jobs
    SELECT COUNT(*) INTO local_jobs
    FROM jobs j
    JOIN job_technologies jt ON j.id = jt.job_id
    WHERE j.location_id = p_location_id
      AND jt.technology_id = p_technology_id
      AND j.posted_at BETWEEN p_start_date AND p_end_date;
      
    SELECT COUNT(*) INTO total_local
    FROM jobs
    WHERE location_id = p_location_id
      AND posted_at BETWEEN p_start_date AND p_end_date;
    
    -- National tech jobs / Total national jobs
    SELECT COUNT(*) INTO national_jobs
    FROM jobs j
    JOIN job_technologies jt ON j.id = jt.job_id
    WHERE jt.technology_id = p_technology_id
      AND j.posted_at BETWEEN p_start_date AND p_end_date;
      
    SELECT COUNT(*) INTO total_national
    FROM jobs
    WHERE posted_at BETWEEN p_start_date AND p_end_date;
    
    -- LQ = (local_jobs / total_local) / (national_jobs / total_national)
    IF total_local > 0 AND total_national > 0 THEN
        lq := (local_jobs::DECIMAL / total_local) / (national_jobs::DECIMAL / total_national);
    ELSE
        lq := 0;
    END IF;
    
    RETURN lq;
END;
$$ LANGUAGE plpgsql;

### Time Series Forecasting (Python):
# In analytics DAG
from prophet import Prophet
import pandas as pd

def forecast_emerging_roles():
    # Fetch historical data
    query = """
    SELECT 
        DATE_TRUNC('week', posted_at) as ds,
        normalized_title,
        COUNT(*) as y
    FROM jobs
    WHERE posted_at >= NOW() - INTERVAL '1 year'
    GROUP BY 1, 2
    HAVING COUNT(*) > 100  -- Min threshold
    ORDER BY 1, 2
    """
    
    df = pd.read_sql(query, engine)
    
    forecasts = {}
    for title in df['normalized_title'].unique():
        title_df = df[df['normalized_title'] == title][['ds', 'y']]
        
        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=False,
            changepoint_prior_scale=0.05
        )
        model.fit(title_df)
        
        future = model.make_future_dataframe(periods=26, freq='W')  # 6 months
        forecast = model.predict(future)
        
        # Calculate growth rate
        current_trend = forecast['yhat'].iloc[-26:].mean()
        past_trend = forecast['yhat'].iloc[-52:-26].mean()
        growth_rate = (current_trend - past_trend) / past_trend * 100
        
        forecasts[title] = {
            'growth_rate': growth_rate,
            'forecast': forecast
        }
    
    # Identify emerging roles (>50% growth)
    emerging = {k: v for k, v in forecasts.items() if v['growth_rate'] > 50}
    
    return emerging

---

## Next Steps & Questions:

### *To move forward, I need your input on:*

1. *Should I start implementing this?* If yes, switch to Agent mode and I'll:
   - Create the entire folder structure
   - Implement the database schema
   - Build the Docker Compose setup
   - Create starter scrapers for 3-5 sources
   - Set up basic Airflow DAGs

2. *Priority order*: What should we build first?
   - Option A: Database + basic scraper + one data source (MVP)
   - Option B: Full infrastructure first, then iterate on scrapers
   - Option C: Your preference?

3. *Technology substitutions*: Any tools you want to swap?
   - TimescaleDB vs vanilla Postgres?
   - Meilisearch vs Elasticsearch?
   - Ollama vs llama.cpp for LLM inference?

4. *Analytics depth*: The analyses you listed are *PhD-level quantitative research*. Should we:
   - Build infrastructure first, analytics later?
   - Focus on simpler metrics initially (job count trends, salary averages)?
   - Go full academic rigor from day 1?