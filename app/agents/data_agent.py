"""DataAgent (Phase 2): вопрос на русском → безопасный SELECT SQL + данные через DuckDB.

Только SELECT + LIMIT (авто-добавляем если нет), белый список колонок.
Few-shot + self-correction (до 3 попыток при ошибке выполнения).
LLM-вызовы — строго через core.llm (structured, temp=0).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import duckdb
import pandas as pd
from pydantic import BaseModel, Field

from app.agents.base import BaseAgent
from app.schemas import DataAgentInput, SqlResult
from core.llm import call_structured, setup_logging

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("DataAgent")

# Колонки датасета (белый список)
ALLOWED_COLUMNS = {
    "period",
    "region",
    "tax_type",
    "accrued",
    "paid",
    "debt",
    "taxpayers",
}

DATA_PATH = Path("data/sample.csv")

# Few-shot примеры (хорошие запросы для белорусских данных)
FEW_SHOT = """
Важное правило для фильтрации по году: колонка period — строка формата 'YYYY-MM'.
Для фильтра по году используй period LIKE '2024-%' (или substr(period,1,4)='2024').
НЕ используй period = '2024' и НЕ YEAR(period) / EXTRACT(YEAR FROM period).

Примеры хороших запросов (только SELECT, с LIMIT):

Q: Какие регионы имеют наибольшую задолженность по НДС?
SQL: SELECT region, SUM(debt) as total_debt FROM df WHERE tax_type = 'НДС' GROUP BY region ORDER BY total_debt DESC LIMIT 10

Q: Динамика начислений по г. Минск за все месяцы?
SQL: SELECT period, SUM(accrued) as total_accrued FROM df WHERE region = 'г. Минск' GROUP BY period ORDER BY period LIMIT 20

Q: Сколько налогоплательщиков в среднем по областям?
SQL: SELECT region, AVG(taxpayers) as avg_taxpayers FROM df GROUP BY region ORDER BY avg_taxpayers DESC LIMIT 10

Q: Топ-3 региона по задолженности в 2024?
SQL: SELECT region, SUM(debt) as total_debt FROM df WHERE period LIKE '2024-%' GROUP BY region ORDER BY total_debt DESC LIMIT 3

# Примечание: алиасы total_debt / total_accrued и т.п. — источник возможных английских лейблов в ChartSpec.y.
# Обработка в viz/style.py:get_russian_label (стрип префиксов + fallback) + в viz/charts (conditional labels).
# Всегда возвращаем данные с алиасами как есть; RU-лейблы на этапе viz.
"""


class _SqlOnly(BaseModel):
    """Внутренняя схема для LLM: только SQL строка."""

    sql: str = Field(..., description="Только SELECT запрос, без объяснений")


class DataAgent(BaseAgent):
    """Агент Text-to-SQL по sample.csv (DuckDB)."""

    name = "data_agent"
    max_retries = 3

    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self._df: pd.DataFrame | None = None

    def _load_df(self) -> pd.DataFrame:
        if self._df is None:
            if not DATA_PATH.exists():
                raise FileNotFoundError(
                    "data/sample.csv не найден. Запусти python data/make_dataset.py"
                )
            self._df = pd.read_csv(DATA_PATH)
        return self._df

    def _execute_sql(self, sql: str) -> list[dict]:
        """Безопасное выполнение: только SELECT, регистрируем df, добавляем LIMIT если нужно."""
        sql = sql.strip().rstrip(";")
        if not sql.lower().startswith("select"):
            raise ValueError("Разрешены только SELECT запросы")

        # Авто LIMIT если отсутствует (защита)
        if "limit" not in sql.lower():
            sql = sql + " LIMIT 500"

        df = self._load_df()
        con = duckdb.connect()
        con.register("df", df)
        try:
            result = con.execute(sql).fetchdf()
            return result.to_dict(orient="records")
        finally:
            con.close()

    def _build_prompt(self, question: str, previous_error: str | None = None) -> str:
        schema_info = f"Доступные колонки: {', '.join(sorted(ALLOWED_COLUMNS))}. Таблица: df (pandas + duckdb)."
        prompt = f"""Ты — эксперт по SQL для аналитики налогов в Республике Беларусь (синтетические данные).

{schema_info}

Пиши ТОЛЬКО валидный SELECT (DuckDB совместимый). Используй точные имена колонок. Добавляй LIMIT если нужно (макс 1000 строк).

Правило для года: period LIKE 'YYYY-%' (например '2024-%') или substr(period,1,4)='2024'. Никогда не period = '2024' и не YEAR(period).

{FEW_SHOT}

Вопрос пользователя: {question}
"""
        if previous_error:
            prompt += f"\nПредыдущий SQL вызвал ошибку: {previous_error}\nИсправь запрос и верни только корректный SQL."
        prompt += '\nВерни JSON строго по схеме: {"sql": "..."}'
        return prompt

    def run(self, question: str) -> SqlResult:
        """Основной вход: вопрос → (sql, data). С self-correction."""
        start = time.time()
        logger.info(f"[DataAgent] start: question={question[:60]}...")
        inp = DataAgentInput(question=question)
        last_error: str | None = None

        for attempt in range(self.max_retries):
            prompt = self._build_prompt(inp.question, last_error)
            try:
                sql_obj = call_structured(prompt, schema=_SqlOnly, model=self.model)
                sql = sql_obj.sql.strip()

                # Валидация whitelist (грубая)
                lowered = sql.lower()
                for bad in ("insert", "update", "delete", "drop", "create", "alter", ";--"):
                    if bad in lowered:
                        raise ValueError(f"Запрещённая операция в SQL: {bad}")

                data = self._execute_sql(sql)
                elapsed = int((time.time() - start) * 1000)
                logger.info(f"[DataAgent] end: rows={len(data)} sql_len={len(sql)} ({elapsed}ms)")
                return SqlResult(sql=sql, data=data, row_count=len(data))

            except Exception as e:
                last_error = str(e)
                if attempt == self.max_retries - 1:
                    elapsed = int((time.time() - start) * 1000)
                    logger.info(f"[DataAgent] error: {last_error} ({elapsed}ms)")
                    raise RuntimeError(
                        f"DataAgent не смог сгенерировать корректный SQL за {self.max_retries} попыток. Последняя ошибка: {last_error}"
                    ) from e

        # unreachable
        raise RuntimeError("DataAgent internal error")

    def run_input(self, inp: DataAgentInput) -> SqlResult:
        return self.run(inp.question)
