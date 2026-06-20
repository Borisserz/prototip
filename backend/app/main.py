"""FastAPI — thin layer над Orchestrator."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, Header, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from app.auth import create_access_token, get_current_user
from app.config import config
import logging
logger = logging.getLogger(__name__)

from app.logger_setup import setup_json_logger
from app.logging_utils import new_correlation_id
from app.middleware.logging import log_requests_middleware
from app.orchestrator import Orchestrator
from app.routers import auth
from app.schemas import (
    DashboardRequest,
    DashboardResult,
    DrilldownContext,
    PresentationRequest,
    PresentationResult,
    PresentationUpdateRequest,
)
from app.utils.clickhouse_client import ch_client

app = FastAPI(
    title="prototip BI",
    version=config.app_version,
    description="Локальная мультиагентная BI-платформа для налоговой аналитики (прототип).",
)


# Включаем JSON логирование
setup_json_logger()

# Phase 19: Observability (Prometheus)
Instrumentator().instrument(app).expose(app)

# Phase 8: регистрируем кастомные бизнес-метрики (LLM, SQL, узлы LangGraph),
# чтобы они присутствовали в /metrics ещё до первого запроса.
try:
    import app.observability  # noqa: F401
except Exception as _obs_exc:  # pragma: no cover
    logger.warning(f"Observability metrics not loaded: {_obs_exc}")

from contextlib import asynccontextmanager
from app.services.email_scheduler import start_scheduler
from app.utils.schema_crawler import generate_semantic_model
from app.utils.init_schema_knowledge import init_schema_knowledge
from app.services.rag_service import initialize_dashboard_rag

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Запуск фонового шедулера при старте
    start_scheduler()
    
    # Авто-генерация схемы БД при старте
    generate_semantic_model()
    
    # Инициализация Smart Schema RAG
    try:
        init_schema_knowledge()
        initialize_dashboard_rag()
    except Exception as e:
        print(f"Schema Knowledge RAG Error: {e}")

    # Phase 4: таблицы долгосрочной памяти (профили + история чата)
    try:
        from core.memory_store import memory_store
        memory_store.init_tables()
    except Exception as e:
        print(f"Memory Store Init Error: {e}")
    
    yield
    # При остановке приложения здесь можно корректно завершить шедулер

app.router.lifespan_context = lifespan

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(log_requests_middleware)
# app.include_router(auth.router, prefix="/auth", tags=["auth"])

_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    drilldown: DrilldownContext | None = None


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "phase": config.app_phase,
        "version": config.app_version,
    }


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    return {
        "message": "prototip — мультиагентная BI-аналитика (PlannerAgent + Orchestrator)",
        "health": "/health",
        "docs": "/docs",
        "phase": config.app_phase,
    }

from datetime import timedelta

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/auth/login", tags=["auth"])
def login(form_data: LoginRequest):
    # Mock auth check
    role = "manager"
    if "admin" in form_data.username.lower():
        role = "admin"
    elif "grodno" in form_data.username.lower():
        role = "grodno_manager"
    elif "minsk" in form_data.username.lower():
        role = "minsk_manager"
        
    access_token = create_access_token(
        data={"sub": form_data.username, "role": role},
        expires_delta=timedelta(minutes=1440)
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": role,
        "username": form_data.username,
        "is_admin": role == "admin",
    }


@app.post("/ask", tags=["orchestrator"])
def ask_endpoint(payload: AskRequest, user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Универсальный запрос через PlannerAgent (Обычный JSON-ответ)."""
    cid = new_correlation_id()
    res = get_orchestrator().ask(
        payload.question,
        drilldown=payload.drilldown,
        correlation_id=cid,
        user=user
    )
    if hasattr(res, "model_dump"):
        return res.model_dump(mode="json")
    return {"result": str(res), "correlation_id": cid}

@app.post("/ask_stream", tags=["orchestrator"])
async def ask_stream_endpoint(payload: AskRequest, user: dict = Depends(get_current_user)):
    """Streaming (SSE) эндпоинт для чата."""
    cid = new_correlation_id()
    return StreamingResponse(
        get_orchestrator().ask_stream(
            payload.question,
            drilldown=payload.drilldown,
            correlation_id=cid,
            user=user
        ),
        media_type="text/event-stream",
    )

import asyncio
import pandas as pd
from io import BytesIO

class ExportRequest(BaseModel):
    data: list[dict[str, Any]]

@app.post("/api/export/excel", tags=["export"])
def export_excel_endpoint(payload: ExportRequest):
    """Экспорт данных в Excel."""
    if not payload.data:
        raise HTTPException(status_code=400, detail="Data is empty")
        
    df = pd.DataFrame(payload.data)
    
    # Записываем в буфер
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Report', index=False)
    
    buffer.seek(0)
    return StreamingResponse(
        buffer, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=report.xlsx"}
    )

DASHBOARD_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'user_dashboards.json')

class UserDashboardRequest(BaseModel):
    pinned_charts: list[str]

@app.get("/api/user/dashboard", tags=["dashboard"])
def get_user_dashboard():
    """Получает сохраненный дашборд пользователя."""
    if os.path.exists(DASHBOARD_FILE):
        try:
            with open(DASHBOARD_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"pinned_charts": []}

@app.post("/api/user/dashboard", tags=["dashboard"])
def save_user_dashboard(payload: UserDashboardRequest):
    """Сохраняет дашборд пользователя."""
    os.makedirs(os.path.dirname(DASHBOARD_FILE), exist_ok=True)
    with open(DASHBOARD_FILE, "w") as f:
        json.dump({"pinned_charts": payload.pinned_charts}, f)
    return {"status": "ok"}

@app.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            question = payload.get("question") or payload.get("content") or payload.get("message")
            session_id = payload.get("session_id")
            
            if not question:
                continue

            # Parse drill-down context from frontend
            drilldown_ctx = None
            drilldown_raw = payload.get("drilldown")
            if drilldown_raw and isinstance(drilldown_raw, dict):
                key = drilldown_raw.get("key", "")
                value = drilldown_raw.get("value", "")
                if key and value:
                    # Map common chart keys to SQL column names
                    key_mapping = {
                        "region": "region", "REGION": "region", "Регион": "region",
                        "tax_type": "tax_type", "TAX_TYPE": "tax_type", "Вид налога": "tax_type",
                        "period": "period", "PERIOD": "period", "Период": "period",
                    }
                    sql_key = key_mapping.get(key, key.lower())
                    action = drilldown_raw.get("action", "drilldown")
                    from app.schemas import DrilldownContext
                    
                    filters = {sql_key: value} if action != "compare" else {}
                    drilldown_ctx = DrilldownContext(
                        filters=filters,
                        dimension=sql_key,
                        segment_label=value,
                    )
                    print(f"[WS] Drilldown context: {sql_key}={value}, action={action}")
                
            await websocket.send_text(json.dumps({"type": "status", "content": "Изучаем ваш запрос..."}))
            await asyncio.sleep(0.5)
            await websocket.send_text(json.dumps({"type": "status", "content": "Анализ данных и подготовка ответа..."}))
            
            loop = asyncio.get_event_loop()
            
            # We can pass user info if we decode the token, but for now fallback to manager
            # or extract from url/headers if possible. Since it's WS, we use default manager.
            import queue
            debate_q = queue.Queue()
            
            def run_ask():
                from app.agent_context import debate_context
                with debate_context(debate_q):
                    return get_orchestrator().ask(question, drilldown=drilldown_ctx, session_id=session_id)
                    
            ask_task = loop.run_in_executor(None, run_ask)
            
            # Poll the queue while ask_task is running
            from app.pipeline_progress import pipeline_store
            last_snapshot = None
            
            while not ask_task.done():
                try:
                    while True:
                        msg = debate_q.get_nowait()
                        await websocket.send_text(json.dumps(msg))
                except queue.Empty:
                    pass
                
                # Send pipeline progress
                current_snapshot = pipeline_store.snapshot()
                if current_snapshot != last_snapshot:
                    await websocket.send_text(json.dumps({
                        "type": "pipeline_update",
                        "stages": current_snapshot.get("stages", {}),
                        "active": current_snapshot.get("active_stages", [])
                    }))
                    last_snapshot = current_snapshot
                    
                await asyncio.sleep(0.5)
                
            # Process remaining messages
            while not debate_q.empty():
                msg = debate_q.get_nowait()
                await websocket.send_text(json.dumps(msg))
                
            ask_result = ask_task.result()
            
            content = ask_result.reasoning or "Анализ завершен."
            
            # If the reasoning is just chart_json (like in presenter_node), we format it nicely
            import json as js
            if ask_result.charts:
                # Let's make sure the text has charts in ```json blocks
                # The frontend parseCharts looks for ```json ... ```
                try:
                    js.loads(content) # if it's purely json, wrap it
                    content = f"Вот ваши данные:\n\n```json\n{content}\n```"
                except Exception:
                    # Not purely json, maybe append charts
                    pass

            response_data = {"type": "result", "content": content}
            
            # Phase 20: Добавляем SQL в ответ для Режима Аналитика
            if getattr(ask_result, "sql", None):
                response_data["sql"] = ask_result.sql
                
            if getattr(ask_result, "pptx_path", None):
                response_data["pptx_path"] = ask_result.pptx_path
                
            if getattr(ask_result, "excel_path", None):
                response_data["excel_path"] = ask_result.excel_path

            await websocket.send_text(json.dumps(response_data))
            
    except WebSocketDisconnect:
        print("WebSocket Client disconnected")
    except Exception as e:
        print(f"WebSocket Error: {str(e)}")
        await websocket.send_text(json.dumps({"type": "error", "content": str(e)}))

