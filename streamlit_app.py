"""
WorkLense – IT Job Market Analytics Dashboard
Run: streamlit run streamlit_app.py
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import networkx as nx
from sqlalchemy import text

from src.database.models import engine

# ---------------------------------------------------------------------------
# Theme & palette
# ---------------------------------------------------------------------------
PALETTE = [
    "#6366f1", "#22d3ee", "#34d399", "#fbbf24", "#f87171",
    "#a78bfa", "#fb923c", "#38bdf8", "#4ade80", "#e879f9",
]

_DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", size=13, color="#e2e8f0"),
    title_font=dict(size=16, color="#f1f5f9"),
    margin=dict(l=60, r=30, t=52, b=50),
    legend=dict(
        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
        font=dict(size=11), bgcolor="rgba(0,0,0,0)",
    ),
    hovermode="x unified",
    hoverlabel=dict(bgcolor="#1e293b", font_size=12, font_color="#f1f5f9"),
)


def _fig(*, height: int = 500, **kw) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**{**_DARK_LAYOUT, "height": height, **kw})
    return fig


def _apply(fig: go.Figure, *, height: int | None = None, **kw) -> go.Figure:
    merged = {**_DARK_LAYOUT, **kw}
    if height is not None:
        merged["height"] = height
    fig.update_layout(**merged)
    return fig


def _section(title: str, description: str):
    """Render a section header with a short description underneath."""
    st.markdown(
        f'<h2 style="margin-bottom:0;padding-top:2.2rem">{title}</h2>'
        f'<p style="color:#94a3b8;margin-top:0.2rem;margin-bottom:1rem;font-size:0.92rem">'
        f'{description}</p>',
        unsafe_allow_html=True,
    )


def _tech_slope(df: pd.DataFrame) -> pd.Series:
    slopes = {}
    for tech, grp in df.groupby("technology"):
        grp = grp.sort_values("month")
        if len(grp) < 2:
            slopes[tech] = 0
            continue
        slopes[tech] = (grp["job_count"].iloc[-1] - grp["job_count"].iloc[0]) / max(1, len(grp) - 1)
    return pd.Series(slopes)


# ---------------------------------------------------------------------------
# SQL constants
# ---------------------------------------------------------------------------
KPI_SQL = """
SELECT
    (SELECT COUNT(*) FROM jobs)          AS total_jobs,
    (SELECT COUNT(*) FROM companies)     AS total_companies,
    (SELECT COUNT(*) FROM technologies)  AS total_techs,
    (SELECT COUNT(*) FROM skills)        AS total_skills,
    (SELECT COUNT(*) FROM locations)     AS total_locations,
    (SELECT COUNT(*) FROM raw_jobs)      AS total_raw,
    (SELECT COUNT(*) FROM raw_jobs WHERE processed) AS processed_raw,
    (SELECT COUNT(DISTINCT source) FROM raw_jobs)   AS sources
"""

SKILL_COMBO_SQL = """
SELECT
    s1.name AS skill_a,
    s2.name AS skill_b,
    COUNT(*) AS co_occurrence_count
FROM job_skills js1
JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
JOIN skills s1 ON js1.skill_id = s1.id
JOIN skills s2 ON js2.skill_id = s2.id
GROUP BY s1.name, s2.name
ORDER BY co_occurrence_count DESC
LIMIT 500;
"""

TECH_TREND_SQL = """
SELECT
    t.name AS technology,
    t.category,
    DATE_TRUNC('month', j.posted_at) AS month,
    COUNT(*) AS job_count
FROM job_technologies jt
JOIN technologies t ON jt.technology_id = t.id
JOIN jobs j ON jt.job_id = j.id
WHERE j.posted_at >= NOW() - INTERVAL '12 months'
GROUP BY t.name, t.category, month
ORDER BY t.name, month;
"""

SKILL_EDGES_SQL = """
WITH skill_pairs AS (
    SELECT js1.skill_id AS sid1, js2.skill_id AS sid2, COUNT(*) AS pair_count
    FROM job_skills js1
    JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
    GROUP BY js1.skill_id, js2.skill_id
),
skill_total AS (
    SELECT sid1 AS skill_id, SUM(pair_count) AS total FROM skill_pairs GROUP BY sid1
    UNION ALL
    SELECT sid2, SUM(pair_count) FROM skill_pairs GROUP BY sid2
),
top_skills AS (
    SELECT skill_id FROM (
        SELECT skill_id, SUM(total) AS t FROM skill_total GROUP BY skill_id ORDER BY t DESC LIMIT %d
    ) x
)
SELECT s1.name AS skill_a, s2.name AS skill_b, sp.pair_count
FROM skill_pairs sp
JOIN top_skills ts1 ON sp.sid1 = ts1.skill_id
JOIN top_skills ts2 ON sp.sid2 = ts2.skill_id
JOIN skills s1 ON sp.sid1 = s1.id
JOIN skills s2 ON sp.sid2 = s2.id
ORDER BY sp.pair_count DESC;
"""

SKILL_PREMIUM_SQL = """
WITH base AS (
    SELECT
        COALESCE(seniority_level, 'Unknown') AS seniority_level,
        AVG((salary_min + salary_max) / 2.0) AS base_avg_salary
    FROM jobs
    WHERE salary_min IS NOT NULL AND salary_max IS NOT NULL
    GROUP BY COALESCE(seniority_level, 'Unknown')
),
skill_salary AS (
    SELECT
        s.name AS skill_name,
        COALESCE(j.seniority_level, 'Unknown') AS seniority_level,
        AVG((j.salary_min + j.salary_max) / 2.0) AS avg_salary_with_skill,
        COUNT(*) AS job_count
    FROM job_skills js
    JOIN skills s ON js.skill_id = s.id
    JOIN jobs j ON js.job_id = j.id
    WHERE j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
    GROUP BY s.name, COALESCE(j.seniority_level, 'Unknown')
    HAVING COUNT(*) >= 3
)
SELECT
    ss.skill_name,
    ss.seniority_level,
    ROUND(ss.avg_salary_with_skill, 0)::numeric          AS avg_salary_with_skill,
    ROUND(b.base_avg_salary, 0)::numeric                 AS base_avg_salary,
    ROUND(ss.avg_salary_with_skill - b.base_avg_salary, 0)::numeric AS premium_usd,
    ROUND((ss.avg_salary_with_skill - b.base_avg_salary)
          / NULLIF(b.base_avg_salary, 0) * 100, 2)::numeric         AS premium_pct,
    ss.job_count
FROM skill_salary ss
JOIN base b ON ss.seniority_level = b.seniority_level
ORDER BY premium_usd DESC
LIMIT 200;
"""

REMOTE_PREMIUM_SQL = """
SELECT
    COALESCE(c.industry, 'Unknown') AS industry,
    l.country,
    ROUND(AVG(CASE WHEN j.is_remote THEN (j.salary_min + j.salary_max) / 2.0 END), 0)::numeric
        AS avg_remote_salary,
    ROUND(AVG(CASE WHEN NOT j.is_remote THEN (j.salary_min + j.salary_max) / 2.0 END), 0)::numeric
        AS avg_onsite_salary,
    ROUND(
        AVG(CASE WHEN j.is_remote     THEN (j.salary_min + j.salary_max) / 2.0 END) -
        AVG(CASE WHEN NOT j.is_remote THEN (j.salary_min + j.salary_max) / 2.0 END),
    0)::numeric AS remote_premium_usd,
    COUNT(*) AS total_jobs
