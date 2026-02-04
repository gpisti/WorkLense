import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from loguru import logger
from src.config.settings import settings


class DatabaseConnection:
    #TODO: Connection pooling (we'll add later)
    
    @staticmethod
    @contextmanager
    def get_connection():
        conn = None
        try:
            conn = psycopg2.connect(
                settings.database_url,
                cursor_factory=RealDictCursor
            )
            logger.debug(f"Database connection established: {settings.postgres_host}")
            yield conn
            conn.commit()
        except psycopg2.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()
                logger.debug("Database connection closed")
                