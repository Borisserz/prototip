"""Orchestrator (Phase 5): единая точка входа ask(question).

Прогоняет полный пайплайн:
DataAgent → AnalystAgent → ChartAgent → build_chart + export_png (в out/)

Возвращает AskResult со всеми артефактами.
Обработка ошибок на каждом шаге (не роняем весь пайплайн).
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

import pandas as pd

from app.agents.analyst_agent import AnalystAgent
from app.agents.chart_agent import ChartAgent
from app.agents.data_agent import DataAgent
from app.schemas import AskResult, SqlResult
from core.llm import setup_logging
from viz.charts import build_chart, export_png

# Ensure central logging
setup_logging()
logger = logging.getLogger("Orchestrator")


class Orchestrator:
    """Оркестратор полного цикла анализа + визуализации."""

    def __init__(self) -> None:
        self.data_agent = DataAgent()
        self.analyst_agent = AnalystAgent()
        self.chart_agent = ChartAgent()
        self.out_dir = Path("out")
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def _slug(self, text: str, max_len: int = 40) -> str:
        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

    def ask(self, question: str) -> AskResult:
        """Главная точка входа."""
        start = time.time()
        logger.info(f"[Orchestrator] start: question={question[:60]}...")
        result = AskResult(question=question, sql="", data=[])

        # 1. DataAgent
        try:
            sql_res: SqlResult = self.data_agent.run(question)
            result.sql = sql_res.sql
            result.data = sql_res.data
            logger.info(f"[Orchestrator] data: rows={len(result.data)}")
        except Exception as e:
            result.sql = f"-- ERROR in DataAgent: {e}"
            result.data = []
            logger.info(f"[Orchestrator] data_error: {e}")
            # продолжаем с пустыми данными, чтобы вернуть частичный результат
            return result

        # 2. AnalystAgent (инсайты)
        try:
            analysis = self.analyst_agent.run(question, result.data)
            result.analysis = analysis
            logger.info(
                f"[Orchestrator] analyst: insights={len(analysis.insights) if analysis else 0}"
            )
        except Exception as e:
            # fallback анализ
            from app.schemas import AnalysisResult

            result.analysis = AnalysisResult(
                insights=[
                    "Не удалось выполнить полноценный анализ из-за ошибки на шаге AnalystAgent.",
                    "Рекомендуется проверить доступность модели Ollama и качество входных данных.",
                    "Дальнейшие шаги пайплайна (график) могут быть частично доступны.",
                ],
                key_conclusion=f"Ошибка AnalystAgent: {e}",
                anomaly_or_trend=None,
            )
            logger.info(f"[Orchestrator] analyst_error: {e}")

        # 3. ChartAgent
        try:
            chart_res = self.chart_agent.run(question, result.data)
            result.chart_spec = chart_res.spec
            logger.info(
                f"[Orchestrator] chart: type={getattr(result.chart_spec, 'chart_type', None)}"
            )
        except Exception as e:
            result.chart_spec = None
            logger.info(f"[Orchestrator] chart_error: {e}")
            # Можно продолжить без чарта

        # 4. Рендер графика + сохранение PNG в out/
        png_path: str | None = None
        if result.chart_spec is not None and result.data:
            try:
                df = pd.DataFrame(result.data)
                fig = build_chart(df, result.chart_spec)
                safe_name = self._slug(question)
                png_file = self.out_dir / f"chart_{safe_name}.png"
                export_png(fig, png_file, scale=2.0)
                png_path = str(png_file)
            except Exception as e:
                png_path = f"ERROR rendering: {e}"
                logger.info(f"[Orchestrator] render_error: {e}")

        result.png_path = png_path
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[Orchestrator] end: png={bool(png_path)} ({elapsed}ms)")
        return result
