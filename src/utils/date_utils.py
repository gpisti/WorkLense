from datetime import datetime, timezone


def parse_date(date_str) -> datetime:
    if not date_str:
        return datetime.now(timezone.utc)
    try:
        if 'T' in date_str:
            date_str = date_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(date_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)
