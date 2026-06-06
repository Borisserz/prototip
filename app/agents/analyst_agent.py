"""AnalystAgent (Phase 3): вопрос + данные (из DataAgent) → AnalysisResult.

3-4 инсайта на русском, ключевой вывод, аномалия/тренд.
Через core/llm.py (structured output, temperature=0).
"""

from __future__ import annotations

import logging
import time

from app.agents.base_agent import BaseAgent
from app.agents.models import AnalysisResult, SqlResult
from core.llm import call_structured, setup_logging

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("AnalystAgent")

FEW_SHOT_ANALYSIS = """
Ты — аналитик налоговых данных Республики Беларусь (синтетический демо-датасет).

Пиши ТОЛЬКО на русском, чётко, без воды, 3-4 инсайта максимум.

ВАЖНО: используй ТОЛЬКО валюту «Br» (или «млн Br», «млрд Br»). НИКОГДА не пиши «руб.», «рублей», «миллион рублей» и т.п. — только Br.

Примеры хороших выводов:

Q: Динамика начислений по регионам
Данные (сэмпл): высокие значения в г. Минск, рост в конце года...
Анализ:
insights: ["г. Минск обеспечивает ~40% всех начислений", "В конце года наблюдается сезонный рост на 20-25% во всех регионах", "Гомельская область показала аномальный всплеск в сентябре (+42%)"]
key_conclusion: "г. Минск остаётся основным драйвером налоговых поступлений, при этом наблюдается общий положительный тренд к концу года."
anomaly_or_trend: "Аномальный рост в Гомельской области по НДС в сентябре требует дополнительной проверки."

Q: Задолженность по налогам
insights: ["Наибольшая задолженность сконцентрирована в Гомельской и Могилёвской областях", "По Подоходному налогу долг минимален — высокая собираемость", "Общая задолженность составляет примерно 15% от начислений"]
key_conclusion: "Основная проблема с собираемостью — в имущественных налогах и акцизах в восточных областях."
anomaly_or_trend: "В Витебской области долг по акцизам выше среднего в 1.8 раза."
"""


class AnalystAgent(BaseAgent):
    """Агент текстового анализа данных (инсайты на русском)."""

    name = "analyst_agent"
    description = "По вопросу и данным (списку записей) выдаёт 3-4 инсайта, ключевой вывод и аномалию/тренд на русском языке."

    def run(self, question: str, data: list[dict]) -> AnalysisResult:
        """Основной метод: вопрос + записи данных → AnalysisResult."""
        start = time.time()
        logger.info(f"[AnalystAgent] start: question={question[:60]}... rows={len(data)}")
        if not data:
            # graceful fallback — всегда возвращаем валидный AnalysisResult (минимум 3 insights)
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
                reasoning="Fallback: передан пустой data. Это может быть как отсутствие данных в датасете, так и проблема передачи контекста в многошаговом плане (см. 'Что было сделано'). Выводы минимальны, чтобы пайплайн не упал.",
            )

        sample = data[:8]  # лимитируем для промпта
        prompt = f"""Ты — аналитик налоговых поступлений Республики Беларусь по синтетическим данным.

{FEW_SHOT_ANALYSIS}

Оригинальный вопрос пользователя: {question}

Данные (первые строки + общее количество {len(data)}):
{sample}

Проанализируй данные и верни структурированный AnalysisResult:
- 3-4 инсайта (чёткие тезисы на русском)
- key_conclusion (главный вывод)
- anomaly_or_trend (если заметна аномалия или тренд, иначе null)

ВАЖНО: ВСЕГДА используй валюту «Br» (млн Br, млрд Br). Никогда не используй «руб.», «рублей» и т.п.

Отвечай строго в JSON по схеме AnalysisResult. Все тексты на русском языке.
"""

        try:
            analysis = call_structured(
                prompt,
                schema=AnalysisResult,
                system="Ты — точный аналитик. Выдавай только валидный JSON. Инсайты на русском, без воды, профессионально.",
            )
        except Exception as e:
            logger.info(f"[AnalystAgent] error: {e}")
            elapsed = int((time.time() - start) * 1000)
            logger.info(f"[AnalystAgent] end_fallback: ({elapsed}ms)")
            # friendly message, no raw traceback to user
            return AnalysisResult(
                insights=[
                    "Не удалось получить анализ от модели.",
                    "Возможно, проблема с доступностью Ollama или форматом ответа.",
                    "Попробуйте повторить запрос позже.",
                ],
                key_conclusion="Анализ временно недоступен из-за внутренней ошибки.",
                anomaly_or_trend=None,
                reasoning="Fallback: LLM structured call для AnalysisResult не удался. Возвращён безопасный AnalysisResult.",
            )
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[AnalystAgent] end: insights={len(analysis.insights)} ({elapsed}ms)")
        # Усиливаем reasoning (модель не всегда его заполняет в старых схемах)
        if not getattr(analysis, "reasoning", ""):
            analysis.reasoning = f"Проанализировано {len(data)} записей. Сформировано {len(analysis.insights)} инсайтов + ключевой вывод."
        return analysis

    def run_from_sql(self, question: str, sql_result: SqlResult) -> AnalysisResult:
        """Удобный метод для оркестратора: принимает SqlResult."""
        return self.run(question, sql_result.data)
