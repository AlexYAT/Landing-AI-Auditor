"""Report export service."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def export_report(report: dict[str, Any] | Any, output_path: str) -> None:
    """Save report JSON to file and create parent directory if needed."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict() if hasattr(report, "to_dict") else report
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
