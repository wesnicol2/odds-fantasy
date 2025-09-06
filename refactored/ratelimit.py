from __future__ import annotations

from datetime import datetime
from typing import Optional


_LAST = {
    "remaining": None,   # type: Optional[int]
    "used": None,        # type: Optional[int]
    "source": None,      # 'network' | 'cache' | None
    "endpoint": None,    # 'events' | f'event_odds:{id}' | None
    "ts": None,          # datetime
}


def update_from_response(headers: dict, endpoint: str):
    global _LAST
    rem = None
    used = None
    for k, v in headers.items():
        lk = k.lower()
        if "requests" in lk and "remaining" in lk:
            try:
                rem = int(v)
            except Exception:
                rem = v
        if "requests" in lk and "used" in lk:
            try:
                used = int(v)
            except Exception:
                used = v
    _LAST.update({
        "remaining": rem if rem is not None else _LAST.get("remaining"),
        "used": used if used is not None else _LAST.get("used"),
        "source": "network",
        "endpoint": endpoint,
        "ts": datetime.utcnow(),
    })


def update_cached(endpoint: str):
    global _LAST
    _LAST.update({
        "source": "cache",
        "endpoint": endpoint,
        "ts": datetime.utcnow(),
    })


def format_status() -> str:
    """Return a simple percentage of remaining requests, plus source and endpoint.

    If we have both remaining and used, percent = remaining / (remaining + used) * 100.
    Otherwise, show ?%.
    """
    rem = _LAST.get("remaining")
    used = _LAST.get("used")
    src = _LAST.get("source") or "n/a"
    ep = _LAST.get("endpoint") or "n/a"

    pct_str = "?%"
    try:
        if isinstance(rem, int) and isinstance(used, int) and (rem + used) > 0:
            pct = (rem / (rem + used)) * 100.0
            pct_str = f"{pct:.1f}%"
    except Exception:
        pass

    return f"remaining={pct_str}, source={src}, endpoint={ep}"


def get_details() -> dict:
    """Return a structured view of the last rate limit readings.

    Keys:
      - remaining: int | None
      - used: int | None
      - total: int | None (remaining+used when available)
      - pct: float | None (0..100)
      - pct_str: str (e.g., '84.2%')
      - source: 'network' | 'cache' | 'n/a'
      - endpoint: str
    """
    rem = _LAST.get("remaining")
    used = _LAST.get("used")
    total = None
    pct = None
    pct_str = "?%"
    try:
        if isinstance(rem, int) and isinstance(used, int):
            total = rem + used
            if total > 0:
                pct = (rem / total) * 100.0
                pct_str = f"{pct:.1f}%"
    except Exception:
        pass
    return {
        "remaining": rem if isinstance(rem, int) else None,
        "used": used if isinstance(used, int) else None,
        "total": total,
        "pct": pct,
        "pct_str": pct_str,
        "source": _LAST.get("source") or "n/a",
        "endpoint": _LAST.get("endpoint") or "n/a",
    }