FROM jobs j
JOIN companies c  ON j.company_id  = c.id
JOIN locations l  ON j.location_id = l.id
WHERE j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
GROUP BY COALESCE(c.industry, 'Unknown'), l.country
HAVING COUNT(*) >= 3
ORDER BY remote_premium_usd DESC;
"""

EXPERIENCE_SALARY_SQL = """
SELECT
    experience_years_min,
    experience_years_max,
    ROUND(AVG((salary_min + salary_max) / 2.0), 0)::numeric  AS avg_salary,
    COUNT(*)::int                                           AS job_count,
    ROUND(
        AVG((salary_min + salary_max) / 2.0) -
        LAG(AVG((salary_min + salary_max) / 2.0))
            OVER (ORDER BY experience_years_min),
    0)::numeric AS salary_jump_vs_prev,
    ROUND(
        (AVG((salary_min + salary_max) / 2.0) -
         LAG(AVG((salary_min + salary_max) / 2.0)) OVER (ORDER BY experience_years_min))
        / NULLIF(experience_years_min -
                 LAG(experience_years_min) OVER (ORDER BY experience_years_min), 0),
    0)::numeric AS salary_per_extra_year
FROM jobs
WHERE salary_min IS NOT NULL
  AND salary_max IS NOT NULL
  AND experience_years_min IS NOT NULL
GROUP BY experience_years_min, experience_years_max
ORDER BY experience_years_min;
"""

POSTING_LIFESPAN_SQL = """
SELECT
    c.name     AS company,
    COALESCE(c.industry, 'Unknown') AS industry,
    COUNT(*)   AS total_postings_6m,
    COUNT(CASE WHEN j.is_active THEN 1 END)  AS currently_active,
    ROUND(AVG(
        EXTRACT(EPOCH FROM (
            COALESCE(j.expires_at, j.last_seen_at, j.posted_at + INTERVAL '30 days') - j.posted_at
        )) / 86400.0
    ), 1)::numeric AS avg_posting_lifespan_days,
    ROUND(
        COUNT(*) / NULLIF(
            EXTRACT(DAY FROM NOW() - MIN(j.posted_at)) / 30.0, 0
        ), 2
    )::numeric AS postings_per_month
FROM jobs j
JOIN companies c ON j.company_id = c.id
WHERE j.posted_at >= NOW() - INTERVAL '6 months'
GROUP BY c.id, c.name, c.industry
HAVING COUNT(*) >= 3
ORDER BY postings_per_month DESC
LIMIT 80;
"""

INDUSTRY_SENIORITY_SQL = """
SELECT
    COALESCE(c.industry, 'Other') AS industry,
    COALESCE(j.seniority_level, 'Unknown') AS seniority_level,
    COUNT(*) AS job_count,
    ROUND(
        COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (PARTITION BY COALESCE(c.industry, 'Other')),
    2)::numeric AS pct_within_industry,
    ROUND(AVG((j.salary_min + j.salary_max) / 2.0), 0)::numeric AS avg_salary
FROM jobs j
JOIN companies c ON j.company_id = c.id
GROUP BY COALESCE(c.industry, 'Other'), COALESCE(j.seniority_level, 'Unknown')
ORDER BY COALESCE(c.industry, 'Other'), job_count DESC;
"""

COMPANY_TECH_SQL = """
SELECT
    c.name           AS company,
    t.category       AS tech_category,
    STRING_AGG(DISTINCT t.name, ', ' ORDER BY t.name) AS technologies,
    COUNT(DISTINCT j.id)  AS jobs_requiring_this_category,
    COUNT(DISTINCT t.id)  AS distinct_techs_in_category,
    ROUND(
        COUNT(DISTINCT j.id) * 100.0
        / SUM(COUNT(DISTINCT j.id)) OVER (PARTITION BY c.name),
    2)::numeric AS pct_of_company_jobs
FROM companies c
JOIN jobs j           ON j.company_id        = c.id
JOIN job_technologies jt ON jt.job_id        = j.id
JOIN technologies t   ON jt.technology_id    = t.id
GROUP BY c.name, t.category
ORDER BY c.name, jobs_requiring_this_category DESC;
"""

SALARY_RANGE_SQL = """
SELECT
    j.normalized_title,
    COALESCE(c.industry, 'Unknown') AS industry,
    ROUND(AVG(j.salary_min), 0)::numeric                             AS avg_min,
    ROUND(AVG(j.salary_max), 0)::numeric                             AS avg_max,
    ROUND(AVG(j.salary_max - j.salary_min), 0)::numeric             AS avg_range,
    ROUND(STDDEV(j.salary_max - j.salary_min), 0)::numeric          AS stddev_range,
    ROUND(AVG(
        (j.salary_max - j.salary_min)
        / NULLIF((j.salary_min + j.salary_max) / 2.0, 0)
    ), 3)::numeric AS range_ratio,
    COUNT(*) AS job_count
FROM jobs j
JOIN companies c ON j.company_id = c.id
WHERE j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
GROUP BY j.normalized_title, COALESCE(c.industry, 'Unknown')
HAVING COUNT(*) >= 2
ORDER BY range_ratio DESC
LIMIT 40;
"""

CITY_TECH_MAP_SQL = """
SELECT
    l.city,
    l.country,
    l.continent,
    t.name           AS technology,
    t.category,
    COUNT(*)         AS job_count,
    AVG(l.latitude)  AS lat,
    AVG(l.longitude) AS lng,
    ROUND(
        COUNT(*) * 100.0
        / SUM(COUNT(*)) OVER (PARTITION BY t.name),
    2)::numeric AS city_share_pct
FROM jobs j
JOIN locations l      ON j.location_id    = l.id
JOIN job_technologies jt ON jt.job_id     = j.id
JOIN technologies t   ON jt.technology_id = t.id
WHERE l.city IS NOT NULL
  AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
GROUP BY l.city, l.country, l.continent, t.name, t.category
HAVING COUNT(*) >= 2
ORDER BY job_count DESC;
"""

EDUCATION_SALARY_SQL = """
WITH edu_norm AS (
    SELECT
        j.id,
        j.salary_min,
        j.salary_max,
        j.company_id,
        CASE
            WHEN j.education_required IN ('phd','masters','bachelors','associate','high_school','none_required')
                THEN j.education_required
            WHEN LOWER(j.education_required) LIKE '%%phd%%'
                OR LOWER(j.education_required) LIKE '%%ph.d%%'
                OR LOWER(j.education_required) LIKE '%%doktor%%'
                OR LOWER(j.education_required) LIKE '%%doctorate%%'
                THEN 'phd'
            WHEN LOWER(j.education_required) LIKE '%%master%%'
                OR LOWER(j.education_required) LIKE '%%msc%%'
                OR LOWER(j.education_required) LIKE '%%m.sc%%'
                OR LOWER(j.education_required) LIKE '%%mba%%'
                OR LOWER(j.education_required) LIKE '%%postgrad%%'
                THEN 'masters'
            WHEN LOWER(j.education_required) LIKE '%%bachelor%%'
                OR LOWER(j.education_required) LIKE '%%bsc%%'
                OR LOWER(j.education_required) LIKE '%%b.sc%%'
                OR LOWER(j.education_required) LIKE '%%degree%%'
                OR LOWER(j.education_required) LIKE '%%university%%'
                OR LOWER(j.education_required) LIKE '%%college%%'
                OR LOWER(j.education_required) LIKE '%%undergrad%%'
                THEN 'bachelors'
            WHEN LOWER(j.education_required) LIKE '%%associate%%'
                OR LOWER(j.education_required) LIKE '%%vocational%%'
                THEN 'associate'
            WHEN LOWER(j.education_required) LIKE '%%high school%%'
                OR LOWER(j.education_required) LIKE '%%secondary%%'
                OR LOWER(j.education_required) LIKE '%%abitur%%'
                THEN 'high_school'
            WHEN LOWER(j.education_required) LIKE '%%not required%%'
                OR LOWER(j.education_required) LIKE '%%no formal%%'
                OR LOWER(j.education_required) LIKE '%%no degree%%'
                OR LOWER(j.education_required) LIKE '%%none%%'
                THEN 'none_required'
            ELSE 'other'
        END AS education_level
    FROM jobs j
    WHERE j.salary_min IS NOT NULL AND j.salary_max IS NOT NULL
      AND j.education_required IS NOT NULL
)
SELECT
    e.education_level AS education_required,
    COALESCE(c.industry, 'Unknown') AS industry,
    COUNT(*)::int AS job_count,
    ROUND(AVG((e.salary_min + e.salary_max) / 2.0), 0)::numeric AS avg_salary,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY (e.salary_min + e.salary_max) / 2.0)::numeric, 0) AS median_salary,
    ROUND(PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY (e.salary_min + e.salary_max) / 2.0)::numeric, 0) AS p75_salary,
    ROUND(MAX((e.salary_min + e.salary_max) / 2.0), 0)::numeric AS max_salary
