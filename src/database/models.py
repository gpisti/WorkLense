from contextlib import contextmanager
from sqlalchemy import (
    Column, Integer, BigInteger, String, Text, Boolean, 
    DateTime, Numeric, ForeignKey, UniqueConstraint, CheckConstraint, JSON, create_engine
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, declarative_base, sessionmaker, Session
from sqlalchemy.sql import func
from src.config.settings import settings
from src.utils.logger import logger

Base = declarative_base()

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=False
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_session() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database session error: {e}")
        raise
    finally:
        session.close()


class Company(Base):
    __tablename__ = 'companies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    normalized_name = Column(String(255), nullable=False, unique=True)
    website = Column(String(500))
    industry = Column(String(100))
    company_size = Column(String(50))
    headquarters_country = Column(String(2))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    jobs = relationship("Job", back_populates="company")


class Location(Base):
    __tablename__ = 'locations'
    
    id = Column(Integer, primary_key=True)
    city = Column(String(100))
    state_province = Column(String(100))
    country = Column(String(2), nullable=False)
    country_name = Column(String(100), nullable=False)
    continent = Column(String(50), nullable=False)
    latitude = Column(Numeric(9, 6))
    longitude = Column(Numeric(9, 6))
    timezone = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    jobs = relationship("Job", back_populates="location")
    
    __table_args__ = (
        UniqueConstraint('city', 'state_province', 'country', name='uq_location'),
    )


class Technology(Base):
    __tablename__ = 'technologies'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    category = Column(String(50), nullable=False)
    aliases = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    jobs = relationship("JobTechnology", back_populates="technology")


class Skill(Base):
    __tablename__ = 'skills'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    type = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    jobs = relationship("JobSkill", back_populates="skill")


class RawJob(Base):
    __tablename__ = 'raw_jobs'
    
    id = Column(BigInteger, primary_key=True)
    source = Column(String(50), nullable=False)
    external_id = Column(String(255), nullable=False)
    raw_data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    processed = Column(Boolean, default=False)
    processed_at = Column(DateTime(timezone=True))
    error_message = Column(Text)
    
    jobs = relationship("Job", back_populates="raw_job")
    
    __table_args__ = (
        UniqueConstraint('source', 'external_id', name='uq_raw_job'),
    )


class Job(Base):
    __tablename__ = 'jobs'
    
    id = Column(BigInteger, primary_key=True)
    external_id = Column(String(255), nullable=False)
    source = Column(String(50), nullable=False)
    
    title = Column(String(500), nullable=False)
    normalized_title = Column(String(200))
    description = Column(Text, nullable=False)
    url = Column(String(1000), nullable=False)
    
    company_id = Column(Integer, ForeignKey('companies.id', ondelete='SET NULL'))
    location_id = Column(Integer, ForeignKey('locations.id', ondelete='SET NULL'))
    raw_job_id = Column(BigInteger, ForeignKey('raw_jobs.id', ondelete='SET NULL'))
    
    is_remote = Column(Boolean, default=False)
    is_hybrid = Column(Boolean, default=False)
    
    salary_min = Column(Numeric(12, 2))
    salary_max = Column(Numeric(12, 2))
    salary_currency = Column(String(3))
    salary_period = Column(String(20))
    
    employment_type = Column(String(20))
    seniority_level = Column(String(20))
    experience_years_min = Column(Integer)
    experience_years_max = Column(Integer)
    education_required = Column(String(50))
    
    benefits = Column(JSONB)
    
    posted_at = Column(DateTime(timezone=True), nullable=False)
    scraped_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    
    content_hash = Column(String(64), nullable=False)
    
    company = relationship("Company", back_populates="jobs")
    location = relationship("Location", back_populates="jobs")
    raw_job = relationship("RawJob", back_populates="jobs")
    technologies = relationship("JobTechnology", back_populates="job")
    skills = relationship("JobSkill", back_populates="job")
    
    __table_args__ = (
        UniqueConstraint('source', 'external_id', name='uq_job'),
        CheckConstraint('salary_min IS NULL OR salary_max IS NULL OR salary_min <= salary_max', name='chk_salary'),
    )


class JobTechnology(Base):
    __tablename__ = 'job_technologies'
    
    job_id = Column(BigInteger, ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    technology_id = Column(Integer, ForeignKey('technologies.id', ondelete='CASCADE'), primary_key=True)
    is_required = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="technologies")
    technology = relationship("Technology", back_populates="jobs")


class JobSkill(Base):
    __tablename__ = 'job_skills'
    
    job_id = Column(BigInteger, ForeignKey('jobs.id', ondelete='CASCADE'), primary_key=True)
    skill_id = Column(Integer, ForeignKey('skills.id', ondelete='CASCADE'), primary_key=True)
    is_required = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    job = relationship("Job", back_populates="skills")
    skill = relationship("Skill", back_populates="jobs")

# -----------------------------------------------------------------------------
# Gál István – szakdolgozat. A megvalósítás során mesterséges intelligencia (AI) eszközöket használtam.