@app.post("/api/v1/upload_data")
async def upload_data(file: UploadFile = File(...)):
    """Загрузка данных (CSV) в dropzone для обработки фоновым ETL Worker'ом."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Только CSV файлы поддерживаются")
        
    dropzone_dir = Path("data/dropzone")
    dropzone_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = dropzone_dir / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    return {"status": "success", "message": f"Файл {file.filename} загружен в dropzone и будет обработан ETL."}

@app.post("/api/v1/trigger_watcher", tags=["system"])
async def trigger_watcher(background_tasks: BackgroundTasks):
    """Триггер проактивного агента (WatcherAgent) для сканирования аномалий."""
    from app.services.watcher_service import WatcherService
    background_tasks.add_task(WatcherService.run_anomaly_scan)
    return {"status": "accepted", "message": "Проактивное сканирование запущено в фоне. Ожидайте письмо."}

@app.post("/generate_dashboard", response_model=DashboardResult, tags=["dashboard"])
def generate_dashboard(payload: DashboardRequest, user: dict = Depends(get_current_user)) -> DashboardResult:
    """Явный fast-path дашборда через Orchestrator.dashboard()."""
    cid = new_correlation_id()
    drilldown = None
    if payload.drilldown_filters:
        drilldown = DrilldownContext(filters=payload.drilldown_filters)
    return get_orchestrator().dashboard(
        payload.question,
        max_charts=payload.max_charts,
        include_kpi=payload.include_kpi,
        data=payload.data,
        drilldown=drilldown,
        correlation_id=cid,
    )


@app.post("/generate_presentation", tags=["presentation"])
def generate_presentation(payload: PresentationRequest, user: dict = Depends(get_current_user)):
    """Генерация презентации через Orchestrator.presentation()."""
    from core.llm import call_structured
    from fastapi.responses import JSONResponse

    cid = new_correlation_id()
    questions = [q.text for q in payload.questions]

    # Audience/detail context for prompt enrichment
    audience_hint = {
        'executive': 'для топ-менеджмента (стратегический уровень, KPI, рекомендации)',
        'board': 'для совета директоров (краткий обзор, риски, возможности)',
        'analyst': 'для аналитиков (детализированные данные, методология, полнота)',
    }.get(payload.audience or 'executive', 'для топ-менеджмента')

    detail_hint = {
        'standard': '5-7',
        'detailed': '7-9',
        'comprehensive': '9-12',
    }.get(payload.detail_level or 'detailed', '7-9')

    if payload.mode != "По вопросам" and payload.overall_theme:
        class QList(BaseModel):
            questions: list[str]

        try:
            qlist = call_structured(
                f"Разложи тему '{payload.overall_theme}' в {detail_hint} конкретных аналитических вопросов "
                f"для профессиональной презентации по налоговой аналитике Республики Беларусь ({audience_hint}). "
                "ВАЖНО: вопросы должны охватывать РАЗНЫЕ аспекты: динамику по времени, региональное сравнение, "
                "структуру по видам налогов, задолженность, топ-регионы, аномалии. "
                "ВАЖНО: вопросы должны запрашивать АГРЕГИРОВАННЫЕ данные из базы (суммы, доли, топ регионов, динамика по месяцам). "
                "НЕ добавляй фильтры по стране или аббревиатуры ('РБ', 'Беларусь', 'BY'). "
                "Примеры хороших вопросов: 'Какие регионы имеют наибольшую налоговую задолженность?', "
                "'Структура начислений по видам налогов (доли)', 'Динамика начислений по месяцам', "
                "'Топ-5 регионов по собираемости НДС', 'Сравнение задолженности по регионам', "
                "'Анализ аномалий в налоговых поступлениях'.",
                schema=QList,
                system=f"Только список из {detail_hint} аналитических вопросов на русском. Вопросы должны быть разнообразными и охватывать разные аспекты темы. Без фильтров по стране.",
                agent_name="api_suggest"
            )
            questions = qlist.questions
        except Exception as e:
            logger.warning(f"[generate_presentation] question LLM failed: {e}, using fallback")
            questions = [
                "Какие регионы имеют наибольшую налоговую задолженность?",
                "Структура налогов по видам (доли начислений)",
                "Динамика налоговых поступлений по месяцам",
                "Топ-5 регионов по собираемости НДС",
                "Сравнение задолженности по регионам и видам налогов",
                "Анализ аномалий в налоговых поступлениях",
                "Динамика задолженности по кварталам 2024 года",
            ]

    if not questions:
        questions = [
            "Какие регионы имеют наибольшую налоговую задолженность?",
            "Структура налогов по видам (доли начислений)",
            "Динамика налоговых поступлений по месяцам",
            "Сравнение задолженности по регионам",
        ]

    # Always pass plain strings to the orchestrator
    q_str: list[str] = []
    for q in (payload.questions if payload.questions and any(getattr(q, "text", "") for q in payload.questions) else questions):
        if isinstance(q, str):
            q_str.append(q)
        elif hasattr(q, "text"):
            q_str.append(str(q.text))
        else:
            q_str.append(str(q))

    try:
        result = get_orchestrator().presentation(
            q_str,
            num_slides=payload.num_slides,
            include_title=payload.include_title,
            include_recommendations=payload.include_recommendations,
            correlation_id=cid,
        )
    except Exception as exc:
        logger.error(f"[generate_presentation] exception: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ошибка генерации презентации: {exc}")

    # If executor caught an exception and returned AgentResult (not PresentationResult)
    from app.agents.models import PresentationResult as PR
    if not isinstance(result, PR):
        err_msg = getattr(result, "error", None) or "PresentationAgent вернул неожиданный тип"
        logger.error(f"[generate_presentation] bad result type={type(result).__name__}: {err_msg}")
        raise HTTPException(status_code=500, detail=err_msg)

    # Return plain JSON to bypass FastAPI response_model validation
    try:
        return JSONResponse(content=result.model_dump(mode="json"))
    except Exception as exc:
        logger.error(f"[generate_presentation] serialization error: {exc}", exc_info=True)
        # Minimal fallback serialization
        return JSONResponse(content={
            "pptx_path": result.pptx_path,
            "num_slides": result.num_slides,
            "slide_png_paths": result.slide_png_paths,
            "presentation_id": result.presentation_id,
            "success": result.success,
            "reasoning": result.reasoning or "",
            "error": result.error,
        })


@app.post("/api/v1/presentation/update", response_model=PresentationResult, tags=["presentation"])
def update_presentation(payload: PresentationUpdateRequest, user: dict = Depends(get_current_user)):
    """Обновляет текстовое содержимое презентации и пересобирает файлы (без LLM)."""
    try:
        from app.agents.presentation_agent import PresentationAgent
        agent = PresentationAgent()
        result = agent.update_presentation(payload.presentation_id, payload.slide_updates)
        return result
    except FileNotFoundError as e:
        logger.error(f"[update_presentation] State not found: {e}")
        return JSONResponse(status_code=404, content={"detail": str(e)})
    except Exception as exc:
        logger.error(f"[update_presentation] error: {exc}", exc_info=True)
        return JSONResponse(status_code=500, content={"detail": str(exc)})




@app.get("/api/v1/kpi", tags=["dashboard"])
def get_kpi_summary():
    """Возвращает агрегированные метрики для Executive Dashboard из ClickHouse."""
    try:
        query = """
            SELECT 
                sum(accrued) as total_accrued,
                sum(paid) as total_paid,
                sum(debt) as total_debt,
                avg(penalties) as avg_penalty
            FROM default.tax_data
        """
        result = ch_client.get_client().query(query)
        row = result.result_rows[0]
        
        total_accrued = float(row[0]) if row[0] else 0.0
        total_paid = float(row[1]) if row[1] else 0.0
        total_debt = float(row[2]) if row[2] else 0.0
        avg_penalty = float(row[3]) if row[3] else 0.0
        
        collection_rate = (total_paid / total_accrued) * 100 if total_accrued > 0 else 0
        
        return {
            "kpi": [
                {"title": "Начислено", "value": f"{total_accrued/1e6:,.1f}M бел. руб.", "trend": "+5%", "status": "good"},
                {"title": "Оплачено", "value": f"{total_paid/1e6:,.1f}M бел. руб.", "trend": "+2%", "status": "neutral"},
                {"title": "Задолженность", "value": f"{total_debt/1e6:,.1f}M бел. руб.", "trend": "-1%", "status": "good"},
                {"title": "Уровень сборов", "value": f"{collection_rate:.1f}%", "trend": "+0.5%", "status": "good"},
                {"title": "Ср. пеня", "value": f"{avg_penalty:,.0f} бел. руб.", "trend": "+12%", "status": "bad"},
            ]
        }
    except Exception as e:
        return {"error": f"ClickHouse error: {str(e)}"}

class ExportRequest(BaseModel):
    data: list[dict]
    filename: str = "analytics_export.xlsx"

@app.post("/api/v1/export-excel", tags=["dashboard"])
def export_custom_excel(payload: ExportRequest):
    """Экспорт текущей выборки данных в красивый Excel (Phase 16)."""
    import os

    from app.utils.excel_exporter import export_to_excel
    
    try:
        file_path = export_to_excel(payload.data, filename=payload.filename)
        # Возвращаем путь для скачивания через /api/v1/download
        return {"status": "ok", "url": f"http://127.0.0.1:8000/api/v1/download?file={os.path.basename(file_path)}"}
    except Exception as e:
        raise HTTPException(500, str(e))

class ReportDocxRequest(BaseModel):
    """Запрос на сборку отчёта в формате Word (.docx) — Phase 2."""
    markdown: str | None = None
    title: str | None = None
    subtitle: str | None = None
    question: str | None = None
    data: list[dict] | None = None
    charts: list[dict] | None = None


@app.post("/api/v1/export/report-docx", tags=["export"])
def export_report_docx(payload: ReportDocxRequest):
    """Сборка отчёта в .docx из размеченного Markdown (или question+data).

    Графики (charts) рендерятся через viz/charts и вставляются в документ;
    готовый .docx зеркалится в MinIO (бакет documents). Возвращает файл на скачивание,
    а presigned URL (если MinIO включён) — в заголовке X-MinIO-URL.
    """
    from app.agents.report_docx_agent import ReportChart, ReportDocxAgent, ReportDocxInput

    charts = [ReportChart(**c) for c in (payload.charts or [])]
    inp = ReportDocxInput(
        markdown=payload.markdown,
        title=payload.title,
        subtitle=payload.subtitle,
        question=payload.question,
        data=payload.data,
        charts=charts,
    )
    result = ReportDocxAgent().run(inp)
    if not result.success:
        raise HTTPException(500, result.error or "Не удалось собрать .docx")
    return FileResponse(
        result.docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(result.docx_path),
        headers={"X-MinIO-URL": result.url or ""},
    )


# ─── Центр управления промптами (Phase 3) ───────────────────────────────────
class ForecastRequest(BaseModel):
    """Запрос на прогноз временного ряда из данных дашборда (Phase 3)."""

    data: list[dict] = Field(default_factory=list, description="Строки временного ряда (история)")
    question: str = Field("", description="Вопрос/контекст для текстового резюме прогноза")
    horizon: int = Field(6, description="Сколько периодов прогнозировать вперёд")


@app.post("/api/v1/forecast", tags=["dashboard"])
def forecast_endpoint(payload: ForecastRequest):
    """Строит прогноз по переданному временному ряду дашборда.

    Прогон через ForecastAnalystAgent (numpy/scipy + опц. statsmodels) и
    LLM-резюме (промпт из центра управления, с fallback). Возвращает числовой
    прогноз, доверительные интервалы, метрики, нарратив и объединённые данные
    (история + прогноз) для отрисовки зоны ДИ на фронтенде.
    """
    from app.agents.forecast_analyst_agent import ForecastAnalystAgent
    from domain import forecasting as fc

    rows = payload.data or []
    if not rows:
        raise HTTPException(400, "Нет данных для прогноза")

    horizon = max(1, min(int(payload.horizon or 6), 24))
    question = payload.question or "Построй прогноз по историческим данным дашборда."

    result = ForecastAnalystAgent().run(question, data=rows, horizon=horizon)
    if not result.success:
        raise HTTPException(422, result.error or "Не удалось построить прогноз")

    x_col, y_col = fc.detect_time_value_columns(rows)
    return {
        "success": True,
        "narrative": result.narrative,
        "method": result.method,
        "horizon": result.horizon,
        "forecast": result.forecast,
        "metrics": result.metrics,
        "data": result.data,
        "x": x_col,
        "y": y_col,
        "title": result.chart_spec.title if result.chart_spec else f"Прогноз: {y_col}",
        "reasoning": result.reasoning,
    }


# ─── Долгосрочная память пользователя (Phase 4) ────────────────────────────────
class UserProfileRequest(BaseModel):
    """Описание пользователя для долгосрочной памяти."""

    profile: str = Field("", description="Текстовое описание пользователя (кто он, чем занимается)")
    role: str = Field("", description="Роль/должность (опционально)")


@app.get("/api/v1/memory/profile", tags=["memory"])
def get_memory_profile(user: dict = Depends(get_current_user)):
    """Профиль текущего пользователя из долгосрочной памяти."""
    from core.memory_store import memory_store

    user_id = user.get("username") or user.get("id")
    profile = memory_store.get_profile(user_id) if user_id else None
    return {
        "user_id": user_id,
        "profile": (profile or {}).get("profile", ""),
        "role": (profile or {}).get("role", "") or user.get("role", ""),
        "exists": profile is not None,
    }


@app.put("/api/v1/memory/profile", tags=["memory"])
def update_memory_profile(payload: UserProfileRequest, user: dict = Depends(get_current_user)):
    """Создаёт/обновляет профиль пользователя (используется Memory Node в System Prompt)."""
    from core.memory_store import memory_store

    user_id = user.get("username") or user.get("id")
    if not user_id:
        raise HTTPException(400, "Не удалось определить пользователя")
    role = payload.role or user.get("role", "")
    ok = memory_store.upsert_profile(user_id, payload.profile, role)
    if not ok:
        raise HTTPException(500, "Не удалось сохранить профиль")
    return {"success": True, "user_id": user_id, "profile": payload.profile, "role": role}


@app.get("/api/v1/memory/history", tags=["memory"])
def get_memory_history(limit: int = 20, user: dict = Depends(get_current_user)):
    """Последние записи истории чата текущего пользователя."""
    from core.memory_store import memory_store

    user_id = user.get("username") or user.get("id")
    history = memory_store.recent_history(user_id, limit=max(1, min(limit, 200))) if user_id else []
    return {"user_id": user_id, "count": len(history), "history": history}


@app.get("/api/v1/memory/recall", tags=["memory"])
def recall_memory(q: str, days: int = 7, k: int = 5, user: dict = Depends(get_current_user)):
    """Семантический поиск по прошлым запросам пользователя (отладка Memory Node)."""
    from core.memory_store import memory_store

    user_id = user.get("username") or user.get("id")
    if not user_id:
        return {"user_id": None, "hits": [], "context": ""}
    hits = memory_store.search_recent(user_id, q, days=days, k=k)
    context = memory_store.build_memory_context(user_id, q, days=days, k=k)
    return {
        "user_id": user_id,
        "hits": [{"prompt": h["prompt"], "ts": str(h["ts"]), "dist": h["dist"]} for h in hits],
        "context": context,
    }


# ─── Управление клиентами (Phase 6: Multi-tenant B2B) ──────────────────────────
class TenantCreateRequest(BaseModel):
    """Создание клиента: личный ClickHouse + коллекция семантики + JWT."""

    client_id: str
    name: str
    ch_host: str = "localhost"
    ch_port: int = 8123
    ch_database: str = "default"
    ch_user: str = "default"
    ch_password: str = ""
    vector_collection: str | None = None
    allowed_tables: list[str] = Field(default_factory=list)
    enforce_client_id: bool = False
    client_id_value: str | None = None


@app.get("/api/v1/admin/tenants", tags=["admin"])
def list_tenants_endpoint():
    """Список клиентов (без секретов)."""
    from core.tenant import tenant_store

    return {"tenants": [t.to_public() for t in tenant_store.list_tenants()]}


@app.post("/api/v1/admin/tenants", tags=["admin"])
def create_tenant_endpoint(payload: TenantCreateRequest):
    """Создаёт клиента, возвращает его конфиг + уникальный JWT-токен и API-ключ."""
    from core.tenant import tenant_store

    try:
        t = tenant_store.create_tenant(
            client_id=payload.client_id,
            name=payload.name,
            ch_host=payload.ch_host,
            ch_port=payload.ch_port,
            ch_database=payload.ch_database,
            ch_user=payload.ch_user,
            ch_password=payload.ch_password,
            vector_collection=payload.vector_collection,
            allowed_tables=payload.allowed_tables,
            enforce_client_id=payload.enforce_client_id,
            client_id_value=payload.client_id_value,
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    out = t.to_public()
    out["jwt_token"] = t.jwt_token
    out["api_key"] = t.api_key
    return out


@app.post("/api/v1/admin/tenants/{client_id}/rotate-token", tags=["admin"])
def rotate_tenant_token(client_id: str):
    """Перевыпускает JWT-токен и API-ключ клиента."""
    from core.tenant import tenant_store

    t = tenant_store.rotate_token(client_id)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    return {"client_id": client_id, "jwt_token": t.jwt_token, "api_key": t.api_key}


@app.delete("/api/v1/admin/tenants/{client_id}", tags=["admin"])
def delete_tenant_endpoint(client_id: str):
    """Удаляет клиента из реестра."""
    from core.tenant import tenant_store

    ok = tenant_store.delete_tenant(client_id)
    if not ok:
        raise HTTPException(404, "Клиент не найден")
    return {"success": True, "client_id": client_id}


@app.get("/api/v1/admin/overview", tags=["admin"])
def admin_overview_endpoint(days: int = 30):
    """Сводные KPI по всем клиентам + лёгкая статистика на каждую карточку.

    Используется лендингом админ-консоли («Мои блоки»).
    """
    from core.tenant import tenant_store
    from app.services.tenant_stats import compute_overview

    tenants = tenant_store.list_tenants()
    overview = compute_overview(tenants, days=days)
    # Прикрепляем публичный конфиг каждого клиента к его агрегатам.
    by_id = {t.client_id: t.to_public() for t in tenants}
    for c in overview["clients"]:
        c["config"] = by_id.get(c["client_id"], {})
    return overview


@app.get("/api/v1/admin/tenants/{client_id}", tags=["admin"])
def get_tenant_endpoint(client_id: str):
    """Публичная конфигурация одного клиента."""
    from core.tenant import tenant_store

    t = tenant_store.get_tenant(client_id)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    return t.to_public()


@app.get("/api/v1/admin/tenants/{client_id}/stats", tags=["admin"])
def tenant_stats_endpoint(client_id: str, days: int = 30):
    """Развёрнутая аналитика использования по клиенту.

    Live-метрики из личного ClickHouse при доступности, иначе детерминированные
    представительные данные (помечены полем ``source``).
    """
    from core.tenant import tenant_store
    from app.services.tenant_stats import compute_tenant_stats

    t = tenant_store.get_tenant(client_id)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    stats = compute_tenant_stats(t, days=days)
    stats["client"] = t.to_public()
    return stats


@app.get("/api/v1/admin/tenants/{client_id}/impersonate", tags=["admin"])
def impersonate_tenant_endpoint(client_id: str):
    """Выдаёт админу scoped JWT клиента для входа «от лица заказчика»."""
    from core.tenant import tenant_store

    t = tenant_store.get_tenant(client_id)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    token = t.jwt_token or create_access_token(
        data={"sub": f"tenant:{t.client_id}", "role": "client", "client_id": t.client_id},
        expires_delta=timedelta(days=365),
    )
    return {"access_token": token, "client_id": t.client_id, "name": t.name, "tenant": t.to_public()}


class TenantUpdateRequest(BaseModel):
    """Частичное обновление настроек клиента (все поля опциональны)."""

    name: str | None = None
    allowed_tables: list[str] | None = None
    enforce_client_id: bool | None = None
    active: bool | None = None
    ch_host: str | None = None
    ch_port: int | None = None
    ch_database: str | None = None


@app.patch("/api/v1/admin/tenants/{client_id}", tags=["admin"])
def update_tenant_endpoint(client_id: str, payload: TenantUpdateRequest):
    """Обновляет настройки клиента (название, доступы, изоляцию, статус, ClickHouse)."""
    from core.tenant import tenant_store

    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not fields:
        raise HTTPException(400, "Нет полей для обновления")
    # ch_* → ключи ClickHouseConfig, понятные update_tenant().
    for src, dst in (("ch_host", "host"), ("ch_port", "port"), ("ch_database", "database")):
        if src in fields:
            fields[dst] = fields.pop(src)
    t = tenant_store.update_tenant(client_id, **fields)
    if not t:
        raise HTTPException(404, "Клиент не найден")
    return t.to_public()


class ClientLoginRequest(BaseModel):
    """Вход заказчика по API-ключу или личному JWT-токену."""

    api_key: str | None = None
    token: str | None = None


@app.post("/api/v1/client/login", tags=["auth"])
def client_login_endpoint(payload: ClientLoginRequest):
    """Аутентификация заказчика. Возвращает scoped JWT и публичный профиль клиента.

    Принимает либо API-ключ клиента, либо его долгоживущий JWT-токен.
    """
    from core.tenant import tenant_store

    tenant = None
    if payload.api_key:
        tenant = tenant_store.resolve_by_api_key(payload.api_key.strip())
    elif payload.token:
        # JWT клиента уже несёт claim client_id и role=client.
        try:
            from jose import jwt as _jwt
            from app.auth import SECRET_KEY, ALGORITHM

            claims = _jwt.decode(payload.token.strip(), SECRET_KEY, algorithms=[ALGORITHM])
            tenant = tenant_store.get_tenant(claims.get("client_id"))
        except Exception:  # noqa: BLE001
            tenant = None

    if not tenant or not tenant.active:
        raise HTTPException(401, "Неверный ключ/токен клиента или клиент отключён")

    access_token = tenant.jwt_token or create_access_token(
        data={"sub": f"tenant:{tenant.client_id}", "role": "client", "client_id": tenant.client_id},
        expires_delta=timedelta(days=365),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "role": "client",
        "is_admin": False,
        "client_id": tenant.client_id,
        "username": tenant.name,
        "tenant": tenant.to_public(),
    }


class PromptUpdateRequest(BaseModel):
    role: str
    goal: str
    rules: str
    few_shot: str = ""


class RawYamlRequest(BaseModel):
    raw_yaml: str


@app.get("/api/v1/admin/prompts", tags=["admin"])
def get_all_prompts():
    """Все конфигурации агентов (промпты) + сырой YAML для редактора."""
    from core.prompt_store import prompt_store
    try:
        return {"agents": prompt_store.load_all(force=True), "raw": prompt_store.get_raw()}
    except Exception as e:
        raise HTTPException(500, f"Не удалось прочитать промпты: {e}")


@app.get("/api/v1/admin/prompts/{agent_name}", tags=["admin"])
def get_prompt(agent_name: str):
    from core.prompt_store import prompt_store
    try:
        return prompt_store.get_agent(agent_name)
    except KeyError:
        raise HTTPException(404, f"Агент '{agent_name}' не найден")


@app.put("/api/v1/admin/prompts/{agent_name}", tags=["admin"])
def update_prompt(agent_name: str, payload: PromptUpdateRequest):
    """Обновить промпт одного агента на лету (без рестарта). Подхватится графом."""
    from core.prompt_store import prompt_store
    try:
        updated = prompt_store.update_agent(agent_name, payload.model_dump())
        return {"status": "ok", "agent": agent_name, "config": updated}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.put("/api/v1/admin/prompts", tags=["admin"])
def replace_prompts(payload: RawYamlRequest):
    """Заменить весь YAML промптов целиком (с валидацией всех агентов)."""
    from core.prompt_store import prompt_store
    try:
        parsed = prompt_store.set_raw(payload.raw_yaml)
        return {"status": "ok", "agents": list(parsed.keys())}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.post("/api/v1/admin/prompts/reload", tags=["admin"])
def reload_prompts():
    """Принудительно перечитать YAML с диска."""
    from core.prompt_store import prompt_store
    return {"status": "ok", "agents": list(prompt_store.reload().keys())}


class EmailRequest(BaseModel):
    to: str | None = "chief@tax.gov.by"
    subject: str = "Отчет: Аналитика"
    content: str = ""

@app.get("/api/v1/pipeline/status", tags=["dashboard"])
def get_pipeline_status():
    from app.pipeline_progress import pipeline_store
    return pipeline_store.snapshot()


@app.get("/api/v1/sessions", tags=["sessions"])
def get_sessions():
    from app.utils.memory import conversation_memory
    sessions = conversation_memory.get_all_sessions()
    # Возвращаем список {session_id, message_count, preview, timestamp}
    res = []
    for sid, msgs in sessions.items():
        res.append({
            "session_id": sid,
            "message_count": len(msgs),
            "preview": msgs[-1]["text"][:50] if msgs else "",
            "timestamp": msgs[-1].get("timestamp", 0) if msgs else 0
        })
    res.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"sessions": res}

@app.get("/api/v1/sessions/{session_id}", tags=["sessions"])
def get_session_history(session_id: str):
    from app.utils.memory import conversation_memory
    sessions = conversation_memory.get_all_sessions()
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": sessions[session_id]}

@app.get("/api/v1/sql-logs", tags=["admin"])
def get_sql_logs():
    """Возвращает последние SQL запросы из system.query_log."""
    try:
        from app.utils.clickhouse_client import ch_client
        query = """
            SELECT user, query, query_duration_ms, type, event_time 
            FROM system.query_log 
            WHERE type = 'QueryFinish' AND query NOT LIKE '%system.query_log%'
            ORDER BY event_time DESC 
            LIMIT 20
        """
        result = ch_client.get_client().query(query)
        logs = []
        for row in result.result_rows:
            logs.append({
                "user": row[0],
                "query": row[1],
                "duration_ms": row[2],
                "status": "Validated" if row[3] == "QueryFinish" else "Failed",
                "time": str(row[4])
            })
        return {"logs": logs}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/v1/send-email", tags=["dashboard"])
def send_email(payload: EmailRequest) -> dict[str, str]:
    """Мок-сервис для отправки email (Phase 13)."""
    
    out_dir = os.path.join(os.path.dirname(__file__), "..", "out", "mock_emails")
    os.makedirs(out_dir, exist_ok=True)
    
    file_id = uuid.uuid4().hex[:8]
    file_path = os.path.join(out_dir, f"email_{file_id}.json")
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, ensure_ascii=False, indent=2)
        
    return {"status": "ok", "message": f"Email успешно отправлен на {payload.to}"}

@app.get("/api/v1/download", tags=["system"])
def download_file(file: str, inline: bool = False):
    """Скачивание / предпросмотр файлов из папки out (.pptx, .png, .xlsx).
    
    - file: имя файла или полный путь (используется только basename)
    - inline: если true, возвращает как inline (для браузерного просмотра PNG)
    """
    import os
    from urllib.parse import quote as _url_quote
    from fastapi import HTTPException
    from fastapi.responses import FileResponse

    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(base_dir, "out")

    # Accept full absolute path — use only basename for security
    safe_filename = os.path.basename(file)
    file_path = os.path.join(out_dir, safe_filename)

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File not found: {safe_filename}")

    # Determine media type
    ext = safe_filename.lower().split(".")[-1] if "." in safe_filename else ""
    media_types = {
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "pdf":  "application/pdf",
        "png":  "image/png",
        "jpg":  "image/jpeg",
        "jpeg": "image/jpeg",
    }
    media_type = media_types.get(ext, "application/octet-stream")
    disposition = "inline" if inline else "attachment"

    # Build Content-Disposition with RFC 5987 encoding for non-ASCII filenames.
    # HTTP headers must be latin-1; Cyrillic characters cause UnicodeEncodeError
    # when using the naive filename="..." form.
    try:
        safe_filename.encode("latin-1")
        content_disp = f'{disposition}; filename="{safe_filename}"'
    except (UnicodeEncodeError, UnicodeDecodeError):
        encoded = _url_quote(safe_filename, safe="")
        content_disp = f"{disposition}; filename*=UTF-8''{encoded}"

    # Do NOT also pass filename= to FileResponse — that would set a second
    # Content-Disposition header which also fails on non-ASCII names.
    return FileResponse(
        file_path,
        media_type=media_type,
        headers={"Content-Disposition": content_disp},
    )

@app.post("/api/v1/workspace/upload", tags=["workspace"])
async def upload_workspace_file(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """Phase 14: Загрузка файлов в персональный Workspace."""
    import os
    import shutil
    import pandas as pd
    from app.utils.clickhouse_client import ch_client
    
    if not file.filename.lower().endswith(('.csv', '.xlsx')):
        raise HTTPException(400, "Только CSV или XLSX файлы")
        
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "out", "workspaces", user.get("username", "guest")))
    os.makedirs(out_dir, exist_ok=True)
    file_path = os.path.join(out_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
            
        safe_name = file.filename.replace('.', '_').replace('-', '_').replace(' ', '_').lower()
        table_name = f"ws_{user.get('username', 'guest')}_{safe_name}"
        
        # ClickHouse integration
        # A simple approach to create a table and insert data
        df = df.fillna("")
        df_dict = df.to_dict('records')
        
        columns = ", ".join([f"`{col}` String" for col in df.columns])
        ch_client.command(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns}) ENGINE = MergeTree() ORDER BY tuple()")
        
        # Insert
        ch_client.insert(table_name, df_dict, column_names=list(df.columns))
        
        return {
            "status": "ok", 
            "table_name": table_name,
            "message": "Файл успешно загружен в Workspace"
        }
    except Exception as e:
        raise HTTPException(500, f"Ошибка загрузки данных: {str(e)}")

@app.post("/api/v1/upload-pdf", tags=["presentation"])
async def upload_pdf(file: UploadFile = File(...)):
    """Legacy: Загрузка PDF -> Генерация презентации (backward compat)."""
    import os
    import shutil
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Только PDF файлы")
        
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "out", "uploads"))
    os.makedirs(out_dir, exist_ok=True)
    file_path = os.path.join(out_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        from app.utils.pdf_presentation import generate_presentation_from_pdf
        from app.services.rag_service import ingest_document
        
        ingest_document(file_path)
        pptx_path = generate_presentation_from_pdf(file_path)
        
        return {
            "status": "ok", 
            "pptx_path": os.path.basename(pptx_path), 
            "message": "Документ проиндексирован и сгенерирована базовая презентация"
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/v1/pdf/analyze", tags=["presentation"])
async def pdf_analyze(
    file: UploadFile = File(...),
    output_type: str = "presentation",
    audience: str = "executive",
    detail_level: str = "detailed",
    user: dict = Depends(get_current_user)
):
    """PDF Generation Hub: Загрузка PDF -> Генерация презентации или дашборда с полным AI-анализом.
    
    output_type: 'presentation' | 'dashboard'
    audience: 'executive' | 'analyst' | 'board'
    detail_level: 'standard' | 'detailed' | 'comprehensive'
    """
    import os
    import shutil
    import fitz # PyMuPDF
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(400, "Только PDF файлы")
        
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "out", "uploads"))
    os.makedirs(out_dir, exist_ok=True)
    file_path = os.path.join(out_dir, file.filename)
    
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Step 1: Extract text from PDF using PyMuPDF (better extraction than pypdf)
    try:
        doc = fitz.open(file_path)
        text = ""
        for page in doc:
            extracted = page.get_text()
            if extracted:
                text += extracted + "\n"
        
        if not text.strip():
            # Fallback if it's completely empty (maybe scanned)
            raise ValueError("Не удалось извлечь текст из PDF. Возможно, документ отсканирован (содержит только изображения).")
        
        num_pages = len(doc)
        text_snippet = text[:20000]
        doc.close()
    except Exception as e:
        raise HTTPException(400, f"Ошибка чтения PDF: {str(e)}")
    
    # Step 2: Index document in RAG
    try:
        from app.services.rag_service import ingest_document
        ingest_document(file_path)
        logger.info(f"[pdf_analyze] PDF indexed: {file.filename}")
    except Exception as e:
        logger.warning(f"[pdf_analyze] RAG indexing failed (non-fatal): {e}")

    # Step 3: Extract document metadata via LLM
    try:
        from core.llm import call_structured
        from pydantic import BaseModel as PydanticBaseModel, Field as PydanticField
        
        class PDFMeta(PydanticBaseModel):
            title: str = PydanticField(..., description="Название документа (на русском)")
            summary: str = PydanticField(..., description="Краткое содержание документа (2-3 предложения)")
            key_topics: list[str] = PydanticField(..., description="5-7 ключевых тем документа")
            document_type: str = PydanticField(..., description="Тип документа: отчет, инструкция, аналитика, презентация, и т.д.")
            suggested_questions: list[str] = PydanticField(..., description="5 ключевых аналитических вопросов для презентации по этому документу")
        
        meta = call_structured(
            f"Проанализируй текст документа и извлеки метаданные.\nТекст:\n{text_snippet[:8000]}",
            schema=PDFMeta,
            system="Анализируй документ и возвращай только JSON с метаданными на русском языке.",
            agent_name="pdf_meta"
        )
        doc_title = meta.title
        doc_summary = meta.summary
        doc_topics = meta.key_topics
        doc_type = meta.document_type
        suggested_questions = meta.suggested_questions
    except Exception as e:
        logger.warning(f"[pdf_analyze] LLM meta extraction failed: {e}")
        doc_title = os.path.splitext(file.filename)[0]
        doc_summary = f"Документ содержит {num_pages} страниц."
        doc_topics = []
        doc_type = "документ"
        suggested_questions = [
            "Каковы основные показатели данного документа?",
            "Какова динамика ключевых метрик?",
            "Какие выводы следуют из анализа?",
            "Что рекомендует документ?",
            "Каковы риски и возможности?",
        ]

    cid = new_correlation_id()

    # Step 4: Generate output based on type
    if output_type == "dashboard":
        try:
            dashboard_question = (
                f"Создай аналитический дашборд по документу '{doc_title}'. "
                f"Темы: {', '.join(doc_topics[:3])}. "
                f"Используй данные из базы и дополни контекстом из документа."
            )
            
            result = get_orchestrator().dashboard(
                dashboard_question,
                max_charts=6,
                include_kpi=True,
                correlation_id=cid,
            )
            
            return {
                "status": "ok",
                "output_type": "dashboard",
                "doc_title": doc_title,
                "doc_summary": doc_summary,
                "doc_topics": doc_topics,
                "doc_type": doc_type,
                "num_pages": num_pages,
                "file_name": file.filename,
                "dashboard_data": result.model_dump(mode="json") if hasattr(result, 'model_dump') else result,
            }
        except Exception as e:
            logger.error(f"[pdf_analyze] dashboard generation failed: {e}", exc_info=True)
            raise HTTPException(500, f"Ошибка генерации дашборда: {str(e)}")
    
    else:  # presentation
        try:
            detail_map = {'standard': '5-7', 'detailed': '7-9', 'comprehensive': '9-12'}
            num_slides_map = {'standard': 10, 'detailed': 14, 'comprehensive': 20}
            num_slides = num_slides_map.get(detail_level, 14)
            
            questions_for_pres = suggested_questions[:num_slides_map.get(detail_level, 7)]
            
            result = get_orchestrator().presentation(
                questions_for_pres,
                num_slides=num_slides,
                include_title=True,
                include_recommendations=True,
                correlation_id=cid,
            )
            
            from app.agents.models import PresentationResult as PR
            if not isinstance(result, PR):
                raise HTTPException(500, "Ошибка генерации презентации")
            
            result_dict = result.model_dump(mode="json")
            result_dict.update({
                "doc_title": doc_title,
                "doc_summary": doc_summary,
                "doc_topics": doc_topics,
                "doc_type": doc_type,
                "num_pages": num_pages,
                "file_name": file.filename,
                "output_type": "presentation",
            })
            
            from fastapi.responses import JSONResponse
            return JSONResponse(content=result_dict)
        except Exception as e:
            logger.error(f"[pdf_analyze] presentation generation failed: {e}", exc_info=True)
            raise HTTPException(500, f"Ошибка генерации презентации из PDF: {str(e)}")



# ==========================================
# Phase 4: Knowledge Base & Subscriptions
# ==========================================

@app.get("/api/v1/knowledge", tags=["admin"])
def list_knowledge_base():
    from app.services.rag_service import get_knowledge_documents
    return {"status": "ok", "documents": get_knowledge_documents()}

@app.delete("/api/v1/knowledge", tags=["admin"])
def delete_knowledge_doc(source: str):
    from app.services.rag_service import delete_knowledge_document
    import base64
    try:
        decoded_source = base64.b64decode(source).decode("utf-8")
        if delete_knowledge_document(decoded_source):
            return {"status": "ok"}
        raise HTTPException(404, "Документ не найден")
    except Exception as e:
        raise HTTPException(400, str(e))

@app.post("/api/v1/rag-search", tags=["knowledge"])
def rag_search(payload: dict = Body(...)):
    """Семантический поиск по базе знаний (RAG).
    
    Body: { "query": "...", "k": 4 }
    Returns: { "context": "...", "sources": [...], "chunks": [...] }
    """
    query = payload.get("query", "").strip()
    k = min(int(payload.get("k", 4)), 10)
    if not query:
        raise HTTPException(400, "query is required")
    try:
        from app.services.rag_service import get_embeddings_model
        from app.utils.clickhouse_client import ch_client as _ch
        emb_model = get_embeddings_model()
        query_vector = emb_model.embed_query(query)
        sql = f"""
            SELECT content, source, cosineDistance(embedding, {query_vector}) as dist
            FROM default.knowledge_base
            ORDER BY dist ASC
            LIMIT {k}
        """
        result = _ch.get_client().query(sql)
        rows = result.result_rows if result.result_rows else []
        context = "\n\n".join(r[0] for r in rows)
        sources = list(dict.fromkeys(r[1] for r in rows))
        chunks = [{"content": r[0][:400], "source": r[1], "score": round(float(r[2]), 4)} for r in rows]
        return {"status": "ok", "context": context, "sources": sources, "chunks": chunks, "total": len(rows)}
    except Exception as e:
        logger.error(f"RAG search error: {e}")
        return {"status": "error", "context": "", "sources": [], "chunks": [], "error": str(e)}

@app.get("/api/v1/subscriptions", tags=["admin"])
def list_subscriptions():
    from app.services.subscription_service import get_subscriptions
    return {"status": "ok", "subscriptions": get_subscriptions()}

@app.post("/api/v1/subscriptions", tags=["admin"])
def create_subscription(sub: dict = Body(...)):
    from app.services.subscription_service import add_subscription
    return {"status": "ok", "subscription": add_subscription(sub)}

@app.delete("/api/v1/subscriptions/{sub_id}", tags=["admin"])
def remove_subscription(sub_id: str):
    from app.services.subscription_service import delete_subscription
    if delete_subscription(sub_id):
        return {"status": "ok"}
    raise HTTPException(404, "Подписка не найдена")

@app.post("/api/v1/subscriptions/{sub_id}/toggle", tags=["admin"])
def toggle_sub(sub_id: str):
    from app.services.subscription_service import toggle_subscription
    if toggle_subscription(sub_id):
        return {"status": "ok"}
    raise HTTPException(404, "Подписка не найдена")

# ==========================================
# Phase 5: Schema, Semantic Rules & Dropzone
# ==========================================

@app.get("/api/v1/schema", tags=["admin"])
def get_db_schema():
    from app.services.schema_scanner import scan_clickhouse_schema
    return {"status": "ok", "schema": scan_clickhouse_schema()}

@app.get("/api/v1/semantic-rules", tags=["admin"])
def get_semantic_rules():
    from app.services.wrenai_client import wren_client
    return {"status": "ok", "rules": wren_client.get_rules()}

@app.post("/api/v1/semantic-rules", tags=["admin"])
def update_semantic_rules(rules: list = Body(...)):
    from app.services.wrenai_client import wren_client
    wren_client.save_rules(rules)
    return {"status": "ok"}

@app.get("/api/v1/dropzone", tags=["admin"])
def list_dropzone():
    import os
    dropzone_dir = os.path.join(os.path.dirname(__file__), "..", "data", "dropzone")
    if not os.path.exists(dropzone_dir):
        return {"status": "ok", "files": []}
        
    files = []
    for fname in os.listdir(dropzone_dir):
        path = os.path.join(dropzone_dir, fname)
        if os.path.isfile(path):
            stat = os.stat(path)
            files.append({
                "name": fname,
                "size": stat.st_size,
                "modified": stat.st_mtime
            })
    return {"status": "ok", "files": files}

@app.delete("/api/v1/dropzone/{filename}", tags=["admin"])
def delete_dropzone_file(filename: str):
    import os
    dropzone_dir = os.path.join(os.path.dirname(__file__), "..", "data", "dropzone")
    path = os.path.join(dropzone_dir, filename)
    if os.path.exists(path):
        try:
            os.remove(path)
            return {"status": "ok"}
        except Exception as e:
            raise HTTPException(500, str(e))
    raise HTTPException(404, "Файл не найден")

@app.get("/api/v1/insights", tags=["dashboard"])
def get_auto_insights():
    """Generates 3 fast insights based on database queries and LLM."""
    from core.llm import call_structured
    from pydantic import BaseModel, Field
    
    class Insight(BaseModel):
        type: str = Field(..., description="'positive', 'negative', or 'warning'")
        text: str = Field(..., description="Короткий инсайт на 1-2 предложения на русском языке")
        
    class InsightsList(BaseModel):
        insights: list[Insight]
        
    try:
        from app.utils.clickhouse_client import ch_client
        # Get regions with highest debt
        query_debt = "SELECT region, sum(debt) as d FROM default.tax_data GROUP BY region ORDER BY d DESC LIMIT 3"
        res_debt = ch_client.get_client().query(query_debt)
        
        # Get regions with best collection rate
        query_rate = "SELECT region, (sum(paid)/sum(accrued))*100 as rate FROM default.tax_data GROUP BY region HAVING sum(accrued) > 0 ORDER BY rate DESC LIMIT 3"
        res_rate = ch_client.get_client().query(query_rate)
        
        data_str = f"Топ должники: {res_debt.result_rows}. Топ по сборам: {res_rate.result_rows}."
        
        prompt = f"Данные из БД налогов: {data_str}. Сгенерируй 3 коротких бизнес-инсайта для дашборда руководителя: 1 позитивный, 1 негативный, 1 предупреждение."
        result = call_structured(prompt, schema=InsightsList, system="Ты умный налоговый аналитик. Пиши очень коротко и емко.", agent_name="insights_agent")
        
        return {"status": "ok", "insights": [i.model_dump() for i in result.insights]}
    except Exception as e:
        print(f"Insights Error: {e}")
        return {"status": "error", "insights": [
            {"type": "warning", "text": "Система аналитики временно недоступна."}
        ]}


# ==========================================
# Workspace DB: Database Browser Endpoints
# ==========================================

from pydantic import BaseModel

class RowUpdateRequest(BaseModel):
    old_row: dict
    new_row: dict

@app.put("/api/v1/db/tables/{table}/row", tags=["workspace"])
def update_table_row(table: str, payload: RowUpdateRequest):
    """Updates a row in ClickHouse using ALTER TABLE UPDATE."""
    from app.utils.clickhouse_client import ch_client
    ALLOWED_TABLES = {"tax_data", "knowledge_base", "dashboard_knowledge"}
    
    if table not in ALLOWED_TABLES and not table.startswith("ws_"):
        raise HTTPException(400, f"Table '{table}' is not accessible")
        
    try:
        conditions = []
        for k, v in payload.old_row.items():
            if v is None or (isinstance(v, str) and v.startswith("[vector:")):
                continue
            if isinstance(v, (int, float)):
                conditions.append(f"`{k}` = {v}")
            else:
                safe_val = str(v).replace("'", "''")
                conditions.append(f"`{k}` = '{safe_val}'")
                
        if not conditions:
            raise HTTPException(400, "Cannot update row without identifying values")
            
        where_clause = " AND ".join(conditions)
        
        sets = []
        for k, v in payload.new_row.items():
            if payload.old_row.get(k) == v:
                continue
            if v is None or (isinstance(v, str) and v.startswith("[vector:")):
                continue
            safe_val = str(v).replace("'", "''")
            sets.append(f"`{k}` = '{safe_val}'")
                
        if not sets:
            return {"status": "ok", "message": "No changes detected"}
            
        set_clause = ", ".join(sets)
        sql = f"ALTER TABLE default.{table} UPDATE {set_clause} WHERE {where_clause}"
        
        ch_client.get_client().command(sql)
        
        return {"status": "ok", "message": "Row update scheduled"}
    except Exception as e:
        logger.error(f"Row Update Error: {e}")
        raise HTTPException(500, str(e))

@app.get("/api/v1/db/tables/{table}/data", tags=["workspace"])
def get_table_data(table: str, page: int = 1, limit: int = 50, search: str = ""):
    """Paginated data from a ClickHouse table with optional text search."""
    from app.utils.clickhouse_client import ch_client
    # Whitelist of allowed tables to prevent SQL injection
    ALLOWED_TABLES = {"tax_data", "knowledge_base", "dashboard_knowledge"}
    if table not in ALLOWED_TABLES:
        raise HTTPException(400, f"Table '{table}' is not accessible")
    
    offset = (page - 1) * limit
    
    try:
        # Get columns first
        cols_result = ch_client.get_client().query(f"DESCRIBE TABLE default.{table}")
        columns = [row[0] for row in cols_result.result_rows]
        
        # Build search WHERE clause using first string columns
        where_clause = ""
        if search:
            safe_search = search.replace("'", "''")
            string_cols = [row[0] for row in cols_result.result_rows if "String" in row[1]][:3]
            if string_cols:
                conditions = " OR ".join([f"position(lower({col}), lower('{safe_search}')) > 0" for col in string_cols])
                where_clause = f"WHERE {conditions}"
        
        # Count total
        count_sql = f"SELECT count() FROM default.{table} {where_clause}"
        count_result = ch_client.get_client().query(count_sql)
        total = count_result.result_rows[0][0] if count_result.result_rows else 0
        
        # Get data page
        data_sql = f"SELECT * FROM default.{table} {where_clause} LIMIT {limit} OFFSET {offset}"
        data_result = ch_client.get_client().query(data_sql)
        
        rows = []
        for row in data_result.result_rows:
            row_dict = {}
            for i, col in enumerate(columns):
                val = row[i]
                # Truncate very long values (like embeddings)
                if isinstance(val, list):
                    row_dict[col] = f"[vector:{len(val)}]"
                elif isinstance(val, str) and len(val) > 300:
                    row_dict[col] = val[:300] + "..."
                else:
                    row_dict[col] = val
            rows.append(row_dict)
        
        return {
            "status": "ok",
            "table": table,
            "columns": columns,
            "rows": rows,
            "total": total,
            "page": page,
            "pages": max(1, (total + limit - 1) // limit)
        }
    except Exception as e:
        logger.error(f"DB Browser Error: {e}")
        raise HTTPException(500, str(e))


@app.get("/api/v1/db/tables/{table}/stats", tags=["workspace"])
def get_table_stats(table: str):
    """Get statistics for a specific table."""
    from app.utils.clickhouse_client import ch_client
    ALLOWED_TABLES = {"tax_data", "knowledge_base", "dashboard_knowledge"}
    if table not in ALLOWED_TABLES:
        raise HTTPException(400, f"Table '{table}' is not accessible")
    
    try:
        count_res = ch_client.get_client().query(f"SELECT count() FROM default.{table}")
        total_rows = count_res.result_rows[0][0] if count_res.result_rows else 0
        
        size_res = ch_client.get_client().query(
            f"SELECT formatReadableSize(sum(bytes_on_disk)) FROM system.parts WHERE table='{table}' AND database='default'"
        )
        size = size_res.result_rows[0][0] if size_res.result_rows else "N/A"
        
        return {"status": "ok", "table": table, "total_rows": total_rows, "size_on_disk": size}
    except Exception as e:
        logger.error(f"Table Stats Error: {e}")
        raise HTTPException(500, str(e))


# ==========================================
# Workspace DB: Semantic Schema Endpoints
# ==========================================

@app.get("/api/v1/semantic-schema", tags=["workspace"])
def get_semantic_schema_json():
    """Return the semantic_schema.json content."""
    import json
    schema_path = os.path.join(os.path.dirname(__file__), "semantic_schema.json")
    try:
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        return {"status": "ok", "schema": schema}
    except FileNotFoundError:
        return {"status": "ok", "schema": {}}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.put("/api/v1/semantic-schema", tags=["workspace"])
def update_semantic_schema_json(payload: dict = Body(...)):
    """Update the semantic_schema.json file."""
    import json
    schema_path = os.path.join(os.path.dirname(__file__), "semantic_schema.json")
    try:
        with open(schema_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, str(e))


# ==========================================
# Workspace DB: Knowledge Document Endpoints
# ==========================================

@app.get("/api/v1/knowledge/chunks", tags=["workspace"])
def get_knowledge_chunks(source: str, limit: int = 5):
    """Get text chunks for a specific document source."""
    from app.utils.clickhouse_client import ch_client
    safe_source = source.replace("'", "''")
    try:
        sql = f"SELECT id, content FROM default.knowledge_base WHERE source = '{safe_source}' LIMIT {limit}"
        result = ch_client.get_client().query(sql)
        chunks = [{"id": r[0], "content": r[1]} for r in result.result_rows]
        return {"status": "ok", "chunks": chunks, "source": source}
    except Exception as e:
        logger.error(f"Knowledge chunks error: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/v1/knowledge/upload-text", tags=["workspace"])
async def upload_text_document(payload: dict = Body(...)):
    """Ingest a raw text/markdown document into the knowledge base."""
    from app.services.rag_service import init_tables, get_embeddings_model
    from app.utils.clickhouse_client import ch_client
    import uuid
    
    content = payload.get("content", "").strip()
    source_name = payload.get("source", "manual_upload.md")
    
    if not content:
        raise HTTPException(400, "content is required")
    
    try:
        init_tables()
        model = get_embeddings_model()
        
        # Simple chunking
        chunks = [content[i:i+1000] for i in range(0, len(content), 800)]
        data = []
        for chunk in chunks:
            if chunk.strip():
                emb = model.embed_query(chunk)
                data.append([uuid.uuid4().hex, source_name, chunk, emb])
        
        if data:
            ch_client.insert("knowledge_base", data, column_names=["id", "source", "content", "embedding"])
        
        return {"status": "ok", "chunks_added": len(data), "source": source_name}
    except Exception as e:
        logger.error(f"Text upload error: {e}")
        raise HTTPException(500, str(e))


# ───────────────────────── Phase 8: Observability UI ───────────────────────
@app.get("/api/v1/admin/metrics", tags=["admin"])
def admin_metrics_endpoint(hours: int = 24):
    """Живые агрегаты системных метрик для страницы «Мониторинг» в админке.

    Считает RPS, латентность LLM, error-rate, расход токенов и разбивку по
    агентам/моделям из таблицы аудита ClickHouse. При отсутствии данных
    возвращает демонстрационный набор (source = "demo").
    """
    from app.services.metrics_service import compute_metrics

    try:
        return compute_metrics(hours=hours)
    except Exception as e:  # pragma: no cover
        logger.error(f"admin metrics error: {e}")
        raise HTTPException(500, str(e))
