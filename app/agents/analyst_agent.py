"""AnalystAgent (Phase 3): вопрос + данные (из DataAgent) → AnalysisResult.

3-4 инсайта на русском, ключевой вывод, аномалия/тренд.
Опционально принимает chart_spec для связного нарратива с визуализацией (Diamond-паттерн).
Через core/llm.py (structured output, temperature=0).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.agents.base_agent import BaseAgent
from app.agents.models import AnalysisResult, SqlResult
from app.storytelling import enrich_analysis_explanation
from core.llm import call_structured, setup_logging

setup_logging()
logger = logging.getLogger("AnalystAgent")

CHART_TYPE_RU: dict[str, str] = {
    "bar": "столбчатой диаграмме",
    "grouped_bar": "группированной столбчатой диаграмме",
    "stacked_bar": "стековой столбчатой диаграмме",
    "line": "линейном графике",
    "area": "диаграмме с заливкой (area)",
    "scatter": "точечной диаграмме",
    "waterfall": "водопадной диаграмме",
    "horizontal_bar": "горизонтальной столбчатой диаграмме",
    "donut": "круговой (donut) диаграмме",
    "kpi": "KPI-индикаторе",
    "heatmap": "тепловой карте",
    "treemap": "древовидной диаграмме (treemap)",
}

FEW_SHOT_ANALYSIS = """
Ты — аналитик налоговых данных Республики Беларусь (синтетический демо-датасет). Ты работаешь как модуль в цепочке агентов: DataAgent уже подготовил данные, ChartAgent мог построить визуализацию. Не запрашивай новые данные и не описывай SQL, анализируй только переданный data.

Пиши ТОЛЬКО на русском, чётко, без воды, 3-4 инсайта максимум.

ВАЖНО: используй ТОЛЬКО валюту «Br» (или «млн Br», «млрд Br»). НИКОГДА не пиши «руб.», «рублей», «миллион рублей» и т.п. — только Br.

**Если передан chart_spec** — обязательно свяжи выводы с визуализацией:
- В одном из insights или в key_conclusion добавь отсылку к типу графика и его заголовку.
- Примеры: "Как наглядно видно на горизонтальной столбчатой диаграмме «Топ регионов по задолженности»...", "Линейный график подтверждает сезонный рост к концу года...".
- Не описывай технические поля spec (x, y, agg) — говори о смысле графика для пользователя.

Примеры хороших выводов:

Q: Динамика начислений по регионам
Данные (сэмпл): высокие значения в г. Минск, рост в конце года...
Анализ:
insights: ["г. Минск обеспечивает ~40% всех начислений", "В конце года наблюдается сезонный рост на 20-25% во всех регионах", "Гомельская область показала аномальный всплеск в сентябре (+42%)"]
key_conclusion: "г. Минск остаётся основным драйвером налоговых поступлений, при этом наблюдается общий положительный тренд к концу года."
anomaly_or_trend: "Аномальный рост в Гомельской области по НДС в сентябре требует дополнительной проверки."
follow_up_questions: ["Какая динамика начислений в Гомельской области по месяцам?", "Сравни задолженность Гомельской и Минской областей", "Какие виды налогов дают основной вклад в аномалию?"]

Q: Задолженность по налогам (с chart_spec: horizontal_bar, title="Топ регионов по задолженности")
insights: ["Наибольшая задолженность сконцентрирована в Гомельской и Могилёвской областях", "Как видно на горизонтальной столбчатой диаграмме, разрыв между лидером и аутсайдером превышает 2:1", "По Подоходному налогу долг минимален — высокая собираемость"]
key_conclusion: "Горизонтальная диаграмма наглядно показывает: основная проблема с собираемостью — в имущественных налогах восточных областей."
anomaly_or_trend: "В Витебской области долг по акцизам выше среднего в 1.8 раза."
follow_up_questions: ["Покажи структуру долга в Гомельской области по видам налогов", "Динамика задолженности лидера по месяцам", "Топ-3 региона с наименьшей задолженностью"]

