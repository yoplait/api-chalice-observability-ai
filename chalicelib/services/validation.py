"""Input validation helpers (pure, unit-testable)."""

from __future__ import annotations

import re

from chalicelib.errors import InvalidRequest

NAME_PATTERN = re.compile(r"^[A-Za-z0-9 _\-]{1,64}$")
DELAY_MIN = 0.05
MAX_DELAY_CEIL = 30.0


def validate_name(raw: str | None) -> str:
    if raw is None or raw == "":
        return "world"
    if not NAME_PATTERN.match(raw):
        raise InvalidRequest(
            "Parameter 'name' must be 1-64 chars of letters, digits, space, '_' or '-'"
        )
    return raw


def validate_delay(raw: str | None, max_delay: float) -> float:
    if raw is None or raw == "":
        return 0.2
    try:
        seconds = float(raw)
    except ValueError:
        raise InvalidRequest("Parameter 'delay' must be a number") from None
    ceiling = min(max_delay, MAX_DELAY_CEIL)
    if seconds < DELAY_MIN or seconds > ceiling:
        raise InvalidRequest(f"Parameter 'delay' must be between {DELAY_MIN} and {ceiling} seconds")
    return seconds
