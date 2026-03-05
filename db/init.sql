-- ============================================
-- WorkLense Database Schema
-- ============================================

CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin; 

-- ============================================
-- DIMENSION TABLES
-- ============================================

CREATE TABLE companies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    normalized_name VARCHAR(255) NOT NULL UNIQUE,
    website VARCHAR(500),
    industry VARCHAR(100),
    company_size VARCHAR(50),
    headquarters_country CHAR(2),
    description TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_companies_normalized ON companies(normalized_name);
CREATE INDEX idx_companies_name_trgm ON companies USING gin(name gin_trgm_ops);

-- ============================================

CREATE TABLE locations (
    id SERIAL PRIMARY KEY,
    city VARCHAR(100),
    state_province VARCHAR(100),
    country CHAR(2) NOT NULL,
    country_name VARCHAR(100) NOT NULL,
    continent VARCHAR(50) NOT NULL,
    latitude DECIMAL(9,6),
    longitude DECIMAL(9,6),
    timezone VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(city, state_province, country)
);

CREATE INDEX idx_locations_country ON locations(country);
CREATE INDEX idx_locations_continent ON locations(continent);

-- ============================================

CREATE TABLE technologies (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    aliases TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_technologies_category ON technologies(category);
CREATE INDEX idx_technologies_name ON technologies(lower(name));

-- ============================================

CREATE TABLE skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    type VARCHAR(20) NOT NULL CHECK (type IN ('hard', 'soft')),
    category VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skills_type ON skills(type);

-- ============================================
-- RAW DATA TABLE
-- ============================================

CREATE TABLE raw_jobs (
    id BIGSERIAL PRIMARY KEY,
    source VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    raw_data JSONB NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    
    UNIQUE(source, external_id)
);

CREATE INDEX idx_raw_jobs_source ON raw_jobs(source, fetched_at DESC);
CREATE INDEX idx_raw_jobs_processed ON raw_jobs(processed) WHERE processed = FALSE;
CREATE INDEX idx_raw_jobs_data_gin ON raw_jobs USING gin(raw_data);

-- ============================================
-- FACT TABLE - Jobs
-- ============================================

CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    external_id VARCHAR(255) NOT NULL,
    source VARCHAR(50) NOT NULL,
    
    title VARCHAR(500) NOT NULL,
    normalized_title VARCHAR(200),
    description TEXT NOT NULL,
    url VARCHAR(1000) NOT NULL,
    
    company_id INTEGER REFERENCES companies(id) ON DELETE SET NULL,
    location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
    
    is_remote BOOLEAN DEFAULT FALSE,
    is_hybrid BOOLEAN DEFAULT FALSE,
    
    salary_min DECIMAL(12,2),
    salary_max DECIMAL(12,2),
    salary_currency CHAR(3),
    salary_period VARCHAR(20),
    
    employment_type VARCHAR(20),
    seniority_level VARCHAR(20),
    experience_years_min INTEGER,
    experience_years_max INTEGER,
    education_required VARCHAR(50),
    
    benefits TEXT[],
    
    posted_at TIMESTAMPTZ NOT NULL,
    scraped_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT TRUE,
    last_seen_at TIMESTAMPTZ DEFAULT NOW(),
    
    content_hash CHAR(64) NOT NULL,
    raw_job_id BIGINT REFERENCES raw_jobs(id) ON DELETE SET NULL,
    
    UNIQUE(source, external_id),
    CHECK (salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max)
);

CREATE INDEX idx_jobs_company ON jobs(company_id) WHERE is_active = TRUE;
CREATE INDEX idx_jobs_location ON jobs(location_id) WHERE is_active = TRUE;
CREATE INDEX idx_jobs_posted_at ON jobs(posted_at DESC) WHERE is_active = TRUE;
CREATE INDEX idx_jobs_source ON jobs(source, posted_at DESC);
CREATE INDEX idx_jobs_content_hash ON jobs(content_hash);
CREATE INDEX idx_jobs_title_trgm ON jobs USING gin(normalized_title gin_trgm_ops);
CREATE INDEX idx_jobs_seniority ON jobs(seniority_level) WHERE is_active = TRUE;
CREATE INDEX idx_jobs_remote ON jobs(is_remote) WHERE is_remote = TRUE;
CREATE INDEX idx_jobs_raw_job ON jobs(raw_job_id);

-- ============================================
-- JUNCTION TABLES
-- ============================================

CREATE TABLE job_technologies (
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    technology_id INTEGER NOT NULL REFERENCES technologies(id) ON DELETE CASCADE,
    is_required BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (job_id, technology_id)
);

