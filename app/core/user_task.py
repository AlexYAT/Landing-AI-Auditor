"""Sanitization of user-provided business task strings for safe LLM use."""

from __future__ import annotations

import re

# Keep tasks short enough to limit injection surface; 300–500 range.
MAX_USER_TASK_LENGTH: int = 400

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_user_task(task: str | None) -> str | None:
    """
    Normalize and bound user_task for prompt insertion (not executable instructions).

    - Trims; empty -> None
    - Collapses whitespace and newlines to single spaces
    - Strips ASCII control characters
    - Truncates to MAX_USER_TASK_LENGTH
    """
    if task is None:
        return None
    if not isinstance(task, str):
        return None
    s = task.strip()
    if not s:
        return None
    s = s.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", " ")
    s = _CONTROL_CHARS_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return None
    if len(s) > MAX_USER_TASK_LENGTH:
        s = s[:MAX_USER_TASK_LENGTH].rstrip()
    return s or None
