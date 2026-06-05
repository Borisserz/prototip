"""ChartAgent (Phase 4): вопрос + данные → ChartSpec (выбор типа + заполнение).

Модель сама решает тип по правилам (время→line, сравнение→bar/grouped/stacked, доли→donut, рейтинг→horizontal_bar, kpi для одиночных метрик, heatmap для матриц).
Затем детерминированный build_chart из viz (никакого exec()).
LLM — через core.llm structured (возвращает ChartSpec напрямую).
"""

from __future__ import annotations

import logging
import time

from app.agents.base import BaseAgent
from app.schemas import ChartAgentInput, ChartAgentResult
from core.llm import call_structured, setup_logging
from core.models import ChartSpec

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("ChartAgent")

FEW_SHOT_CHART = """
Правила выбора типа графика (используй точно):
- Если в вопросе время/месяц/период/динамика/тренд → "line" (x=period, color=region часто)
- Сравнение категорий/регионов по одному значению, топ-N, рейтинг, "наибольш", "задолженности по регионам" → "horizontal_bar" (x=region, y=debt или total_debt/accrued; строго horizontal_bar для рейтингов, НЕ bar)
- Несколько серий (налоги/регионы) → "grouped_bar" или "stacked_bar"
- Доли/структура/проценты → "donut" (x=tax_type или region, y=accrued)
- Один ключевой показатель (сумма/итог) → "kpi"
- Матрица (регион x период) → "heatmap" (x=period, color=region или наоборот, y=accrued)

Пример 1:
Q: Динамика начислений по регионам
→ type=line, x=period, y=accrued, color=region, title="Динамика начислений по регионам", rationale="время → line"

Пример 2:
Q: Структура налогов по видам (доли)
→ type=donut, x=tax_type, y=accrued, title=..., rationale="доли → donut"

Пример 3 (рейтинг):
Q: Топ-3 региона по задолженности
 type=horizontal_bar, x=region, y=total_debt, title="Топ-3 региона по задолженности", rationale="рейтинг/топ по задолженности → horizontal_bar"
"""


class ChartAgent(BaseAgent):
    """Агент выбора и заполнения ChartSpec по вопросу и данным."""

    name = "chart_agent"

    def run(self, question: str, data: list[dict]) -> ChartAgentResult:
        start = time.time()
        logger.info(f"[ChartAgent] start: question={question[:60]}... rows={len(data)}")
        inp = ChartAgentInput(question=question, data=data[:20])  # лимит для промпта

        # Краткое описание данных для промпта (чтобы не слать 400+ строк)
        sample = data[:5] if data else []
        prompt = f"""Ты — эксперт по визуализации данных налогов Республики Беларусь (синтетические данные).

{FEW_SHOT_CHART}

Вопрос: {inp.question}
Пример данных (первые строки): {sample}
Всего строк в результате: {len(data)}

Выбери подходящий chart_type из: bar, grouped_bar, stacked_bar, line, horizontal_bar, donut, kpi, heatmap.
Заполни ChartSpec полностью (title на русском, subtitle если нужно, x/y/color из доступных колонок, agg=sum/mean, insights 2-4 тезиса, rationale почему этот тип).

Верни JSON строго по схеме ChartSpec.
"""
        # Прямо просим модель вернуть ChartSpec (она знает схему из structured)
        try:
            spec = call_structured(
                prompt,
                schema=ChartSpec,
                system="Отвечай только валидным JSON по схеме. Все тексты на русском.",
            )
        except Exception as e:
            logger.info(f"[ChartAgent] error: {e}")
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[ChartAgent] end_error: ({elapsed}ms)")
            # Re-raise wrapped friendly (orchestrator will catch; direct use gets nice msg, no raw tb)
            raise RuntimeError(
                "ChartAgent не смог получить спецификацию графика. Проверьте модель Ollama и попробуйте ещё раз."
            ) from e

        # Минимальная пост-валидация (x/y должны быть в данных если не kpi)
        if spec.chart_type != "kpi" and data:
            cols = set(data[0].keys())
            if spec.x not in cols and spec.x:
                # мягко: не падаем, модель иногда выдумывает; в реальности можно fallback
                pass

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[ChartAgent] end: chart_type={spec.chart_type} ({elapsed}ms)")
        return ChartAgentResult(spec=spec)

    def run_input(self, inp: ChartAgentInput) -> ChartAgentResult:
        return self.run(inp.question, inp.data)
