"""Подготовка сэмплов данных для промптов LLM (профиль + стратификация)."""

from __future__ import annotations

from typing import Any

from app.chart_data_profile import format_profile_for_prompt, profile_data


def stratified_sample(
    data: list[dict],
    *,
    max_rows: int = 12,
    diversify_by: str = "region",
) -> list[dict]:
    """Возвращает репрезентативную выборку: разнообразие по ключевой колонке + хвост."""
    if not data:
        return []
    if diversify_by not in data[0]:
        return data[:max_rows]

    seen: set[Any] = set()
    diverse: list[dict] = []
    for row in data:
        key = row.get(diversify_by)
        if key is not None and key not in seen:
            seen.add(key)
            diverse.append(row)
            if len(diverse) >= max(4, max_rows // 2):
                break
    tail = data[: max(2, max_rows - len(diverse))]
    merged = diverse + [r for r in tail if r not in diverse]
    return merged[:max_rows]


def format_data_for_llm(
    data: list[dict],
    *,
    max_rows: int = 12,
    diversify_by: str = "region",
) -> tuple[str, str]:
    """Профиль + сэмпл для вставки в промпт. Возвращает (profile_text, sample_repr)."""
    if not data:
        return "Нет данных.", "[]"
    profile = profile_data(data)
    profile_text = format_profile_for_prompt(profile)
    sample = stratified_sample(data, max_rows=max_rows, diversify_by=diversify_by)
    return profile_text, str(sample)