CREATE INDEX idx_job_tech_tech ON job_technologies(technology_id);
CREATE INDEX idx_job_tech_job ON job_technologies(job_id);

-- ============================================

CREATE TABLE job_skills (
    job_id BIGINT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id INTEGER NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
    is_required BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (job_id, skill_id)
);

CREATE INDEX idx_job_skills_skill ON job_skills(skill_id);
CREATE INDEX idx_job_skills_job ON job_skills(job_id);

-- ============================================
-- SEED DATA - Common Technologies
-- ============================================

INSERT INTO technologies (name, category, aliases) VALUES
-- Languages
('Python', 'language', ARRAY['python', 'py']),
('JavaScript', 'language', ARRAY['javascript', 'js', 'ecmascript']),
('TypeScript', 'language', ARRAY['typescript', 'ts']),
('Java', 'language', ARRAY['java']),
('Go', 'language', ARRAY['go', 'golang']),
('Rust', 'language', ARRAY['rust']),
('C++', 'language', ARRAY['c++', 'cpp', 'cplusplus']),
('C#', 'language', ARRAY['c#', 'csharp', 'c sharp']),
('PHP', 'language', ARRAY['php']),
('Ruby', 'language', ARRAY['ruby']),
('Swift', 'language', ARRAY['swift']),
('Kotlin', 'language', ARRAY['kotlin']),

-- Frameworks
('React', 'framework', ARRAY['react', 'reactjs', 'react.js']),
('Angular', 'framework', ARRAY['angular', 'angularjs']),
('Vue', 'framework', ARRAY['vue', 'vuejs', 'vue.js']),
('Django', 'framework', ARRAY['django']),
('Flask', 'framework', ARRAY['flask']),
('FastAPI', 'framework', ARRAY['fastapi']),
('Spring', 'framework', ARRAY['spring', 'spring boot', 'springboot']),
('Node.js', 'framework', ARRAY['node', 'nodejs', 'node.js']),
('Express', 'framework', ARRAY['express', 'expressjs', 'express.js']),
('Next.js', 'framework', ARRAY['next', 'nextjs', 'next.js']),

-- Databases
('PostgreSQL', 'database', ARRAY['postgres', 'postgresql', 'psql']),
('MySQL', 'database', ARRAY['mysql']),
('MongoDB', 'database', ARRAY['mongodb', 'mongo']),
('Redis', 'database', ARRAY['redis']),
('Elasticsearch', 'database', ARRAY['elasticsearch', 'elastic']),
('Oracle', 'database', ARRAY['oracle', 'oracle db']),
('SQL Server', 'database', ARRAY['sql server', 'mssql', 'microsoft sql']),

-- Cloud
('AWS', 'cloud', ARRAY['aws', 'amazon web services']),
('Azure', 'cloud', ARRAY['azure', 'microsoft azure']),
('GCP', 'cloud', ARRAY['gcp', 'google cloud', 'google cloud platform']),
('Docker', 'cloud', ARRAY['docker']),
('Kubernetes', 'cloud', ARRAY['kubernetes', 'k8s']),

-- Tools
('Git', 'tool', ARRAY['git']),
('Jenkins', 'tool', ARRAY['jenkins']),
('GitLab', 'tool', ARRAY['gitlab']),
('Jira', 'tool', ARRAY['jira'])
ON CONFLICT (name) DO NOTHING;

-- ============================================
-- FUNCTIONS & TRIGGERS
-- ============================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================
-- VIEWS
-- ============================================

CREATE VIEW v_active_jobs AS
SELECT 
    j.id,
    j.title,
    j.description,
    j.url,
    c.name as company_name,
    l.city,
    l.country,
    j.is_remote,
    j.salary_min,
    j.salary_max,
    j.salary_currency,
    j.seniority_level,
    j.posted_at,
    j.source
FROM jobs j
LEFT JOIN companies c ON j.company_id = c.id
LEFT JOIN locations l ON j.location_id = l.id
WHERE j.is_active = TRUE;

CREATE VIEW v_tech_demand AS
SELECT 
    t.name as technology,
    t.category,
    COUNT(DISTINCT jt.job_id) as job_count
FROM technologies t
LEFT JOIN job_technologies jt ON t.id = jt.technology_id
LEFT JOIN jobs j ON jt.job_id = j.id
WHERE j.is_active = TRUE
GROUP BY t.id, t.name, t.category
ORDER BY job_count DESC;