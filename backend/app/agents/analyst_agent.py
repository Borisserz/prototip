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
from app.data_sampling import format_data_for_llm
from app.domain.constants import CHART_TYPE_RU
from app.storytelling import enrich_analysis_explanation
from core.llm import call_structured, setup_logging

setup_logging()
logger = logging.getLogger("AnalystAgent")

from app.agents.config_loader import get_agent_config


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
        previous_feedback: str | None = None,
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
                success=False,
                degraded=True,
                reasoning="Fallback: передан пустой data. Выводы минимальны, чтобы пайплайн не упал.",
            )

        profile_text, sample_repr = format_data_for_llm(data, max_rows=12)
        chart_context = self._format_chart_context(chart_spec)
        data_context = self._format_data_context(
            source_sql=source_sql,
            drilldown_filters=drilldown_filters,
            row_count=len(data),
        )
        
        # Phase 18: Z-Score Anomaly Detection
        anomaly_context = ""
        try:
            import numpy as np
            import pandas as pd
            df = pd.DataFrame(data)
            num_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            if num_cols:
                for col in num_cols:
                    if len(df[col].dropna()) > 3:
                        z_scores = (df[col] - df[col].mean()) / df[col].std(ddof=0)
                        anomalies = df[np.abs(z_scores) > 2.5] # Ищем жесткие выбросы
                        if not anomalies.empty:
                            anomaly_context += f"\nВНИМАНИЕ! Математически обнаружена строгая статистическая аномалия (Z-score > 2.5) в колонке '{col}':\n"
                            for idx, row in anomalies.head(3).iterrows():
                                # Пытаемся найти текстовое описание (имя региона, налога)
                                text_cols = df.select_dtypes(exclude=[np.number]).columns.tolist()
                                desc = row[text_cols[0]] if text_cols else f"Индекс {idx}"
                                anomaly_context += f"- Объект '{desc}': Значение {row[col]} критически выбивается!\n"
                            anomaly_context += "ОБЯЗАТЕЛЬНО упомяни это в anomaly_or_trend с пометкой 🚨 СТАТИСТИЧЕСКАЯ АНОМАЛИЯ.\n"
        except Exception as e:
            logger.error(f"Ошибка Z-score: {e}")
        cfg = get_agent_config("analyst_agent")
        
        prompt = f"""Ты — {cfg.role}. {cfg.goal}

{cfg.rules}

=== FEW-SHOT EXAMPLES ===
{cfg.few_shot}

Оригинальный вопрос пользователя: {question}

Профиль данных:
{profile_text}
Репрезентативная выборка ({len(data)} строк всего):
{sample_repr}
{data_context}{chart_context}
{anomaly_context}
Проанализируй данные и верни структурированный AnalysisResult:
- 3-4 инсайта (чёткие тезисы на русском)
- key_conclusion (главный вывод; при наличии chart_spec/action_title — со ссылкой на визуализацию)
- data_explanation: одно короткое предложение на русском — как получены цифры (фильтры, группировка, агрегация). Без SQL-жаргона. null только если данных нет.
- anomaly_or_trend (если заметна аномалия или тренд, иначе null)
- follow_up_questions: ровно 2-3 коротких уточняющих вопроса на русском, которые пользователь логично задаст следующими, исходя из инсайтов (без воды, до 80 символов каждый)

Отвечай строго в JSON по схеме AnalysisResult. Все тексты на русском языке.
"""
        if previous_feedback:
            prompt += f"\n\n[ОБРАТНАЯ СВЯЗЬ ОТ REVIEWER AGENT]\nТвой предыдущий анализ был отклонен со следующей критикой:\n{previous_feedback}\nИсправь недочеты и сделай выводы более глубокими!\n"


        try:
            system_msg = (
                f"Ты — {cfg.role}. Выдавай только валидный JSON. "
                "Инсайты на русском, без воды, профессионально. "
                "Если тебе передан chart_spec (спецификация графика), ОБЯЗАТЕЛЬНО сделай 1-2 отсылки "
                "к визуализации в своих инсайтах. Например: «Как наглядно видно на круговой диаграмме...», "
                "«На линейном графике выделяется тренд...». Свяжи цифры с тем, как они визуализированы. "
                "Обязательно заполни data_explanation — простое объяснение происхождения цифр. "
                "Обязательно предложи 2-3 follow_up_questions — конкретные следующие шаги исследования."
            )
            analysis = call_structured(
                prompt,
                schema=AnalysisResult,
                system=system_msg,
                agent_name=self.name
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
                success=False,
                degraded=True,
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
