"""ChartAgent (Phase 4): вопрос + данные → ChartSpec (выбор типа + заполнение).

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

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("ChartAgent")

FEW_SHOT_CHART = """
Ты — модуль визуализации в мультиагентной цепочке. DataAgent уже подготовил данные, PlannerAgent может запускать тебя параллельно с AnalystAgent. Не запрашивай новые данные, не генерируй SQL и не пиши код графика. Верни только ChartSpec.

Правила выбора типа графика (используй точно):
- Если в вопросе время/месяц/период/динамика/тренд → "line" (x=period, color=region часто)
- Плавная заливка под линией (накопительная динамика, заполненная область) → "area"
- Точки без соединения (распределение, корреляции, отдельные наблюдения) → "scatter"
- Сравнение категорий/регионов по одному значению, топ-N, рейтинг, "наибольш", "задолженности по регионам" → "horizontal_bar" (x=region, y=debt или total_debt/accrued; строго horizontal_bar для рейтингов, НЕ bar)
- Несколько серий (налоги/регионы) → "grouped_bar" или "stacked_bar"
- Доли/структура/проценты → "donut" (x=tax_type или region, y=accrued)
- Один ключевой показатель (сумма/итог) → "kpi"
- Матрица (регион x период) → "heatmap" (x=period, color=region или наоборот, y=accrued)
- Иерархическая структура / состав при >4 категориях → "treemap" (x=верхний уровень, color=второй уровень опционально, y=мера)

**Data Storytelling (новые поля ChartSpec):**
- action_title: говорящий бизнес-вывод для заголовка («Гомельская область — лидер по задолженности»). title остаётся описательным.
- show_average=true: при сравнении категорий/рейтингах (single-series bar/horizontal_bar/line/area).
- highlight_category: акцент одной категории (только если color=null).

Пример 1:
Q: Динамика начислений по регионам
→ type=line, x=period, y=accrued, color=region, title="Динамика начислений по регионам", rationale="время → line"

Пример 2:
Q: Структура налогов по видам (доли)
→ type=donut, x=tax_type, y=accrued, title=..., rationale="доли → donut"

Пример 3 (рейтинг):
Q: Топ-3 региона по задолженности
 type=horizontal_bar, x=region, y=total_debt, title="Топ-3 региона по задолженности", rationale="рейтинг/топ по задолженности → horizontal_bar"

Пример 4 (накопительная динамика с заливкой):
Q: Как менялась общая задолженность по месяцам
 type=area, x=period, y=debt, title="Накопительная динамика задолженности", rationale="сглаженная накопительная динамика → area"

Пример 5 (корреляция / распределение):
Q: Зависимость между начислениями и задолженностью по регионам
 type=scatter, x=accrued, y=debt, color=region, title="Корреляция начислений и долга", rationale="распределение и корреляция → scatter"

Пример 6 (водопад изменений):
Q: Изменения в задолженности: начисления - уплата - остаток
 type=waterfall, x=step, y=change, title="Водопад задолженности", rationale="показать приросты/спады → waterfall"

Пример 7 (treemap — структура):
Q: Структура начислений по регионам и видам налогов
 type=treemap, x=region, color=tax_type, y=accrued, title="Структура начислений", action_title="г. Минск доминирует в общем объёме начислений", rationale="иерархия >4 категорий → treemap"

Пример 8 (рейтинг + storytelling):
Q: Регионы по задолженности — выделить Гомельскую область
 type=horizontal_bar, x=region, y=debt, show_average=true, highlight_category="Гомельская область", title="Задолженность по регионам", action_title="Гомельская область превышает средний уровень задолженности", rationale="сравнение + акцент → horizontal_bar + show_average + highlight"
"""


class ChartAgent(BaseAgent):
    """Агент выбора и заполнения ChartSpec по вопросу и данным."""

    name = "chart_agent"
    description = "По вопросу + данным выбирает тип графика (line/bar/donut/... по эвристикам) и заполняет ChartSpec (structured). Рендер — всегда через viz/charts.py."

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

        prompt = f"""Ты — эксперт по визуализации данных налогов Республики Беларусь (синтетические данные). Ты работаешь как tool-agent: на входе вопрос и готовые records, на выходе только спецификация ChartSpec для детерминированного рендера в viz/charts.py.

{FEW_SHOT_CHART}

Вопрос: {inp.question}
Профиль данных (колонки, диапазоны, уникальные значения):
{profile_text}
Пример данных (первые строки + разнообразие регионов если есть): {sample}
Всего строк в результате: {len(data)}

Выбери подходящий chart_type из: bar, grouped_bar, stacked_bar, line, area, scatter, waterfall, horizontal_bar, donut, kpi, heatmap, treemap.
Заполни ChartSpec полностью (title на русском, subtitle если нужно, x/y/color из доступных колонок, agg=sum/mean, insights 2-4 тезиса, rationale почему этот тип).
Заполняй action_title, show_average, highlight_category осмысленно (иначе null/false).

**Правила для новых типов (Phase 2):**
- Если динамика с накоплением, сглаживанием или нужно показать "площадь под кривой" → area (часто с color=region для нескольких серий).
- Если нужно показать распределение точек, корреляцию двух показателей, кластеры или отдельные значения без линий → scatter (x и y — две разные метрики, color опционально для категорий).
- Для водопада изменений (накопительные приросты/спады, напр. начисления → уплата → остаток) → waterfall (x=шаги, y=изменения).
- Для вопросов с "по регионам" + время/динамика и колонкой region — для line/area обязательно используй color="region".

**Важное правило для вопросов с "по регионам" или "динамика по регионам":**
Если в вопросе явно про регионы + время/динамика и в данных есть колонка "region" — для line/area **обязательно** ставь color="region".
Это позволит нарисовать отдельную линию/область на каждый регион. Не агрегируй всё в одну линию, если вопрос просит "по регионам".

Верни JSON строго по схеме ChartSpec.
"""
        # Прямо просим модель вернуть ChartSpec (она знает схему из structured)
        try:
            spec = normalize_chart_spec(
                call_structured(
                    prompt,
                    schema=ChartSpec,
                    system="Отвечай только валидным JSON по схеме. Все тексты на русском.",
                )
            )
        except Exception as e:
            logger.info(f"[ChartAgent] error: {e}")
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[ChartAgent] end_error: ({elapsed}ms)")
            # Re-raise wrapped friendly (orchestrator will catch; direct use gets nice msg, no raw tb)
            raise RuntimeError(
                "ChartAgent не смог получить спецификацию графика. Проверьте модель Ollama и попробуйте ещё раз."
            ) from e

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

        # Минимальная пост-валидация (x/y должны быть в данных если не kpi)
        if spec.chart_type != "kpi" and data:
            cols = set(data[0].keys())
            if spec.x not in cols and spec.x:
                # мягко: не падаем, модель иногда выдумывает; в реальности можно fallback
                pass

        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[ChartAgent] end: chart_type={spec.chart_type} ({elapsed}ms)")
        # Минимальное изменение: заполняем reasoning из rationale модели (spec-first принцип)
        reasoning = (
            getattr(spec, "rationale", None)
            or "Модель выбрала тип графика по правилам FEW_SHOT и заполнила ChartSpec."
        )
        return ChartAgentResult(spec=spec, reasoning=reasoning)

    def run_input(self, inp: ChartAgentInput) -> ChartAgentResult:
        return self.run(inp.question, inp.data)
