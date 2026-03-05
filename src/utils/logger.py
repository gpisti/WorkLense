from loguru import logger as _logger
import sys
import os
from src.config.settings import settings


def setup_logger():
    _logger.remove()
    
    _logger.add(
        sys.stdout,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
               "<level>{message}</level>",
        level=settings.LOG_LEVEL
    )
    
    log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
        _logger.add(
            os.path.join(log_dir, "errors.log"),
            rotation="500 MB",
            retention="10 days",
            level="ERROR",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"
        )
    except PermissionError:
        pass
    
    return _logger


logger = setup_logger()