"""ForecastAnalystAgent (Phase 3): узел предиктивной аналитики.

Алгоритм (по плану):
  1. Исторические данные приходят из ClickHouse (SQL пишет DataAgent в data_node графа).
  2. Данные передаются НЕ в LLM, а в числовой скрипт прогнозирования
     (domain/forecasting.py на базе numpy/scipy/опц. statsmodels).
  3. Скрипт возвращает экстраполяцию (числа + доверительные интервалы + метрики).
  4. Агент-резюмизатор (LLM) описывает результат текстом.

Возвращает ForecastAnalystResult: числовой прогноз, нарратив, метрики и ChartSpec
(история + прогноз), а также augmented-данные для отрисовки графика.
Промпт резюмизатора берётся из центра управления промптами (agents.yaml ->
forecast_agent); при отсутствии — дефолтный.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.models import AgentResult
from core.models import ChartSpec
from domain import forecasting as fc

logger = logging.getLogger("ForecastAnalystAgent")


class ForecastAnalystResult(AgentResult):
    narrative: str = Field("", description="Текстовое описание прогноза (LLM)")
    method: str = Field("", description="Использованный метод прогнозирования")
    horizon: int = Field(0, description="Горизонт прогноза (число периодов)")
    forecast: list[dict[str, Any]] = Field(default_factory=list, description="Точки прогноза с ДИ")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Числовые метрики динамики")
    chart_spec: ChartSpec | None = Field(None, description="Спецификация графика (история+прогноз)")
    data: list[dict[str, Any]] = Field(default_factory=list, description="История+прогноз для графика")


class _Narrative(BaseModel):
    narrative: str = Field(..., description="Деловое описание прогноза на русском (2-4 предложения)")


class ForecastAnalystAgent(BaseAgent):
    name = "forecast_analyst_agent"
    description = (
        "Предиктивная аналитика: численная экстраполяция исторических данных "
        "(numpy/scipy/statsmodels) + текстовое резюме прогноза от LLM."
    )

    def run(
        self,
        question: str,
        data: list[dict] | None = None,
        horizon: int = 3,
        **kwargs: Any,
    ) -> ForecastAnalystResult:
        rows = data or []
        if not rows:
            return ForecastAnalystResult(
                success=False,
                error="Нет исторических данных для прогноза",
                reasoning="Пустой датасет — нечего экстраполировать.",
            )

        try:
            df = pd.DataFrame(rows)
            t_col, v_col = fc.detect_time_value_columns(rows)
            if t_col is None or v_col is None:
                return ForecastAnalystResult(
                    success=False,
                    error="Не удалось определить колонки периода/значения",
                    reasoning="Нет подходящих колонок для временного ряда.",
                )

            # числовая колонка -> float
            df[v_col] = pd.to_numeric(
                df[v_col].astype(str).str.replace(" ", "").str.replace(",", "."),
                errors="coerce",
            )
            df = df.dropna(subset=[v_col])
            # сортировка по периоду (как строка/дата)
            with contextlib.suppress(Exception):
                df = df.sort_values(by=t_col).reset_index(drop=True)

            values = df[v_col].tolist()
            labels = [str(x) for x in df[t_col].tolist()]

            result = fc.forecast_series(values, horizon=horizon, labels=labels)

            # данные для графика (история + прогноз)
            combined = result.combined_rows(label_key=t_col, value_key=v_col)

            chart_spec = ChartSpec(
                chart_type="area",
                title=f"Прогноз: {v_col}",
                subtitle=f"Метод: {result.method}, горизонт: {horizon}",
                x=t_col,
                y=v_col,
                rationale=(
                    f"Экстраполяция {len(values)} исторических точек на {horizon} "
                    f"периодов вперёд методом '{result.method}'."
                ),
            )

            narrative = self._summarize(question, result, t_col, v_col)

            return ForecastAnalystResult(
                success=True,
                narrative=narrative,
                method=result.method,
                horizon=horizon,
                forecast=[
                    {"period": p.label, "value": p.value, "lower": p.lower, "upper": p.upper}
                    for p in result.forecast
                ],
                metrics=result.metrics,
                chart_spec=chart_spec,
                data=combined,
                reasoning=(
                    f"Прогноз построен методом '{result.method}' по {len(values)} точкам; "
                    f"рост к последнему факту: {result.metrics.get('growth_pct', 0):.1f}%."
                ),
            )
        except Exception as e:  # noqa: BLE001
            logger.error("ForecastAnalystAgent error: %s", e)
            return ForecastAnalystResult(
                success=False, error=str(e), reasoning="Ошибка в вычислениях прогноза."
            )

    # ── LLM-резюмизатор ─────────────────────────────────────────────────────────
    def _summarize(self, question: str, result: fc.ForecastResult, t_col: str, v_col: str) -> str:
        facts = self._facts_block(result, t_col, v_col)
        system, extra = self._load_prompt()
        prompt = (
            f"{extra}\n\n"
            f"Запрос пользователя: {question}\n\n"
            f"Числовые результаты прогноза (НЕ выдумывай других чисел, опирайся только на них):\n{facts}\n\n"
            "Опиши прогноз деловым языком на русском (2-4 предложения): тренд, ожидаемые значения "
            "и темпы роста/падения, уровень неопределённости. Без вступлений."
        )
        try:
            from core.llm import call_structured

            res = call_structured(
                prompt, schema=_Narrative, system=system, agent_name=self.name
            )
            if res.narrative.strip():
                return res.narrative.strip()
        except Exception as e:  # noqa: BLE001
            logger.info("ForecastAnalystAgent: LLM недоступна (%s), дефолтный нарратив", e)
        return self._fallback_narrative(result, v_col)

    def _facts_block(self, result: fc.ForecastResult, t_col: str, v_col: str) -> str:
        lines = [
            f"- Показатель: {v_col}; период: {t_col}",
            f"- Метод: {result.method}; сезонность: {'да' if result.seasonal else 'нет'}",
            f"- Последнее факт. значение: {result.metrics.get('last_value')}",
            f"- Среднее по истории: {result.metrics.get('mean_history'):.2f}"
            if result.metrics.get("mean_history") is not None
            else "",
            f"- Прогноз на конец горизонта: {result.metrics.get('forecast_last'):.2f}"
            if result.metrics.get("forecast_last") is not None
            else "",
            f"- Изменение к последнему факту: {result.metrics.get('growth_pct', 0):.1f}% "
            f"({result.metrics.get('growth_abs', 0):+.2f})",
        ]
        if "r2" in result.metrics:
            lines.append(f"- Качество линейной аппроксимации R²: {result.metrics['r2']:.3f}")
        lines.append("- Прогнозные точки (период: значение [нижн.; верхн.]):")
        for p in result.forecast:
            lines.append(f"    {p.label}: {p.value:.2f} [{p.lower:.2f}; {p.upper:.2f}]")
        return "\n".join(x for x in lines if x)

    def _fallback_narrative(self, result: fc.ForecastResult, v_col: str) -> str:
        g = result.metrics.get("growth_pct", 0.0)
        direction = "рост" if g > 1 else "снижение" if g < -1 else "стабилизация"
        last = result.forecast[-1].value if result.forecast else result.metrics.get("last_value", 0)
        return (
            f"Прогноз показателя «{v_col}» указывает на {direction}: к концу горизонта "
            f"ожидается значение около {last:.2f} ({g:+.1f}% к последнему факту). "
            f"Оценка получена методом '{result.method}'; учитывайте доверительный интервал "
            f"как меру неопределённости."
        )

    def _load_prompt(self) -> tuple[str, str]:
        """Берёт промпт из центра управления (agents.yaml -> forecast_agent)."""
        default_system = "Ты — аналитик-прогнозист. Опиши числовой прогноз, не выдумывая данных. Отвечай строго JSON."
        try:
            from app.agents.config_loader import get_agent_config

            cfg = get_agent_config("forecast_agent")
            system = f"{cfg.role}. {cfg.goal}".strip()
            extra = cfg.rules or ""
            return system or default_system, extra
        except Exception:
            return default_system, ""

    def get_capabilities(self) -> dict[str, Any]:
        caps = super().get_capabilities()
        caps["outputs"] = ["forecast_numbers", "narrative", "chart_spec"]
        caps["engine"] = "domain/forecasting.py (numpy/scipy/statsmodels)"
        return caps
