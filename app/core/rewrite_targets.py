"""Parse and validate --rewrite CLI values (hero, cta, trust)."""

from __future__ import annotations

ALLOWED_REWRITE_TARGETS: frozenset[str] = frozenset({"hero", "cta", "trust"})


def parse_rewrite_targets_arg(raw: str) -> tuple[str, ...]:
    """
    Parse comma-separated rewrite targets; dedupe preserving first-seen order.

    Used as argparse ``type=`` for ``--rewrite``. Raises ``argparse.ArgumentTypeError`` on bad input.
    """
    import argparse

    s = raw.strip()
    if not s:
        raise argparse.ArgumentTypeError(
            "rewrite targets cannot be empty; use hero, cta, and/or trust (comma-separated).",
        )
    parts = [p.strip().lower() for p in s.split(",")]
    parts = [p for p in parts if p]
    if not parts:
        raise argparse.ArgumentTypeError(
            "rewrite targets cannot be empty; use hero, cta, and/or trust (comma-separated).",
        )
    unknown = [p for p in parts if p not in ALLOWED_REWRITE_TARGETS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"invalid rewrite target(s): {', '.join(unknown)}. Allowed: hero, cta, trust (comma-separated).",
        )
    ordered_unique: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if p not in seen:
            seen.add(p)
            ordered_unique.append(p)
    return tuple(ordered_unique)
