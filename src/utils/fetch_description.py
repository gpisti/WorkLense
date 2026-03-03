"""Fetch full job description from job page URL (APIs often return only a snippet)."""
import requests
from bs4 import BeautifulSoup

from src.utils.logger import logger

_USER_AGENT = "Mozilla/5.0 (compatible; WorkLense/1.0)"
_MIN_SELECTOR_CHARS = 100

# Adzuna job page: description is in this section (fallback to body text if missing/short)
_ADZUNA_SELECTOR = (
    "body > div.container.mx-auto.bg-white.font-sans.text-adzuna-gray-900.md\\:px-4 "
    "> main > div > section.lg\\:flex.mb-4 > div.flex-grow > section"
)


def fetch_full_description(url: str, max_chars: int = 15000, timeout: int = 10, source: str | None = None) -> str | None:
    """Get main text from job page. For source='adzuna' uses section selector first, then fallback."""
    if not url or not url.startswith("http"):
        return None
    try:
        r = requests.get(url, headers={"User-Agent": _USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        text = None
        if source == "adzuna":
            el = soup.select_one(_ADZUNA_SELECTOR)
            if el:
                text = el.get_text(separator="\n", strip=True)
                text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
            if not text or len(text) < _MIN_SELECTOR_CHARS:
                text = None

        if text is None:
            for tag in soup(["script", "style", "nav", "header", "footer"]):
                tag.decompose()
            text = soup.get_text(separator="\n", strip=True)
            text = "\n".join(line.strip() for line in text.splitlines() if line.strip())

        return text[:max_chars] if text else None
    except Exception as e:
        logger.debug(f"Fetch description from URL failed: {e}")
        return None
