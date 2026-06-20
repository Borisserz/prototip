"""DataAgent (Phase 2): вопрос на русском → безопасный SELECT SQL + данные через ClickHouse (DWH).

Только SELECT + LIMIT (авто-добавляем если нет), белый список колонок.
Few-shot + self-correction (до 3 попыток при ошибке выполнения).
LLM-вызовы — строго через core.llm (structured, temp=0).
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.models import DataAgentInput, SqlResult
from app.pipeline_progress import emit_pipeline_stage
from core.llm import call_structured, setup_logging

# Ensure central logging (idempotent)
setup_logging()
logger = logging.getLogger("DataAgent")

from app.agents.db_schema_extractor import get_schema_prompt

# Колонки для drilldown (базовый белый список для UI, хотя SQL агент теперь всеяден)
ALLOWED_COLUMNS = {
    "period",
    "region",
    "tax_type",
    "accrued",
    "paid",
    "debt",
    "taxpayers",
    "penalties",
}


from app.agents.config_loader import get_agent_config

class _SqlOnly(BaseModel):
    """Внутренняя схема для LLM: SQL строка и пошаговые рассуждения."""

    step_by_step_reasoning: str = Field(
        ..., 
        description="Пошаговый план запроса: 1. Таблицы 2. Фильтры 3. Группировки"
    )
    sql: str = Field(..., description="Только SELECT запрос, без объяснений")


class DataAgent(BaseAgent):
    """Агент Text-to-SQL (ClickHouse)."""

    name = "data_agent"
    description = "Генерирует безопасный SELECT SQL по вопросу на русском (ClickHouse DWH, whitelist, self-correction до 3 попыток)."
    max_retries = 3

    def __init__(self, model: str | None = None) -> None:
        self.model = model
        self._schema_cache: str | None = None

    def _get_dynamic_schema(self, question: str) -> str:
        if not self._schema_cache:
            from app.agents.db_schema_extractor import get_schema_prompt
            self._schema_cache = get_schema_prompt()
        return self._schema_cache

    def _execute_sql(self, sql: str) -> list[dict]:
        """Безопасное выполнение через ClickHouse."""
        sql = sql.strip().rstrip(";")
        if not sql.lower().startswith("select"):
            raise ValueError("Разрешены только SELECT запросы")

        # Авто LIMIT если отсутствует (защита)
        if "limit" not in sql.lower():
            sql = sql + " LIMIT 500"

        import re

        from app.utils.clickhouse_client import ch_client
        
        # Заменяем обращения к таблице df на enterprise_taxes если нужно (совместимость со старыми few-shot)
        ch_sql = re.sub(r'(?i)\bFROM df\b', 'FROM default.enterprise_taxes', sql)
        
        from app.agent_context import get_current_tenant, get_user_role

        role = get_user_role()
        region_filter = None
        if role == "grodno_manager":
            region_filter = "г. Гродно"
        elif role == "minsk_manager":
            region_filter = "г. Минск"

        # Phase 6: жёсткая валидация + изоляция клиента (allowed tables + WHERE client_id)
        tenant = get_current_tenant()
        extra_filters = {"region": region_filter} if region_filter else None
        from core.sql_guard import SqlSecurityError, secure_sql
        try:
            ch_sql = secure_sql(ch_sql, tenant=tenant, extra_filters=extra_filters)
        except SqlSecurityError as sec_e:
            logger.warning(f"[DataAgent] SQL заблокирован политикой безопасности: {sec_e}")
            raise ValueError(f"Запрос отклонён политикой безопасности: {sec_e}")

        # Маршрутизация: персональный ClickHouse клиента (multi-tenant) или общий DWH
        run_client = ch_client
        if tenant is not None and getattr(tenant, "clickhouse", None):
            try:
                from core.tenant import tenant_store
                _raw = tenant_store.get_clickhouse_client(tenant)

                class _TenantCH:
                    def execute_df(self, q):
                        return _raw.query_df(q)

                run_client = _TenantCH()
                logger.info(f"[DataAgent] Маршрут в ClickHouse клиента '{tenant.client_id}'")
            except Exception as route_e:
                logger.error(f"[DataAgent] Не удалось подключиться к ClickHouse клиента: {route_e}")
                raise ValueError(f"Ошибка подключения к БД клиента: {route_e}")

        # Eval: Проверка синтаксиса перед выполнением (SQL-Eval Pattern)
        try:
            explain_query = f"EXPLAIN SYNTAX {ch_sql}"
            run_client.execute_df(explain_query)
            logger.info("[DataAgent] SQL Eval пройден (EXPLAIN SYNTAX)")
        except Exception as eval_e:
            logger.error(f"[DataAgent] SQL Eval (EXPLAIN) провалился: {eval_e}")
            raise ValueError(f"Ошибка в синтаксисе SQL или названиях таблиц/колонок: {eval_e}. Проверь семантическую модель.")

        try:
            df_result = run_client.execute_df(ch_sql)
            logger.info("[DataAgent] Запрос успешно выполнен в ClickHouse")
            # Convert pandas timestamp / dates to strings to avoid JSON serialization issues
            for col in df_result.select_dtypes(include=['datetime64', 'datetimetz']).columns:
                df_result[col] = df_result[col].astype(str)
            import numpy as np
            df_result = df_result.replace({np.nan: None})
            return df_result.to_dict(orient="records")
        except Exception as e:
            logger.error(f"[DataAgent] Ошибка выполнения в ClickHouse: {e}")
            raise ValueError(f"ClickHouse Execution Error: {e}")

    def _format_drilldown_constraints(self, filters: dict[str, str] | None) -> str:
        if not filters:
            return ""
        real = {k: v for k, v in filters.items() if k in ALLOWED_COLUMNS and v}
        if not real:
            return ""
        clauses = []
        for col, val in real.items():
            safe_val = str(val).replace("'", "''")
            clauses.append(f"{col} = '{safe_val}'")
        return (
            "\n\nОБЯЗАТЕЛЬНЫЕ фильтры drill-down (добавь в WHERE): "
            + " AND ".join(clauses)
            + "."
        )
        
    def _get_semantic_schema(self) -> str:
        """Загружает семантический слой YAML через Advanced Semantic Engine (Phase 11)."""
        from app.semantic.catalog import SemanticCatalog
        schema_path = Path(__file__).parent.parent.parent / "data" / "semantic_model.yaml"
        catalog = SemanticCatalog.load(schema_path)
        return catalog.to_llm_prompt()

    def _build_prompt(
        self,
        question: str,
        previous_error: str | None = None,
        *,
        drilldown_filters: dict[str, str] | None = None,
    ) -> str:
        semantic_context = self._get_semantic_schema()
        schema_info = self._get_dynamic_schema(question)
        
        # Phase 16: Внедряем контекст памяти
        from app.utils.memory import conversation_memory
        memory_context = conversation_memory.get_context_string("default_session")
        
        cfg = get_agent_config("data_agent")
        
        prompt = f"""Ты — {cfg.role}. Твоя задача — {cfg.goal}