FROM edu_norm e
JOIN companies c ON e.company_id = c.id
GROUP BY e.education_level, COALESCE(c.industry, 'Unknown')
ORDER BY median_salary DESC;
"""

UNICORN_JOBS_SQL = """
WITH pair_rarity AS (
    SELECT
        js1.skill_id AS skill_a,
        js2.skill_id AS skill_b,
        COUNT(*)     AS pair_count
    FROM job_skills js1
    JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
    GROUP BY js1.skill_id, js2.skill_id
),
job_rarity AS (
    SELECT
        js1.job_id,
        AVG(pr.pair_count)  AS avg_pair_freq,
        MIN(pr.pair_count)  AS rarest_pair,
        COUNT(DISTINCT js1.skill_id) AS n_skills
    FROM job_skills js1
    JOIN job_skills js2 ON js1.job_id = js2.job_id AND js1.skill_id < js2.skill_id
    JOIN pair_rarity pr ON pr.skill_a = js1.skill_id AND pr.skill_b = js2.skill_id
    GROUP BY js1.job_id
    HAVING COUNT(DISTINCT js1.skill_id) >= 4
)
SELECT
    j.title,
    c.name        AS company,
    j.seniority_level,
    jr.n_skills,
    ROUND(jr.avg_pair_freq, 1)::numeric AS avg_pair_frequency,
    jr.rarest_pair,
    RANK() OVER (ORDER BY jr.avg_pair_freq ASC)::int AS unicorn_rank