Q: Начисления в г. Минск по видам налогов
data_explanation: "Данные отфильтрованы по г. Минск и сгруппированы по видам налогов, агрегированы суммой."
insights: ["НДС даёт основной вклад в начисления", "Подоходный налог стабилен по месяцам", "Имущественные налоги — меньшая доля"]
key_conclusion: "В г. Минск доминирует НДС среди всех видов налогов."
"""


class AnalystAgent(BaseAgent):
    """Агент текстового анализа данных (инсайты на русском)."""

    name = "analyst_agent"
    description = (
        "По вопросу и данным выдаёт 3-4 инсайта, ключевой вывод и аномалию/тренд. "
        "При наличии chart_spec связывает выводы с визуализацией на экране пользователя."
    )

    def _format_chart_context(self, chart_spec: dict[str, Any] | None) -> str:
        if not chart_spec:
            return ""
        ctype = str(chart_spec.get("chart_type") or "")
        title = str(chart_spec.get("title") or "без заголовка")
        action_title = str(chart_spec.get("action_title") or "")
        ctype_ru = CHART_TYPE_RU.get(ctype, "диаграмме")
        action_hint = (
            f"- Говорящий заголовок (action_title): «{action_title}» — используй в key_conclusion.\n"
            if action_title
            else ""
        )
        return (
            f"\n\nСпецификация графика (chart_spec от ChartAgent):\n"
            f"{chart_spec}\n"
            f"- Тип: {ctype} ({ctype_ru}), заголовок на экране: «{title}»\n"
            f"{action_hint}"
            f"- ОБЯЗАТЕЛЬНО сделай 1-2 отсылки к этой визуализации в insights или key_conclusion.\n"
        )

    def _format_data_context(
        self,
        *,
        source_sql: str | None,
        drilldown_filters: dict[str, str] | None,
        row_count: int,
    ) -> str:
        parts: list[str] = []
        if drilldown_filters:
            filters_ru = ", ".join(f"{k}={v}" for k, v in drilldown_filters.items())
            parts.append(f"Активные фильтры drill-down: {filters_ru}.")
        if source_sql:
            parts.append(f"SQL-запрос (для справки, не цитируй дословно): {source_sql[:300]}")
        parts.append(f"Всего строк в выборке: {row_count}.")
        if not parts:
            return ""
        return "\n\nКонтекст получения данных:\n" + "\n".join(parts) + "\n"

    def run(
        self,
        question: str,
        data: list[dict],
        chart_spec: dict | None = None,
        source_sql: str | None = None,
        drilldown_filters: dict[str, str] | None = None,
    ) -> AnalysisResult:
        """Основной метод: вопрос + записи данных [+ chart_spec] → AnalysisResult."""
        start = time.time()
        logger.info(
            f"[AnalystAgent] start: question={question[:60]}... rows={len(data)} "
            f"has_chart_spec={chart_spec is not None}"
        )
        if not data:
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[AnalystAgent] end: no_data_fallback ({elapsed}ms)")
            return AnalysisResult(
                insights=[
                    "Для данного вопроса не удалось получить строки данных для анализа.",
                    "Возможно, данные не были переданы между шагами плана, или фильтры в запросе слишком строгие, или за указанный период данные отсутствуют в датасете.",
                    "Попробуйте переформулировать вопрос или уточнить период/регион/налог.",
                ],
                key_conclusion="Нет данных для формирования выводов.",
                anomaly_or_trend=None,
                follow_up_questions=[
                    "Какая задолженность по регионам за последний год?",
                    "Покажи динамику начислений в г. Минск",
                ],
                reasoning="Fallback: передан пустой data. Выводы минимальны, чтобы пайплайн не упал.",
            )

        sample = data[:8]
        chart_context = self._format_chart_context(chart_spec)
        data_context = self._format_data_context(
            source_sql=source_sql,
            drilldown_filters=drilldown_filters,
            row_count=len(data),
        )
        prompt = f"""Ты — аналитик налоговых поступлений Республики Беларусь по синтетическим данным. Ты модуль в мультиагентном пайплайне: получаешь записи от DataAgent и (опционально) ChartSpec от ChartAgent. Возвращай только структурированный AnalysisResult.

{FEW_SHOT_ANALYSIS}

Оригинальный вопрос пользователя: {question}

Данные (первые строки + общее количество {len(data)}):
{sample}
{data_context}{chart_context}
Проанализируй данные и верни структурированный AnalysisResult:
- 3-4 инсайта (чёткие тезисы на русском)
- key_conclusion (главный вывод; при наличии chart_spec/action_title — со ссылкой на визуализацию)
- data_explanation: одно короткое предложение на русском — как получены цифры (фильтры, группировка, агрегация). Без SQL-жаргона. null только если данных нет.
- anomaly_or_trend (если заметна аномалия или тренд, иначе null)
- follow_up_questions: ровно 2-3 коротких уточняющих вопроса на русском, которые пользователь логично задаст следующими, исходя из инсайтов (без воды, до 80 символов каждый)

ВАЖНО: ВСЕГДА используй валюту «Br» (млн Br, млрд Br). Никогда не используй «руб.», «рублей» и т.п.

Отвечай строго в JSON по схеме AnalysisResult. Все тексты на русском языке.
"""

        try:
            analysis = call_structured(
                prompt,
                schema=AnalysisResult,
                system=(
                    "Ты — точный аналитик. Выдавай только валидный JSON. "
                    "Инсайты на русском, без воды, профессионально. "
                    "Если тебе передан chart_spec (спецификация графика), ОБЯЗАТЕЛЬНО сделай 1-2 отсылки "
                    "к визуализации в своих инсайтах. Например: «Как наглядно видно на круговой диаграмме...», "
                    "«На линейном графике выделяется тренд...». Свяжи цифры с тем, как они визуализированы. "
                    "Обязательно заполни data_explanation — простое объяснение происхождения цифр. "
                    "Обязательно предложи 2-3 follow_up_questions — конкретные следующие шаги исследования."
                ),
            )
        except Exception as e:
            logger.info(f"[AnalystAgent] error: {e}")
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[AnalystAgent] end_fallback: ({elapsed}ms)")
            return AnalysisResult(
                insights=[
                    "Не удалось получить анализ от модели.",
                    "Возможно, проблема с доступностью Ollama или форматом ответа.",
                    "Попробуйте повторить запрос позже.",
                ],
                key_conclusion="Анализ временно недоступен из-за внутренней ошибки.",
                anomaly_or_trend=None,
                follow_up_questions=[],
                reasoning="Fallback: LLM structured call для AnalysisResult не удался.",
            )
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[AnalystAgent] end: insights={len(analysis.insights)} ({elapsed}ms)")
        if not getattr(analysis, "reasoning", ""):
            suffix = " + связь с визуализацией" if chart_spec else ""
            analysis.reasoning = (
                f"Проанализировано {len(data)} записей. "
                f"Сформировано {len(analysis.insights)} инсайтов + ключевой вывод{suffix}."
            )
        return enrich_analysis_explanation(
            analysis,
            sql=source_sql,
            drilldown_filters=drilldown_filters,
            spec=chart_spec,
            row_count=len(data),
        )

    def run_from_sql(self, question: str, sql_result: SqlResult) -> AnalysisResult:
        """Удобный метод для оркестратора: принимает SqlResult."""
        return self.run(question, sql_result.data)
