"""ChartAgent: вопрос + данные → ChartSpec (выбор типа + заполнение).

Модель сама решает тип по правилам (время→line, сравнение→bar/grouped/stacked, доли→donut, рейтинг→horizontal_bar, kpi для одиночных метрик, heatmap для матриц).
Затем детерминированный build_chart из viz (никакого exec()).
LLM — через core.llm structured (возвращает ChartSpec напрямую).
"""

from __future__ import annotations

import logging
import time

from app.agents.base_agent import BaseAgent
from app.agents.models import ChartAgentInput, ChartAgentResult
from app.chart_data_profile import format_profile_for_prompt, profile_data
from app.chart_repair import normalize_chart_spec, repair_chart_spec
from core.llm import call_structured, setup_logging
from core.models import ChartSpec


setup_logging()
logger = logging.getLogger("ChartAgent")

from app.agents.config_loader import get_agent_config


class ChartAgent(BaseAgent):
    """Агент выбора и заполнения ChartSpec по вопросу и данным."""

    name = "chart_agent"
    description = "По вопросу + данным выбирает тип графика (line/bar/donut/... по эвристикам) и заполняет ChartSpec (structured). Рендер — всегда через viz/charts.py."
    max_retries = 3

    def run(self, question: str, data: list[dict]) -> ChartAgentResult:
        start = time.time()
        logger.info(f"[ChartAgent] start: question={question[:60]}... rows={len(data)}")
        inp = ChartAgentInput(question=question, data=data[:20])  # лимит для промпта

        # Краткое описание данных для промпта.
        # Важно: даём разнообразие по регионам, если они есть в данных,
        # чтобы модель видела необходимость color=region для вопросов "по регионам".
        sample = data[:5] if data else []
        if data and len(data) > 5 and "region" in data[0]:
            try:
                seen_regions = {}
                diverse = []
                for row in data:
                    reg = row.get("region")
                    if reg and reg not in seen_regions:
                        seen_regions[reg] = True
                        diverse.append(row)
                        if len(diverse) >= 6:
                            break
                # Добавляем немного общих строк сверху
                sample = (diverse + data[:4])[:10]
            except Exception:
                sample = data[:5]

        data_profile = profile_data(data)
        profile_text = format_profile_for_prompt(data_profile)

        last_error: str | None = None
        specs: list[ChartSpec] = []

        from pydantic import BaseModel

        class ChartList(BaseModel):
            charts: list[ChartSpec]

        for attempt in range(self.max_retries):
            retry_hint = ""
            if last_error:
                retry_hint = (
                    f"\nПредыдущая попытка не удалась: {last_error}\n"
                    "Исправь спецификации: используй только колонки из профиля данных, "
                    "валидный chart_type и осмысленные x/y."
                )
            cfg = get_agent_config("chart_agent")
            prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}

=== FEW-SHOT EXAMPLES ===
{cfg.few_shot}

Вопрос: {inp.question}
Профиль данных (колонки, диапазоны, уникальные значения):
{profile_text}
Пример данных (первые строки + разнообразие регионов если есть): {sample}
Всего строк в результате: {len(data)}

ОБЯЗАТЕЛЬНО выбери МИНИМУМ 2-3 подходящих chart_type из: bar, grouped_bar, stacked_bar, line, area, scatter, waterfall, horizontal_bar, donut, kpi, heatmap, treemap.
Обязательно верни 2 или 3 разных графика, показывающих данные с разных ракурсов (например, график динамики + график структуры или рейтинга).
Заполни каждый ChartSpec полностью (title на русском, subtitle если нужно, x/y/color из доступных колонок, agg=sum/mean, insights 2-4 тезиса, rationale почему этот тип).
Заполняй action_title, show_average, highlight_category осмысленно (иначе null/false).

{retry_hint}

Верни JSON строго по схеме ChartList.
"""
            try:
                chart_list = call_structured(
                    prompt,
                    schema=ChartList,
                    system="Отвечай только валидным JSON по схеме ChartList. Все тексты на русском.",
                    agent_name=self.name,
                )
                specs = [normalize_chart_spec(c) for c in chart_list.charts]
                break
            except Exception as e:
                last_error = str(e)
                logger.info(
                    f"[ChartAgent] attempt {attempt + 1}/{self.max_retries} error: {last_error}"
                )

        if not specs:
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[ChartAgent] end_error: ({elapsed}ms)")
            raise RuntimeError(
                f"ChartAgent не смог получить спецификации графиков за {self.max_retries} попыток. "
                f"Последняя ошибка: {last_error}"
            )

        final_specs = []
        for spec in specs:
            highlight = getattr(spec, "highlight_category", None)
            if highlight and spec.color is not None:
                logger.info(
                    "[ChartAgent] highlight_category сброшен: несовместим с color=%s",
                    spec.color,
                )
                spec = spec.model_copy(update={"highlight_category": None})

            spec = repair_chart_spec(spec, data, question=inp.question)

            if spec.chart_type == "treemap" and data:
                cols = set(data[0].keys())
                n_unique = len({row.get(spec.x) for row in data if spec.x in cols})
                if n_unique <= 4:
                    logger.info(
                        "[ChartAgent] treemap при %d категориях (<=4) — допустимо, но bar/donut могли бы подойти",
                        n_unique,
                    )

            final_specs.append(spec)

        elapsed = int((time.time() - start) * 1000)
        types_str = ", ".join([s.chart_type for s in final_specs])
        logger.info(f"[ChartAgent] end: chart_types={types_str} ({elapsed}ms)")

        reasoning = f"Выбрано {len(final_specs)} графиков: " + ", ".join(
            [getattr(s, "rationale", "") for s in final_specs]
        )
        return ChartAgentResult(specs=final_specs, reasoning=reasoning)

    def run_input(self, inp: ChartAgentInput) -> ChartAgentResult:
        return self.run(inp.question, inp.data)
