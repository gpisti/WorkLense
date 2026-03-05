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
    FINDWORK_API_KEY: str = os.getenv("FINDWORK_API_KEY", "")

    # NLP / LLM (Ollama)
    OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral:7b")
    OLLAMA_TECH_MODEL = os.getenv("OLLAMA_TECH_MODEL", "qwen2.5:7b-instruct")

    # Embeddings (sentence-transformers)
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

settings = Settings()