=== DYNAMIC SCHEMA (Flat Tables) ===
{schema_info}

=== SEMANTIC MODEL (MDL) ===
ВНИМАНИЕ: Это бизнес-слой. Строго используй описанные здесь метрики, таблицы и расчеты. Не придумывай свои агрегации, если они уже есть в MDL.
{semantic_context}

=== MEMORY CONTEXT ===
{memory_context}

=== RULES ===
{cfg.rules}

=== FEW-SHOT EXAMPLES ===
{cfg.few_shot}

Вопрос пользователя (с учетом истории диалога): {question}
{self._format_drilldown_constraints(drilldown_filters)}
"""
        if previous_error:
            prompt += f"\nПРЕДЫДУЩАЯ ОШИБКА (SQL EVAL): {previous_error}\nВнимательно проверь синтаксис (EXPLAIN SYNTAX) и сверься с Semantic Model. Исправь запрос."
        prompt += '\nВерни JSON строго по схеме: {"step_by_step_reasoning": "...", "sql": "..."}'
        return prompt

    def run(self, request: str | DataAgentInput) -> SqlResult:
        """Основной вход: вопрос → (sql, data). С self-correction."""
        if isinstance(request, DataAgentInput):
            inp = request
        else:
            inp = DataAgentInput(question=str(request))
        start = time.time()
        logger.info(f"[DataAgent] start: question={inp.question[:60]}...")
        
        # Phase 15: Semantic cache - SKIP if drilldown filters are present to ensure fresh SQL with correct filters
        from app.utils.semantic_cache import semantic_cache
        if not inp.drilldown_filters:
            cached_sql = semantic_cache.get_sql(inp.question)
            if cached_sql:
                try:
                    emit_pipeline_stage("sql", "done", f"SQL найден в кэше ({len(cached_sql)} символов)", agent="data_agent")
                    emit_pipeline_stage("clickhouse", "running", "Извлечение данных по кэшированному SQL...", agent="data_agent")
                    data = self._execute_sql(cached_sql)
                    emit_pipeline_stage("clickhouse", "done", f"Обработано строк: {len(data)}", agent="data_agent")
                    elapsed = int((time.time() - start) * 1000)
                    return SqlResult(
                        sql=cached_sql,
                        data=data,
                        row_count=len(data),
                        reasoning=f"Запрос найден в кэше (ускорение LLM). Строк: {len(data)}. ({elapsed}ms)"
                    )
                except Exception as e:
                    logger.warning(f"[DataAgent] Ошибка выполнения кэшированного SQL (продолжаем штатно): {e}")
        else:
            logger.info(f"[DataAgent] Drilldown filters present - skipping semantic cache to apply filters: {inp.drilldown_filters}")
                
        last_error: str | None = None
        sql_succeeded = False

        for attempt in range(self.max_retries):
            prompt = self._build_prompt(
                inp.question, last_error, drilldown_filters=inp.drilldown_filters
            )
            try:
                emit_pipeline_stage(
                    "sql",
                    "running",
                    "LLM генерирует безопасный SELECT...",
                    agent="data_agent",
                )
                sql_obj = call_structured(prompt, schema=_SqlOnly, model=self.model, agent_name=self.name)
                sql = sql_obj.sql.strip()
                emit_pipeline_stage(
                    "sql",
                    "done",
                    f"SQL сформирован ({len(sql)} символов)",
                    agent="data_agent",
                )
                sql_succeeded = True

                # Валидация whitelist (грубая)
                lowered = sql.lower()
                for bad in ("insert", "update", "delete", "drop", "create", "alter", ";--"):
                    if bad in lowered:
                        raise ValueError(f"Запрещённая операция в SQL: {bad}")
                        
                # 1. Быстрая проверка синтаксиса (Бесплатно)
                from app.utils.clickhouse_client import ch_client
                try:
                    ch_client.execute_df(f"EXPLAIN SYNTAX {sql}")
                except Exception as syntax_e:
                    raise ValueError(f"Синтаксическая ошибка SQL: {syntax_e}. Проверь названия колонок и синтаксис ClickHouse.")
                # 2. Выполнение запроса (Получение реальных данных для Dry-Run)
                emit_pipeline_stage(
                    "clickhouse",
                    "running",
                    "ClickHouse выполняет запрос к БД...",
                    agent="data_agent",
                )
                data = self._execute_sql(sql)
                emit_pipeline_stage(
                    "clickhouse",
                    "done",
                    f"Обработано строк: {len(data)}",
                    agent="data_agent",
                )
                        
                # 3. Продвинутый SQL Eval (LLM-as-a-Judge - Дорого)
                from app.agents.sql_evaluator import SqlEvaluatorAgent
                evaluator = SqlEvaluatorAgent()
                eval_schema = self._get_dynamic_schema(inp.question)
                eval_res = evaluator.evaluate(inp.question, sql, eval_schema, sample_data=data[:5])
                if not eval_res.is_correct:
                    logger.warning(f"[DataAgent] SQL Eval забраковал запрос: {eval_res.feedback}")
                    raise ValueError(f"SQL Eval Logical Error: {eval_res.feedback}")

                elapsed = int((time.time() - start) * 1000)
                logger.info(f"[DataAgent] end: rows={len(data)} sql_len={len(sql)} ({elapsed}ms)")
                
                # Сохраняем успешный запрос в кэш только если нет drilldown-фильтров.
                # Drill-down генерирует SQL с WHERE фильтрами (напр. region='Гродно'),
                # который нельзя кэшировать — он не подходит для обычных запросов с тем же текстом.
                if not inp.drilldown_filters:
                    semantic_cache.set_sql(inp.question, sql)
                
                return SqlResult(
                    step_by_step_planning=sql_obj.step_by_step_reasoning,
                    sql=sql,
                    data=data,
                    row_count=len(data),
                    reasoning=f"Сгенерирован безопасный SELECT (self-correction, whitelist, авто-LIMIT). Строк: {len(data)}.",
                )

            except Exception as e:
                last_error = str(e)
                emit_pipeline_stage(
                    "sql",
                    "error",
                    "Ошибка генерации или выполнения SQL",
                    agent="data_agent",
                    error=last_error,
                )
                if sql_succeeded:
                    emit_pipeline_stage(
                        "clickhouse",
                        "error",
                        "ClickHouse не выполнил запрос",
                        agent="data_agent",
                        error=last_error,
                    )
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