FROM job_rarity jr
JOIN jobs j      ON jr.job_id = j.id
JOIN companies c ON j.company_id = c.id
ORDER BY avg_pair_frequency ASC
LIMIT 30;
"""

SOURCE_QUALITY_SQL = """
SELECT
    rj.source,
    COUNT(*)::int                                                                  AS total_raw,
    COUNT(CASE WHEN rj.processed THEN 1 END)::int                                  AS processed,
    COUNT(CASE WHEN rj.error_message IS NOT NULL THEN 1 END)::int                  AS errors,
    ROUND(COUNT(CASE WHEN rj.error_message IS NOT NULL THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 2)::numeric AS error_rate_pct,
    ROUND(COUNT(CASE WHEN j.salary_min IS NULL THEN 1 END) * 100.0 / NULLIF(COUNT(j.id), 0), 2)::numeric   AS missing_salary_pct,
    ROUND(COUNT(CASE WHEN j.location_id IS NULL THEN 1 END) * 100.0 / NULLIF(COUNT(j.id), 0), 2)::numeric AS missing_location_pct,
    ROUND(COUNT(CASE WHEN j.seniority_level IS NULL THEN 1 END) * 100.0 / NULLIF(COUNT(j.id), 0), 2)::numeric AS missing_seniority_pct,
    ROUND(AVG(EXTRACT(EPOCH FROM (rj.processed_at - rj.fetched_at)) / 60), 2)::numeric AS avg_processing_min
FROM raw_jobs rj
LEFT JOIN jobs j ON j.raw_job_id = rj.id
GROUP BY rj.source
ORDER BY error_rate_pct DESC NULLS LAST;
"""

ZOMBIE_JOBS_SQL = """
SELECT
    c.name       AS company,
    COALESCE(c.industry, 'Unknown') AS industry,
    j.title,
    j.seniority_level,
    j.posted_at,
    j.last_seen_at,
    j.expires_at,
    EXTRACT(DAY FROM (j.last_seen_at - j.posted_at))::INT AS days_alive,
    CASE
        WHEN j.expires_at IS NULL AND j.is_active AND j.posted_at < NOW() - INTERVAL '60 days' THEN 'no_expiry_ever_set'
        WHEN j.expires_at < NOW() AND j.is_active THEN 'expired_but_still_active'
        WHEN EXTRACT(DAY FROM (j.last_seen_at - j.posted_at)) > 90 THEN 'long_running_90d+'
        ELSE 'normal'
    END AS zombie_type,
    ROUND((j.salary_min + j.salary_max) / 2.0, 0)::numeric AS midpoint_salary
FROM jobs j
JOIN companies c ON j.company_id = c.id
WHERE
    (j.expires_at IS NULL AND j.is_active AND j.posted_at < NOW() - INTERVAL '60 days')
    OR (j.expires_at < NOW() AND j.is_active)
    OR (EXTRACT(DAY FROM (j.last_seen_at - j.posted_at)) > 90)
ORDER BY days_alive DESC;
"""

ISO2_TO_ISO3 = {
    "us": "USA", "gb": "GBR", "au": "AUS", "de": "DEU", "fr": "FRA", "ca": "CAN",
    "nl": "NLD", "pl": "POL", "at": "AUT", "es": "ESP", "it": "ITA", "be": "BEL",
    "in": "IND", "sg": "SGP", "nz": "NZL", "br": "BRA", "mx": "MEX", "za": "ZAF",
    "ie": "IRL", "ch": "CHE", "pt": "PRT", "se": "SWE", "no": "NOR", "dk": "DNK",
    "fi": "FIN", "jp": "JPN", "kr": "KOR", "cn": "CHN", "hk": "HKG", "tw": "TWN",
    "ro": "ROU", "cz": "CZE", "hu": "HUN", "gr": "GRC", "il": "ISR", "ae": "ARE",
    "ru": "RUS", "ua": "UKR", "tr": "TUR", "ar": "ARG", "cl": "CHL", "co": "COL",
    "bg": "BGR", "hr": "HRV", "sk": "SVK", "si": "SVN", "lt": "LTU", "lv": "LVA",
    "ee": "EST", "lu": "LUX", "mt": "MLT", "cy": "CYP", "th": "THA", "ph": "PHL",
    "my": "MYS", "id": "IDN", "vn": "VNM", "pk": "PAK", "bd": "BGD", "ng": "NGA",
    "ke": "KEN", "eg": "EGY", "sa": "SAU", "qa": "QAT", "kw": "KWT", "bh": "BHR",
}

_DARK_GEO = dict(
    bgcolor="rgba(0,0,0,0)",
    showframe=False,
    showcoastlines=True,
    coastlinecolor="#334155",
    showland=True,
    landcolor="#1e293b",
    showocean=True,
    oceancolor="#0f172a",
    showcountries=True,
    countrycolor="#334155",
    showlakes=False,
)

# ═══════════════════════════════════════════════════════════════════════════
# Page config & global CSS
# ═══════════════════════════════════════════════════════════════════════════
st.set_page_config(page_title="WorkLense", layout="wide")

st.markdown("""<style>
    div[data-testid="stAppViewBlockContainer"] {
        max-width: 1200px;
        margin: 0 auto;
        padding-top: 1rem;
    }
    .kpi-row {
        display: flex;
        gap: 0.75rem;
        flex-wrap: wrap;
        margin-bottom: 1.5rem;
    }
    .kpi-card {
        flex: 1;
        min-width: 130px;
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1rem 1.1rem;
        text-align: center;
    }
    .kpi-card .value {
        font-size: 1.65rem;
        font-weight: 700;
        color: #f1f5f9;
        line-height: 1.2;
    }
    .kpi-card .label {
        font-size: 0.78rem;
        color: #94a3b8;
        margin-top: 0.2rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    .section-divider {
        border: none;
        border-top: 1px solid #1e293b;
        margin: 2.5rem 0 0.5rem 0;
    }
</style>""", unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# Header
# ═══════════════════════════════════════════════════════════════════════════
st.markdown(
    '<h1 style="margin-bottom:0.15rem">WorkLense</h1>'
    '<p style="color:#64748b;margin-top:0;font-size:0.95rem">'
    'IT allaspiaci adatok vizualizacioja – technologiak, skillek, berek, trendek'
    '</p>',
    unsafe_allow_html=True,
)

# ═══════════════════════════════════════════════════════════════════════════
# KPI row
# ═══════════════════════════════════════════════════════════════════════════
try:
    with engine.connect() as conn:
        kpi = pd.read_sql(text(KPI_SQL), conn).iloc[0]
    cards = [
        (f"{int(kpi['total_jobs']):,}", "Feldolgozott allas"),
        (f"{int(kpi['total_companies']):,}", "Ceg"),
        (f"{int(kpi['total_techs']):,}", "Technologia"),
        (f"{int(kpi['total_skills']):,}", "Skill"),
        (f"{int(kpi['total_locations']):,}", "Helyszin"),
        (f"{int(kpi['sources']):,}", "Adatforras"),
        (f"{int(kpi['processed_raw']):,} / {int(kpi['total_raw']):,}", "Feldolgozva / Nyers"),
    ]
    html = '<div class="kpi-row">'
    for value, label in cards:
        html += f'<div class="kpi-card"><div class="value">{value}</div><div class="label">{label}</div></div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)
except Exception as e:
    st.error(f"KPI lekerdezesi hiba: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# 1. Skill Co-occurrence Heatmap
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Skill co-occurrence",
    "Mely skillek jelennek meg egyutt leggyakrabban ugyanabban az allasban? "
    "A matrixban a szinintenzitas a kozos elofordulasok szamat mutatja – "
    "igy kiderul, milyen valos tech stackek leteznek a piacon.",
)
top_skills = st.slider("Top N skill", 10, 30, 15, key="heatmap_n")
try:
    with engine.connect() as conn:
        df = pd.read_sql(text(SKILL_COMBO_SQL), conn)
    if df.empty:
        st.info("Nincs skill-par adat.")
    else:
        total_per_skill: dict[str, int] = {}
        for _, row in df.iterrows():
            c = row["co_occurrence_count"]
            for s in (row["skill_a"], row["skill_b"]):
                total_per_skill[s] = total_per_skill.get(s, 0) + c
        skills = sorted(total_per_skill, key=lambda s: -total_per_skill[s])[:top_skills]
        top_set = set(skills)
        matrix = pd.DataFrame(0, index=skills, columns=skills)
        for _, row in df.iterrows():
            a, b, c = row["skill_a"], row["skill_b"], row["co_occurrence_count"]
            if a in top_set and b in top_set:
                matrix.loc[a, b] = c
                matrix.loc[b, a] = c
        fig = go.Figure(
            go.Heatmap(
                z=matrix.values, x=matrix.columns.tolist(), y=matrix.index.tolist(),
                colorscale=[[0, "#0f172a"], [0.25, "#1e3a5f"], [0.5, "#2563eb"], [0.75, "#38bdf8"], [1, "#67e8f9"]],
                hoverongaps=False, text=matrix.values,
                texttemplate="%{text}", textfont=dict(size=10, color="#94a3b8"),
            )
        )
        n = len(skills)
        _apply(fig, height=420 + n * 16,
               xaxis=dict(tickangle=-45, tickfont=dict(size=11)),
               yaxis=dict(tickfont=dict(size=11)),
               margin=dict(l=120, r=60, t=20, b=120))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df.head(100), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 2. Technology Trends
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Technologia trendek",
    "Az utolso 12 honap havi bontasban: hogyan valtozik az egyes technologiak iranti kereslet? "
    "A vastagabb, kiemeltek vonalak a legnagyobb novekedest mutato tech-ek – "
    "ezek a felszallo agban levo technologiak.",
)
try:
    with engine.connect() as conn:
        df_trend = pd.read_sql(text(TECH_TREND_SQL), conn)
    if df_trend.empty:
        st.info("Nincs technologia/honap adat.")
    else:
        df_trend["month"] = pd.to_datetime(df_trend["month"])
        categories = sorted(df_trend["category"].dropna().unique().tolist())
        selected_cats = st.multiselect(
            "Kategoria szuro", options=categories, default=categories, key="tech_trend_cat",
        )
        if selected_cats:
            df_trend = df_trend[df_trend["category"].isin(selected_cats)]
        col1, col2 = st.columns(2)
        with col1:
            top_n_tech = st.slider("Top N technologia", 5, 50, 15, key="tech_topn")
        with col2:
            top_slope_n = st.slider("Kiemelt vonalak (novekedes)", 0, 15, 5, key="tech_trend_slope")

        tech_totals = df_trend.groupby("technology")["job_count"].sum()
        top_techs = tech_totals.nlargest(top_n_tech).index.tolist()
        df_plot = df_trend[df_trend["technology"].isin(top_techs)]
        slopes = _tech_slope(df_plot)
        highlight_techs = set(slopes.sort_values(ascending=False).head(top_slope_n).index) if top_slope_n else set()

        fig = _fig(height=520)
        for tech in df_plot["technology"].unique():
            grp = df_plot[df_plot["technology"] == tech].sort_values("month")
            hl = tech in highlight_techs
            fig.add_trace(go.Scatter(
                x=grp["month"], y=grp["job_count"], name=tech,
                mode="lines+markers" if hl else "lines",
                line=dict(width=3 if hl else 1.2),
                marker=dict(size=5) if hl else None,
                opacity=1.0 if hl else 0.35,
            ))
        _apply(fig, xaxis_title="Honap", yaxis_title="Job count",
               margin=dict(l=60, r=30, t=20, b=50),
               legend=dict(orientation="v", yanchor="top", y=1, xanchor="left", x=1.02, font=dict(size=10)))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Meredekseg rangsor"):
            st.dataframe(slopes.sort_values(ascending=False).reset_index(name="slope").head(20), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 3. Skill Network
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Skill halozat",
    "Force-directed graf, ahol minden csomopont egy skill (merete = hany allasban fordul elo), "
    "az elek vastagsaga pedig azt mutatja, milyen gyakran jelennek meg egyutt. "
    "A kozeppontban levo, sok kapcsolattal rendelkezo skillek a 'gateway' skillek – "
    "ezek ismerete nyitja meg a legtobb allaslehetoseget.",
)
top_n_net = st.slider("Top N skill a halozatban", 15, 35, 22, key="net_top_n")
try:
    with engine.connect() as conn:
        df_edges = pd.read_sql(text(SKILL_EDGES_SQL % top_n_net), conn)
    if df_edges.empty:
        st.info("Nincs skill el adat.")
    else:
        skill_names = sorted(set(df_edges["skill_a"]) | set(df_edges["skill_b"]))
        params = {f"n{i}": n for i, n in enumerate(skill_names)}
        placeholders = ", ".join(f":n{i}" for i in range(len(skill_names)))
        node_sql = text(
            "SELECT s.name, COUNT(DISTINCT js.job_id) AS appears_in_n_jobs "
            "FROM skills s JOIN job_skills js ON js.skill_id = s.id "
            "WHERE s.name IN (" + placeholders + ") GROUP BY s.name"
        )
        with engine.connect() as conn:
            df_nodes = pd.read_sql(node_sql, conn, params=params)
        jobs_per_skill = df_nodes.set_index("name")["appears_in_n_jobs"].to_dict()
        for s in skill_names:
            jobs_per_skill.setdefault(s, 1)

        G = nx.Graph()
        for _, row in df_edges.iterrows():
            G.add_edge(row["skill_a"], row["skill_b"], weight=row["pair_count"])
        pos = nx.spring_layout(G, k=1.8, iterations=60, seed=42, weight="weight")

        fig = _fig(height=650)
        for _, row in df_edges.iterrows():
            x0, y0 = pos[row["skill_a"]]
            x1, y1 = pos[row["skill_b"]]
            w = row["pair_count"]
            width = max(0.4, min(4, 0.3 + w / 50))
            fig.add_trace(go.Scatter(
                x=[x0, x1, None], y=[y0, y1, None], mode="lines",
                line=dict(width=width, color=f"rgba(99,102,241,{min(0.6, 0.15 + w / 200)})"),
                hoverinfo="none", showlegend=False,
            ))
        sizes = [max(10, min(40, 6 + jobs_per_skill[n] // 4)) for n in skill_names]
        node_x = [pos[n][0] for n in skill_names]
        node_y = [pos[n][1] for n in skill_names]
        fig.add_trace(go.Scatter(
            x=node_x, y=node_y, mode="markers+text",
            text=skill_names, textposition="top center",
            textfont=dict(size=10, color="#e2e8f0"),
            marker=dict(size=sizes, color="#6366f1", line=dict(width=1.5, color="#a5b4fc")),
            hovertext=[f"<b>{n}</b><br>{jobs_per_skill[n]} jobs" for n in skill_names],
            hoverinfo="text", showlegend=False,
        ))
        _apply(fig,
               xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
               yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
               margin=dict(l=20, r=20, t=20, b=20))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Elek"):
            st.dataframe(df_edges.head(80), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 4. Skill Premium
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Skill premium",
    "Mennyivel tobb (vagy kevesebb) bert fizet a piac azokert az allasokert, amelyek egy adott "
    "skillet igenyelnek, az azonos seniority szint atlagahoz kepest? "
    "Zold = pozitiv premium, piros = az adott skill atlag alatti bert jelent.",
)
try:
    with engine.connect() as conn:
        df_prem = pd.read_sql(text(SKILL_PREMIUM_SQL), conn)
    if df_prem.empty:
        st.info("Nincs skill premium adat (beradat hianyzik).")
    else:
        seniorities = sorted(df_prem["seniority_level"].dropna().unique().tolist())
        col1, col2 = st.columns(2)
        with col1:
            selected_sr = st.multiselect(
                "Seniority szuro", options=seniorities, default=seniorities, key="premium_seniority",
            )
        with col2:
            top_n_prem = st.slider("Top N skill", 10, 50, 25, key="premium_top_n")
        if selected_sr:
            df_prem = df_prem[df_prem["seniority_level"].isin(selected_sr)]
        df_prem = df_prem.nlargest(top_n_prem, "premium_usd").sort_values("premium_usd", ascending=True).copy()
        df_prem["label"] = df_prem["skill_name"] + " (" + df_prem["seniority_level"].astype(str) + ")"
        colors = ["#34d399" if float(x) >= 0 else "#f87171" for x in df_prem["premium_usd"]]

        fig = go.Figure(go.Bar(
            x=df_prem["premium_usd"], y=df_prem["label"], orientation="h",
            marker_color=colors, text=df_prem["premium_usd"],
            texttemplate="%{text:,.0f}", textposition="outside", textfont=dict(size=11),
            customdata=df_prem[["seniority_level", "premium_pct", "job_count"]].values,
            hovertemplate="%{y}<br>Premium: %{x:,.0f}<br>Seniority: %{customdata[0]}<br>Premium %%: %{customdata[1]}%%<br>Jobs: %{customdata[2]}<extra></extra>",
        ))
        fig.add_vline(x=0, line_dash="dot", line_color="#475569")
        _apply(fig, height=400 + len(df_prem) * 16,
               xaxis_title="Premium (salary diff.)", yaxis_title="",
               margin=dict(l=180, r=80, t=20, b=50), showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df_prem, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 5. Remote Premium
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Remote premium",
    "Megeri-e tavmunkaban dolgozni? A terkep orszagonkent mutatja a remote vs on-site "
    "atlagber kulonbseget (zold = a remote fizet tobbet, piros = kevesebbet). "
    "A mellette levo bar chart iparagankent bontja a remote es on-site atlagbereket.",
)
try:
    with engine.connect() as conn:
        df_remote = pd.read_sql(text(REMOTE_PREMIUM_SQL), conn)
    if df_remote.empty:
        st.info("Nincs remote premium adat.")
    else:
        for col in ["avg_remote_salary", "avg_onsite_salary", "remote_premium_usd"]:
            df_remote[col] = pd.to_numeric(df_remote[col], errors="coerce")

        country_premium = (
            df_remote.dropna(subset=["remote_premium_usd"])
            .groupby("country")
            .apply(lambda g: (g["remote_premium_usd"] * g["total_jobs"]).sum() / g["total_jobs"].sum())
            .reset_index(name="remote_premium_usd")
        )
        country_premium["_iso3"] = country_premium["country"].astype(str).str.lower().str[:2].map(ISO2_TO_ISO3)
        country_premium = country_premium.dropna(subset=["_iso3"])

        df_remote["_w_remote"] = df_remote["avg_remote_salary"].fillna(0) * df_remote["total_jobs"]
        df_remote["_w_onsite"] = df_remote["avg_onsite_salary"].fillna(0) * df_remote["total_jobs"]
        industry_agg = df_remote.groupby("industry", as_index=True).agg(
            _w_remote=("_w_remote", "sum"), _w_onsite=("_w_onsite", "sum"),
            total_jobs=("total_jobs", "sum"),
        )
        industry_agg["avg_remote_salary"] = (industry_agg["_w_remote"] / industry_agg["total_jobs"]).astype(float)
        industry_agg["avg_onsite_salary"] = (industry_agg["_w_onsite"] / industry_agg["total_jobs"]).astype(float)
        industry_agg = industry_agg.drop(columns=["_w_remote", "_w_onsite"]).reset_index()
        industry_agg = industry_agg.nlargest(20, "total_jobs").sort_values("avg_onsite_salary", ascending=True)
        industry_agg["industry"] = industry_agg["industry"].astype(str)

        col_map, col_bar = st.columns(2)
        with col_map:
            if country_premium.empty:
                st.warning("Nincs orszag ISO-3 megfelelo a terkephez.")
            else:
                z = country_premium["remote_premium_usd"].tolist()
                z_abs = max(abs(min(z)), abs(max(z)), 1)
                fig_map = go.Figure(go.Choropleth(
                    locations=country_premium["_iso3"], z=z, zmid=0, zmin=-z_abs, zmax=z_abs,
                    colorscale=[[0, "#f87171"], [0.5, "#1e293b"], [1, "#34d399"]],
                    autocolorscale=False, locationmode="ISO-3",
                    text=country_premium["country"].astype(str) + ": " + country_premium["remote_premium_usd"].apply(lambda x: f"{x:,.0f}"),
                    hoverinfo="text", marker_line_color="#334155", marker_line_width=0.5,
                    colorbar=dict(title="Premium", tickfont=dict(color="#94a3b8"), titlefont=dict(color="#94a3b8")),
                ))
                _apply(fig_map, height=380, geo=_DARK_GEO, margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig_map, use_container_width=True)

        with col_bar:
            if industry_agg.empty or industry_agg["avg_remote_salary"].sum() == 0:
                st.info("Nincs ipar / ber adat.")
            else:
                fig_bar = _fig(height=380)
                fig_bar.add_trace(go.Bar(name="Remote", x=industry_agg["industry"], y=industry_agg["avg_remote_salary"], marker_color="#34d399"))
                fig_bar.add_trace(go.Bar(name="On-site", x=industry_agg["industry"], y=industry_agg["avg_onsite_salary"], marker_color="#6366f1"))
                _apply(fig_bar, barmode="group",
                       xaxis=dict(type="category", tickangle=-45, tickfont=dict(size=10)),
                       yaxis_title="Salary", margin=dict(l=60, r=30, t=20, b=140))
                st.plotly_chart(fig_bar, use_container_width=True)

        with st.expander("Nyers adat"):
            st.dataframe(df_remote.head(100), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 6. Experience vs Salary ROI
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Tapasztalat vs ber (ROI)",
    "Hogyan no az atlagber a tapasztalati evek fuggvenyeben, es hol van a legnagyobb "
    "'megterueles'? A kek gorbe az atlagbert, a sarga szaggatott a bernovekmenyt mutatja "
    "evente. Ahol a sarga gorbe kiugrik, ott eri meg a legjobban tapasztalatot szerezni.",
)
try:
    with engine.connect() as conn:
        df_exp = pd.read_sql(text(EXPERIENCE_SALARY_SQL), conn)
    if df_exp.empty:
        st.info("Nincs tapasztalat/ber adat.")
    else:
        for col in ["avg_salary", "salary_jump_vs_prev", "salary_per_extra_year"]:
            if col in df_exp.columns:
                df_exp[col] = pd.to_numeric(df_exp[col], errors="coerce")

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_exp["experience_years_min"], y=df_exp["avg_salary"],
            name="Atlag ber", mode="lines+markers",
            line=dict(color="#6366f1", width=2.5), marker=dict(size=7), yaxis="y",
        ))
        fig.add_trace(go.Scatter(
            x=df_exp["experience_years_min"], y=df_exp["salary_per_extra_year"],
            name="ROI / extra ev", mode="lines+markers",
            line=dict(color="#fbbf24", width=2.5, dash="dot"), marker=dict(size=7, symbol="diamond"), yaxis="y2",
        ))
        _apply(fig, height=460,
               xaxis=dict(title="Min. tapasztalat (ev)", dtick=1),
               yaxis=dict(title="Atlag ber", titlefont=dict(color="#6366f1"), tickfont=dict(color="#818cf8")),
               yaxis2=dict(title="ROI / extra ev", side="right", overlaying="y",
                           titlefont=dict(color="#fbbf24"), tickfont=dict(color="#fbbf24")),
               margin=dict(l=60, r=60, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df_exp, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 7. Posting Lifespan Bubble
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Hirdetesi dinamika",
    "Melyik ceg toboroz agressziven? A buborek X tengelyen az atlagos hirdetes-elettartamot, "
    "Y-on a havi hirdetesszamot mutatja. A kicsi, bal felso sarokbeli pontok = "
    "gyors, intenziv toborzas. A buborek merete az aktualis nyitott poziciok szama.",
)
try:
    with engine.connect() as conn:
        df_bub = pd.read_sql(text(POSTING_LIFESPAN_SQL), conn)
    if df_bub.empty:
        st.info("Nincs posting lifespan adat.")
    else:
        for col in ["avg_posting_lifespan_days", "postings_per_month", "total_postings_6m", "currently_active"]:
            if col in df_bub.columns:
                df_bub[col] = pd.to_numeric(df_bub[col], errors="coerce")
        df_bub = df_bub.dropna(subset=["avg_posting_lifespan_days", "postings_per_month"])
        if df_bub.empty:
            st.warning("Nincs sor lifespan/postings ertekkel.")
        else:
            industries = sorted(df_bub["industry"].dropna().unique().tolist())
            color_map = {ind: PALETTE[i % len(PALETTE)] for i, ind in enumerate(industries)}
            active = df_bub["currently_active"].fillna(0).clip(lower=0)
            s_range = max(active.max() - active.min(), 1e-6)

            fig = _fig(height=520)
            for ind in industries:
                sub = df_bub[df_bub["industry"] == ind]
                if sub.empty:
                    continue
                ss = (10 + (sub["currently_active"].fillna(0) - active.min()) / s_range * 35).tolist()
                fig.add_trace(go.Scatter(
                    x=sub["avg_posting_lifespan_days"], y=sub["postings_per_month"],
                    mode="markers", name=ind,
                    marker=dict(size=ss, sizemode="diameter", color=color_map[ind],
                                line=dict(width=0.8, color="#1e293b"), opacity=0.85),
                    text=(sub["company"].astype(str) + "<br>Active: "
                          + sub["currently_active"].fillna(0).astype(int).astype(str)
                          + " | Total 6m: " + sub["total_postings_6m"].fillna(0).astype(int).astype(str)),
                    hoverinfo="text",
                ))
            _apply(fig, xaxis_title="Atl. elettartam (nap)", yaxis_title="Hirdetes / ho",
                   margin=dict(l=60, r=30, t=20, b=50))
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("Nyers adat"):
                st.dataframe(df_bub, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 8. Industry / Seniority stacked
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Iparagak seniority eloszlasa",
    "Hogyan oszlanak meg a junior, mid es senior poziciok az egyes iparagakban? "
    "100%%-os stacked bar chart – minden sav egy iparag, a szinek a seniority szinteket jelzik. "
    "A tooltip megjeleníti az adott metszet atlagberet is.",
)
try:
    with engine.connect() as conn:
        df_is = pd.read_sql(text(INDUSTRY_SENIORITY_SQL), conn)
    if df_is.empty:
        st.info("Nincs ipar / seniority adat.")
    else:
        df_is["pct_within_industry"] = pd.to_numeric(df_is["pct_within_industry"], errors="coerce").fillna(0)
        df_is["avg_salary"] = pd.to_numeric(df_is["avg_salary"], errors="coerce")
        industry_totals = df_is.groupby("industry")["job_count"].sum().sort_values(ascending=True)
        industries_ordered = industry_totals.index.tolist()
        seniorities = df_is["seniority_level"].dropna().unique().tolist()
        color_sen = {s: PALETTE[i % len(PALETTE)] for i, s in enumerate(seniorities)}

        fig = _fig(height=400 + len(industries_ordered) * 20)
        for sen in seniorities:
            pcts, salaries = [], []
            for ind in industries_ordered:
                row = df_is[(df_is["industry"] == ind) & (df_is["seniority_level"] == sen)]
                if row.empty:
                    pcts.append(0)
                    salaries.append("n/a")
                else:
                    pcts.append(float(row["pct_within_industry"].iloc[0]))
                    sal = row["avg_salary"].iloc[0]
                    salaries.append(f"{sal:,.0f}" if pd.notna(sal) else "n/a")
            fig.add_trace(go.Bar(
                name=sen, y=industries_ordered, x=pcts, orientation="h",
                marker_color=color_sen.get(sen, "#888"), customdata=salaries,
                hovertemplate="%{y}<br>%{x:.1f}%%<br>Avg salary: %{customdata}<extra></extra>",
            ))
        _apply(fig, barmode="stack",
               xaxis=dict(title="%%", range=[0, 100]),
               margin=dict(l=180, r=30, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df_is, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 9. Company Tech Radar
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Ceg tech profil",
    "Hasonlitsd ossze a cegek technologiai profiljat! A radar chart (spider) megmutatja, "
    "hogy az egyes cegek allasaiban milyen aranyban jelennek meg az egyes tech kategoriak "
    "(pl. language, framework, database). Valassz 3-5 ceget az osszehasonlitashoz.",
)
try:
    with engine.connect() as conn:
        df_ct = pd.read_sql(text(COMPANY_TECH_SQL), conn)
    if df_ct.empty:
        st.info("Nincs ceg / tech kategoria adat.")
    else:
        df_ct["pct_of_company_jobs"] = pd.to_numeric(df_ct["pct_of_company_jobs"], errors="coerce").fillna(0)
        companies_all = sorted(df_ct["company"].dropna().unique().tolist())
        categories_all = sorted(df_ct["tech_category"].dropna().unique().tolist())
        col1, col2 = st.columns([3, 1])
        with col1:
            selected = st.multiselect(
                "Cegek (3-5)", options=companies_all,
                default=companies_all[:min(5, len(companies_all))],
                max_selections=5, key="radar_companies",
            )
        with col2:
            view = st.radio("Nezet", ["Radar", "Stacked bar"], key="radar_view", horizontal=True)
        if not selected:
            st.warning("Valassz legalabb egy ceget.")
        elif not categories_all:
            st.warning("Nincs tech kategoria.")
        else:
            df_sel = df_ct[df_ct["company"].isin(selected)]
            if view == "Radar":
                fig = _fig(height=520)
                for i, company in enumerate(selected):
                    r = []
                    for cat in categories_all:
                        row = df_sel[(df_sel["company"] == company) & (df_sel["tech_category"] == cat)]
                        r.append(float(row["pct_of_company_jobs"].iloc[0]) if not row.empty else 0)
                    fig.add_trace(go.Scatterpolar(
                        r=r, theta=categories_all, name=company, fill="toself",
                        line=dict(color=PALETTE[i % len(PALETTE)]),
                    ))
                _apply(fig, polar=dict(
                    bgcolor="rgba(0,0,0,0)",
                    radialaxis=dict(visible=True, range=[0, 100], gridcolor="#334155", tickfont=dict(color="#64748b")),
                    angularaxis=dict(gridcolor="#334155", tickfont=dict(color="#94a3b8")),
                ), margin=dict(l=60, r=60, t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                fig = _fig(height=430)
                for i, cat in enumerate(categories_all):
                    pcts = []
                    for comp in selected:
                        row = df_sel[(df_sel["company"] == comp) & (df_sel["tech_category"] == cat)]
                        pcts.append(float(row["pct_of_company_jobs"].iloc[0]) if not row.empty else 0)
                    fig.add_trace(go.Bar(name=cat, x=selected, y=pcts, marker_color=PALETTE[i % len(PALETTE)]))
                _apply(fig, barmode="stack", yaxis_title="%%", xaxis_tickangle=-45,
                       margin=dict(l=60, r=30, t=20, b=140))
                st.plotly_chart(fig, use_container_width=True)
            with st.expander("Nyers adat"):
                st.dataframe(df_sel.head(150), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 10. Salary Range
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Fizetesi spread (range ratio)",
    "Hol a legszelessebb a fizetesi sav? Minden sor egy pozicio+ipar kombinacio, "
    "es az atlagos min-max tartomannyal jelzett savot mutatja. "
    "Minel pirosabb es szelessebb, annal nagyobb a fizetesi bizonytalansag "
    "('fekete lyuk' – nem tudni, mennyit is fizetnek valojaban).",
)
try:
    with engine.connect() as conn:
        df_sr = pd.read_sql(text(SALARY_RANGE_SQL), conn)
    if df_sr.empty:
        st.info("Nincs fizetesi range adat.")
    else:
        for col in ["avg_min", "avg_max", "avg_range", "stddev_range", "range_ratio"]:
            if col in df_sr.columns:
                df_sr[col] = pd.to_numeric(df_sr[col], errors="coerce")
        df_sr = df_sr.dropna(subset=["avg_min", "avg_max", "range_ratio"])
        df_sr["label"] = df_sr["normalized_title"].astype(str) + " | " + df_sr["industry"].astype(str)
        df_sr = df_sr.sort_values("range_ratio", ascending=False).reset_index(drop=True)
        labels = df_sr["label"].tolist()[::-1]
        n = len(labels)
        r_min, r_max = float(df_sr["range_ratio"].min()), float(df_sr["range_ratio"].max())
        r_range = (r_max - r_min) or 1

        fig = _fig(height=400 + n * 18)
        for i in range(n):
            row = df_sr.iloc[n - 1 - i]
            mn, mx = float(row["avg_min"]), float(row["avg_max"])
            ratio = float(row["range_ratio"])
            norm = (ratio - r_min) / r_range
            r_c = int(99 + 157 * norm)
            g_c = int(102 - 60 * norm)
            b_c = int(241 - 180 * norm)
            color = f"rgb({r_c},{g_c},{b_c})"
            cd = [ratio, int(row["job_count"]), mn, mx]
            fig.add_trace(go.Scatter(
                x=[mn, mx], y=[i, i], mode="lines",
                line=dict(width=14, color=color), customdata=[cd, cd],
                hovertemplate="%{customdata[2]:,.0f} – %{customdata[3]:,.0f}<br>Range ratio: %{customdata[0]:.3f}<br>Jobs: %{customdata[1]}<extra></extra>",
            ))
        _apply(fig,
               yaxis=dict(tickvals=list(range(n)), ticktext=labels, tickfont=dict(size=10)),
               xaxis_title="Fizetes", showlegend=False, hovermode="closest",
               margin=dict(l=220, r=60, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df_sr, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 11. City Tech Map
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Varos / tech terkep",
    "Hol koncentralodnak az IT allasok, es milyen technologiak dominalnak az egyes varosokban? "
    "A pontok merete az allasszamot, szine a domians tech kategoriat jelzi. "
    "Szurj technologiara, hogy lasd, melyik varos a hub az adott tech-nek.",
)
try:
    with engine.connect() as conn:
        df_city = pd.read_sql(text(CITY_TECH_MAP_SQL), conn)
    if df_city.empty:
        st.info("Nincs varos/tech terkep adat (lat/lng hianyzik).")
    else:
        for col in ["lat", "lng", "job_count", "city_share_pct"]:
            if col in df_city.columns:
                df_city[col] = pd.to_numeric(df_city[col], errors="coerce")
        df_city = df_city.dropna(subset=["lat", "lng"])
        if df_city.empty:
            st.info("Nincs lat/lng adat a varosokhoz.")
        else:
            tech_options = sorted(df_city["technology"].dropna().unique().tolist())
            selected_tech = st.multiselect(
                "Technologia szuro", options=tech_options,
                default=tech_options[:min(10, len(tech_options))], key="city_map_tech",
            )
            if selected_tech:
                df_city = df_city[df_city["technology"].isin(selected_tech)]
            if df_city.empty:
                st.warning("Nincs adat a kivalasztott technologiakkal.")
            else:
                city_agg = df_city.groupby(["city", "country", "lat", "lng"], as_index=False).agg(total_jobs=("job_count", "sum"))
                dominant = (
                    df_city.groupby(["city", "country", "lat", "lng"])
                    .apply(lambda g: g.loc[g["job_count"].idxmax(), "category"])
                    .reset_index(name="dominant_category")
                )
                city_agg = city_agg.merge(dominant, on=["city", "country", "lat", "lng"])
                categories = city_agg["dominant_category"].dropna().unique().tolist()
                cat_colors = {c: PALETTE[i % len(PALETTE)] for i, c in enumerate(categories)}

                fig = _fig(height=520)
                for cat in categories:
                    sub = city_agg[city_agg["dominant_category"] == cat]
                    ss = (6 + (sub["total_jobs"] - city_agg["total_jobs"].min()) / max(city_agg["total_jobs"].max() - city_agg["total_jobs"].min(), 1) * 25).clip(6, 35).tolist()
                    fig.add_trace(go.Scattergeo(
                        lat=sub["lat"], lon=sub["lng"],
                        text=(sub["city"].astype(str) + ", " + sub["country"].astype(str)
                              + "<br>Jobs: " + sub["total_jobs"].astype(int).astype(str) + " | " + cat),
                        mode="markers", name=cat,
                        marker=dict(size=ss, sizemode="diameter", color=cat_colors.get(cat, "#888"),
                                    line=dict(width=0.5, color="#1e293b"), opacity=0.85),
                        hoverinfo="text",
                    ))
                _apply(fig, geo=_DARK_GEO, margin=dict(l=0, r=0, t=20, b=0))
                st.plotly_chart(fig, use_container_width=True)
                with st.expander("Nyers adat"):
                    st.dataframe(df_city.head(200), use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 12. Education vs Salary
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Vegzettseg vs ber",
    "Megeri-e a diploma? A grouped bar chart iparagankent es vegzettsegi szintenként "
    "mutatja a median bert. A szaggatott referenciavonal az osszes adat medianja – "
    "ami felette van diploma nelkul, az az 'arbitrazs zona' (magas ber, alacsony belepesi kuszcob).",
)
try:
    with engine.connect() as conn:
        df_edu = pd.read_sql(text(EDUCATION_SALARY_SQL), conn)
    if df_edu.empty:
        st.info("Nincs education/salary adat.")
    else:
        for col in ["avg_salary", "median_salary", "p75_salary", "max_salary"]:
            if col in df_edu.columns:
                df_edu[col] = pd.to_numeric(df_edu[col], errors="coerce")
        overall_median = float(df_edu["median_salary"].dropna().median())
        industries = sorted(df_edu["industry"].dropna().unique().tolist())

        fig = _fig(height=480)
        for i, ind in enumerate(industries):
            sub = df_edu[df_edu["industry"] == ind]
            fig.add_trace(go.Bar(name=ind, x=sub["education_required"], y=sub["median_salary"], marker_color=PALETTE[i % len(PALETTE)]))
        fig.add_hline(y=overall_median, line_dash="dash", line_color="#94a3b8",
                      annotation_text="Median", annotation_font_color="#94a3b8")
        _apply(fig, barmode="group", xaxis_title="Vegzettseg", yaxis_title="Median salary",
               xaxis_tickangle=-45, margin=dict(l=60, r=30, t=20, b=140))
        st.plotly_chart(fig, use_container_width=True)
        with st.expander("Nyers adat"):
            st.dataframe(df_edu, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 13. Unicorn Jobs
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Unicorn allasok",
    "Melyek a legritkabb skill-kombinaciokat igenylo allasok? Minel alacsonyabb egy pozicio "
    "atlagos par-gyakorisaga, annal egyedibb – ezek az 'unicorn' allasok, "
    "amelyekre keves jelolt felel meg. Idealis celpontok a specializalodott szakemberek szamara.",
)
try:
    with engine.connect() as conn:
        df_uni = pd.read_sql(text(UNICORN_JOBS_SQL), conn)
    if df_uni.empty:
        st.info("Nincs unicorn job adat.")
    else:
        df_uni["avg_pair_frequency"] = pd.to_numeric(df_uni["avg_pair_frequency"], errors="coerce")
        freq_max = float(df_uni["avg_pair_frequency"].max())
        freq_min = float(df_uni["avg_pair_frequency"].min())
        freq_range = max(freq_max - freq_min, 1e-6)

        df_display = df_uni[["unicorn_rank", "title", "company", "n_skills", "avg_pair_frequency"]].copy()
        df_display["rarity_pct"] = df_uni["avg_pair_frequency"].apply(
            lambda v: round(100 - min(100, max(0, (float(v) - freq_min) / freq_range * 100)), 1)
        )

        def _spark(n):
            pct = (float(n) - freq_min) / freq_range
            b = max(0, min(10, int((1 - pct) * 10)))
            return "\u2588" * b + "\u2591" * (10 - b)

        df_display["rarity_bar"] = df_uni["avg_pair_frequency"].apply(_spark)
        st.dataframe(df_display, use_container_width=True)

        fig = _fig(height=220)
        fig.add_trace(go.Bar(x=df_uni["unicorn_rank"], y=df_uni["avg_pair_frequency"], marker_color="#6366f1"))
        _apply(fig, xaxis_title="Unicorn rank", yaxis_title="Avg pair freq.", showlegend=False,
               margin=dict(l=60, r=30, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 14. Source Quality
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Adatforras minoseg",
    "Mennyire megbizhatok az egyes adatforrasok? A tablazat szines hatterrel jelzi "
    "a hianyzo adatok aranyat (zold = jo, piros = sok hianyzik). "
    "Az avg processing min a feldolgozasi idot mutatja – lassabb forrasok tovabbi optimalizalast igenyelhetnek.",
)
try:
    with engine.connect() as conn:
        df_sq = pd.read_sql(text(SOURCE_QUALITY_SQL), conn)
    if df_sq.empty:
        st.info("Nincs source quality adat.")
    else:
        pct_cols = ["error_rate_pct", "missing_salary_pct", "missing_location_pct", "missing_seniority_pct"]
        for col in pct_cols + ["avg_processing_min"]:
            if col in df_sq.columns:
                df_sq[col] = pd.to_numeric(df_sq[col], errors="coerce")
        styled = df_sq.style.background_gradient(
            subset=[c for c in pct_cols if c in df_sq.columns], cmap="RdYlGn_r", vmin=0, vmax=100,
        )
        st.dataframe(styled, use_container_width=True)

        fig = _fig(height=260)
        fig.add_trace(go.Bar(
            x=df_sq["source"], y=df_sq["avg_processing_min"].fillna(0), marker_color="#6366f1",
            text=df_sq["avg_processing_min"].fillna(0).apply(lambda x: f"{x:.1f}"),
            textposition="outside", textfont=dict(size=11),
        ))
        _apply(fig, showlegend=False, xaxis_title="Source", yaxis_title="Perc",
               margin=dict(l=60, r=30, t=20, b=50))
        st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.error(str(e))

# ═══════════════════════════════════════════════════════════════════════════
# 15. Zombie Jobs
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
_section(
    "Zombie hirdetesek",
    "Mely allashirdetesek 'elnek' gyanusan sokaig? Harom tipust figyelunk: "
    "nincs lejarat de aktiv (piros), lejart de meg aktiv (sarga), 90+ napja fut (lila). "
    "A timeline mutatja a posted -> last_seen idoszakot, a donut a tipusok aranyat.",
)
try:
    with engine.connect() as conn:
        df_z = pd.read_sql(text(ZOMBIE_JOBS_SQL), conn)
    if df_z.empty:
        st.info("Nincs zombie job adat.")
    else:
        df_z["posted_at"] = pd.to_datetime(df_z["posted_at"])
        df_z["days_alive"] = pd.to_numeric(df_z["days_alive"], errors="coerce").fillna(0).astype(int)
        companies_z = sorted(df_z["company"].dropna().unique().tolist())
        sel_company = st.multiselect(
            "Ceg szuro", options=companies_z,
            default=companies_z[:5] if len(companies_z) >= 5 else companies_z, key="zombie_company",
        )
        if sel_company:
            df_z = df_z[df_z["company"].isin(sel_company)]
        if df_z.empty:
            st.warning("Nincs sor a kivalasztott cegekkel.")
        else:
            z_type_colors = {
                "no_expiry_ever_set": "#f87171",
                "expired_but_still_active": "#fbbf24",
                "long_running_90d+": "#a78bfa",
                "normal": "#34d399",
            }

            col_donut, col_timeline = st.columns([1, 2])
            with col_donut:
                type_counts = df_z["zombie_type"].value_counts()
                fig_d = go.Figure(go.Pie(
                    labels=type_counts.index.tolist(), values=type_counts.tolist(), hole=0.6,
                    marker=dict(colors=[z_type_colors.get(t, "#888") for t in type_counts.index]),
                ))
                _apply(fig_d, height=380, margin=dict(l=20, r=20, t=20, b=20))
                st.plotly_chart(fig_d, use_container_width=True)

            with col_timeline:
                df_z["last_seen_at"] = pd.to_datetime(df_z["last_seen_at"])
                sub = df_z.head(35)
                fig_g = _fig(height=380 + len(sub) * 14)
                for i, (_, row) in enumerate(sub.iterrows()):
                    fig_g.add_trace(go.Scatter(
                        x=[row["posted_at"], row["last_seen_at"]], y=[i, i], mode="lines",
                        line=dict(width=14, color=z_type_colors.get(row["zombie_type"], "#888")),
                        name=row["zombie_type"], legendgroup=row["zombie_type"],
                        showlegend=(i == 0 or row["zombie_type"] != sub.iloc[max(0, i - 1)].get("zombie_type")),
                    ))
                _apply(fig_g,
                       xaxis=dict(type="date"),
                       yaxis=dict(tickvals=list(range(len(sub))), ticktext=sub["title"].astype(str).str[:40].tolist(), tickfont=dict(size=9)),
                       margin=dict(l=220, r=30, t=20, b=50))
                st.plotly_chart(fig_g, use_container_width=True)

            with st.expander("Nyers adat"):
                st.dataframe(df_z.head(100), use_container_width=True)
except Exception as e:
    st.error(str(e))

# Footer
st.markdown(
    '<hr class="section-divider">'
    '<p style="text-align:center;color:#475569;font-size:0.8rem;padding:1rem 0">'
    'WorkLense – IT allaspiaci analytics</p>',
    unsafe_allow_html=True,
)
