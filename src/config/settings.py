import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql://worklense:worklense@localhost:5432/worklense"
    )
    
    # Application
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

    # Scrapers
    ADZUNA_API_KEY = os.getenv("ADZUNA_API_KEY")
    ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID")

settings = Settings()
