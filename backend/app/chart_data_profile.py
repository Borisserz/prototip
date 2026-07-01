"""Профиль данных для промпта ChartAgent."""

from __future__ import annotations

from typing import Any

import pandas as pd

DIMENSIONS = ("region", "tax_type", "period")
METRICS = ("accrued", "paid", "debt", "penalties", "taxpayers")


def profile_data(data: list[dict]) -> dict[str, Any]:
    """Краткая сводка колонок для LLM (без полного датасета)."""
    if not data:
        return {"row_count": 0, "columns": []}

    df = pd.DataFrame(data)
    profile: dict[str, Any] = {
        "row_count": len(df),
        "columns": list(df.columns),
        "dimensions": {},
        "metrics": {},
    }

    for col in DIMENSIONS:
        if col in df.columns:
            uniq = df[col].dropna().unique().tolist()
            profile["dimensions"][col] = {
                "nunique": len(uniq),
                "top_values": [str(v) for v in uniq[:5]],
            }

    for col in df.columns:
        if col in METRICS or pd.api.types.is_numeric_dtype(df[col]):
            try:
                s = pd.to_numeric(df[col], errors="coerce").dropna()
                if not s.empty:
                    profile["metrics"][col] = {
                        "min": float(s.min()),
                        "max": float(s.max()),
                        "sum": float(s.sum()),
                    }
            except Exception:
                pass

    return profile


def format_profile_for_prompt(profile: dict[str, Any]) -> str:
    lines = [f"Строк: {profile.get('row_count', 0)}", f"Колонки: {profile.get('columns', [])}"]
    for dim, info in (profile.get("dimensions") or {}).items():
        lines.append(
            f"  {dim}: {info.get('nunique')} уник., примеры: {info.get('top_values', [])[:3]}"
        )
    for met, info in (profile.get("metrics") or {}).items():
        lines.append(f"  {met}: min={info.get('min'):.0f}, max={info.get('max'):.0f}")
    return "\n".join(lines)
