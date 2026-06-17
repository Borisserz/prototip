import logging
from typing import Any, Annotated, TypedDict, Optional
from langgraph.graph import StateGraph, START, END, MessagesState

from app.agents.factory import get_executor
from app.agents.models import AskResult, DashboardResult, PresentationResult, DrilldownContext
from app.config import config

logger = logging.getLogger("LangGraph")

import json
from langchain_core.messages import HumanMessage, AIMessage, AnyMessage
from langgraph.graph.message import add_messages

from app.agents.rag_agent import RagAgent
from app.agents.data_agent import DataAgent
from app.agents.analyst_agent import AnalystAgent
from app.agents.chart_agent import ChartAgent
from app.agents.models import AskResult, DashboardResult, PresentationResult, DrilldownContext
from app.config import config

logger = logging.getLogger("LangGraph")

class GraphState(TypedDict):
    question: str
    drilldown: Optional[DrilldownContext]
    user_role: Optional[str]
    
    # State accumulated
    business_context: Optional[str]
    sub_questions: Optional[list[str]]
    raw_data: Optional[list]
    sql: Optional[str]
    analysis: Optional[str]
    chart_spec: Optional[dict]
    
    final_result: Optional[Any]
    error: Optional[str]
    
    messages: Annotated[list[AnyMessage], add_messages]
    
    # Reviewer flow
    raw_analysis_dict: Optional[dict]
    eval_feedback: Optional[str]
    eval_retry_count: Optional[int]

def planner_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Планировщик")
    logger.info(f"[Planner Node] Extracting business context for: {state['question']}")
    # Use RagAgent to get context (simplification of Planner)
    rag = RagAgent()
    res = rag.run(state["question"])
    context = res.context if res.success else "Контекст не найден."
    
    from app.agents.task_decomposer import TaskDecompositionAgent
    decomposer = TaskDecompositionAgent()
    tasks = decomposer.decompose(state["question"], context)
    
    return {
        "business_context": context,
        "sub_questions": tasks
    }

def supervisor_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Маршрутизатор")
    logger.info(f"[Supervisor Node] Evaluating route for: {state['question']}")
    
    # CRITICAL: If drilldown context is present, ALWAYS route to data agent.
    # Never use direct_answer for drilldown requests.
    if state.get("drilldown"):
        drilldown = state["drilldown"]
        filters = getattr(drilldown, 'filters', {}) if hasattr(drilldown, 'filters') else drilldown.get('filters', {})
        logger.info(f"[Supervisor Node] Drilldown detected -> forcing route=data. Filters: {filters}")
        # CRITICAL: Explicitly clear final_result to prevent stale cached results
        # from search_node leaking through and causing route_after_supervisor to
        # short-circuit to END.
        return {"route": "data", "final_result": None}
    
    from core.llm import call_structured
    from app.agents.models import SupervisorDecision
    
    prompt = f"""
Ты — Supervisor Node аналитической системы.
Твоя задача — определить, нужен ли для ответа на вопрос пользователя SQL-запрос к базе данных, или ты можешь ответить напрямую.

Если вопрос требует агрегации, поиска, группировки конкретных цифр по налогам, регионам, задолженностям — выбирай маршрут "data".
Если вопрос — это приветствие, благодарность, запрос помощи (например, "Что ты умеешь?") или вопрос, не требующий вычислений, — выбирай "direct_answer" и напиши ответ.

Вопрос пользователя: {state['question']}
Найденный контекст: {state.get('business_context', '')}
"""
    try:
        decision = call_structured(prompt, SupervisorDecision, system="Ты — маршрутизатор. Отвечай строго в JSON.", agent_name="supervisor_node")
        logger.info(f"[Supervisor Node] Route decided: {decision.route}")
        if decision.route == "direct_answer":
            # If direct answer, we package the final result directly
            from app.agents.models import AskResult
            return {
                "final_result": AskResult(
                    question=state["question"],
                    success=True,
                    reasoning=decision.direct_response or "Готов помочь!",
                    charts=[]
                ),
                "route": "direct_answer"
            }
        return {"route": "data"}
    except Exception as e:
        logger.error(f"[Supervisor Node] Fallback to data due to error: {e}")
        return {"route": "data"}


def data_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Data Agent (SQL)")
    logger.info(f"[Data Node] Fetching data...")
    agent = DataAgent()
    user_role = state.get("user_role", "manager")
    
    sub_questions = state.get("sub_questions")
    if not sub_questions:
        sub_questions = [state["question"]]
    
    # Extract drilldown filters if present
    drilldown = state.get("drilldown")
    drilldown_filters = None
    if drilldown and hasattr(drilldown, 'filters') and drilldown.filters:
        drilldown_filters = drilldown.filters
        logger.info(f"[Data Node] Drilldown filters detected: {drilldown_filters}")
    elif drilldown and isinstance(drilldown, dict) and drilldown.get('filters'):
        drilldown_filters = drilldown['filters']
        logger.info(f"[Data Node] Drilldown filters (dict) detected: {drilldown_filters}")
        
    all_raw_data = []
    all_sql = []
    
    from app.agent_context import user_context
    from app.agents.models import DataAgentInput
    with user_context(user_role):
        for idx, task in enumerate(sub_questions):
            logger.info(f"[Data Node] Running sub-task {idx+1}/{len(sub_questions)}: {task}")
            
            # Build DataAgentInput with drilldown filters
            inp = DataAgentInput(
                question=f"Контекст: {state.get('business_context', '')}\nВопрос: {task}\nРоль пользователя (RBAC): {user_role}",
                drilldown_filters=drilldown_filters
            )
            res = agent.run(inp)
            
            if not res.success:
                return {"error": f"Ошибка в подзадаче '{task}': {res.error}"}
                
            # Добавляем маркер подзадачи, чтобы Аналитик не запутался
            task_data = res.data or []
            if len(sub_questions) > 1:
                for row in task_data:
                    row["_task"] = task
                    
            all_raw_data.extend(task_data)
            
            if getattr(res, "sql", None):
                all_sql.append(f"-- Подзадача: {task}\n{res.sql}")

    combined_sql = "\n\n".join(all_sql)
    return {"raw_data": all_raw_data, "sql": combined_sql}

def analyst_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Аналитик")
    logger.info(f"[Analyst Node] Analyzing data...")
    if state.get("error"):
        return {}
    
    from app.agent_context import emit_debate
    emit_debate("Analyst", "Анализирую данные и формирую выводы...")
    
    # If there's a drilldown context, enrich the question for analyst so it provides specific insights
    effective_question = state["question"]
    drilldown = state.get("drilldown")
    if drilldown:
        filters = getattr(drilldown, 'filters', {}) if hasattr(drilldown, 'filters') else drilldown.get('filters', {})
        dimension = getattr(drilldown, 'dimension', '') if hasattr(drilldown, 'dimension') else drilldown.get('dimension', '')
        segment = getattr(drilldown, 'segment_label', '') if hasattr(drilldown, 'segment_label') else drilldown.get('segment_label', '')
        if filters:
            filter_str = ", ".join(f"{k}={v}" for k, v in filters.items())
            effective_question = f"{state['question']} [DRILL-DOWN: Сфокусируй анализ на: {filter_str}. Предоставь детальный разбор именно по этому сегменту.]"
    
    agent = AnalystAgent()
    res = agent.run(
        question=effective_question, 
        data=state.get("raw_data", []),
        previous_feedback=state.get("eval_feedback")
    )
    if not res.success:
        emit_debate("Analyst", f"Ошибка: {res.error}")
        return {"error": res.error}
        
    emit_debate("Analyst", f"Выводы готовы. Ключевой инсайт: {res.key_conclusion}")
    if not res.success:
        return {"error": res.error}
        
    analysis_dict = {
        "insights": res.insights,
        "key_conclusion": res.key_conclusion,
        "anomaly_or_trend": res.anomaly_or_trend
    }
    return {
        "analysis": res.reasoning, 
        "raw_analysis_dict": analysis_dict
    }

def reviewer_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Критик (CDO)")
    logger.info(f"[Reviewer Node] Critiquing analysis...")
    if state.get("error"):
        return {}
        
    from app.agent_context import emit_debate
    emit_debate("Reviewer", "CDO (Критик) проверяет аналитику на галлюцинации и бизнес-ценность...")
    
    retries = state.get("eval_retry_count", 0)
    if retries >= 1: # Max 1 retry for debate
        logger.info("[Reviewer Node] Max retries reached, accepting analysis.")
        emit_debate("Reviewer", "Лимит попыток исправления исчерпан. Пропускаю текущую версию.")
        return {"eval_feedback": None}
        
    from app.agents.reviewer_agent import ReviewerAgent
    reviewer = ReviewerAgent()
    decision = reviewer.evaluate(
        question=state["question"], 
        analysis=state.get("raw_analysis_dict", {}),
        raw_data=state.get("raw_data", [])
    )
    
    if decision.is_good:
        logger.info("[Reviewer Node] Analysis approved.")
        emit_debate("Reviewer", "Аналитика одобрена. Выводы корректны и опираются на цифры.")
        return {"eval_feedback": None}
    else:
        logger.warning(f"[Reviewer Node] Analysis rejected: {decision.feedback}")
        emit_debate("Reviewer", f"Аналитика отклонена! Замечание: {decision.feedback}")
        return {
            "eval_feedback": decision.feedback,
            "eval_retry_count": retries + 1
        }


def presenter_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("Презентация")
    logger.info(f"[Presenter Node] Formatting output...")
    q_lower = state["question"].lower()
    
    if "презентац" in q_lower or "слайд" in q_lower:
        logger.info("[Presenter Node] Presentation requested. Calling PresentationAgent.")
        from app.agents.presentation_agent import PresentationAgent
        
        # Найти предыдущий вопрос пользователя, чтобы на его основе сделать презентацию
        pres_qs = []
        from langchain_core.messages import HumanMessage
        for m in reversed(state.get("messages", [])):
            if isinstance(m, HumanMessage) and "презентац" not in m.content.lower():
                pres_qs.append(m.content)
                break
        if not pres_qs:
            pres_qs = ["Общий отчет по показателям"]
            
        try:
            pres_agent = PresentationAgent()
            pres_result = pres_agent.run(pres_qs)
            final_reasoning = f"Презентация готова! Вы можете скачать ее здесь: <a href=\"/api/v1/download?file={pres_result.pptx_path}\" download target=\"_blank\">Скачать .pptx</a>"
            return {"final_result": AskResult(
                question=state["question"], 
                success=True, 
                reasoning=final_reasoning, 
                charts=[],
                pptx_path=pres_result.pptx_path
            )}
        except Exception as e:
            logger.error(f"[Presenter Node] Presentation error: {e}")
            return {"final_result": AskResult(
                question=state["question"], 
                success=False, 
                reasoning=f"Ошибка при генерации презентации: {e}", 
                charts=[]
            )}

    if state.get("error"):
        error_msg = str(state["error"])
        friendly_error = f"Извините, при анализе данных произошла ошибка. Я не смог выполнить запрос.\n\nТехнические детали: {error_msg}"
        return {"final_result": AskResult(
            question=state["question"], 
            success=False, 
            reasoning=friendly_error,
            error=error_msg,
            charts=[]
        )}

    
    if "прогноз" in q_lower:
        logger.info("[Presenter Node] Forecast requested. Using ForecastAgent.")
        from app.agents.forecast_agent import ForecastAgent
        chart_agent = ForecastAgent()
        chart_res = chart_agent.run(state["question"], data=state.get("raw_data", []))
        chart_specs = [chart_res.specs[0]] if chart_res.success and chart_res.specs else []
        final_text = state.get("analysis", "Анализ завершен.")
        # Create a simplified version of chart_dicts without the huge 'data' arrays for LLM memory
        memory_result = {
            "title": chart_res.specs[0].title if chart_res.success and chart_res.specs else "Forecast",
            "charts": [{"chart_type": spec.chart_type, "title": spec.title} for spec in chart_specs]
        }
        final_reasoning = json.dumps(memory_result, ensure_ascii=False)
    else:
        logger.info("[Presenter Node] Dashboard requested. Using DashboardAgent.")
        from app.agents.dashboard_agent import DashboardAgent
        from app.agents.models import DashboardRequest
        dash_agent = DashboardAgent()
        # CRITICAL: Pass raw_data from graph state so DashboardAgent doesn't re-fetch
        raw_data = state.get("raw_data", [])
        logger.info(f"[Presenter Node] Passing {len(raw_data)} rows of raw_data to DashboardAgent")
        # Also pass drilldown_filters so DashboardAgent uses them if it needs to refetch
        drilldown = state.get("drilldown")
        dd_filters = None
        if drilldown:
            if hasattr(drilldown, 'filters'):
                dd_filters = drilldown.filters
            elif isinstance(drilldown, dict):
                dd_filters = drilldown.get('filters')
        req = DashboardRequest(question=state["question"], data=raw_data, max_charts=4, drilldown_filters=dd_filters)
        dash_res = dash_agent.run(req)
        
        final_text = dash_res.summary + "\n\n"
        if dash_res.kpi_cards:
            final_text += "### Ключевые показатели (KPI):\n"
            for kpi in dash_res.kpi_cards:
                change_str = f" ({'+' if (kpi.change or 0)>0 else ''}{kpi.change}% {kpi.change_period})" if kpi.change else ""
                final_text += f"- **{kpi.name}**: {kpi.value} {kpi.unit}{change_str}\n"
        
        if dash_res.insights:
            final_text += "\n### Главные выводы:\n"
            for ins in dash_res.insights:
                final_text += f"- {ins}\n"
                
        chart_specs = dash_res.charts
        
        chart_json = ""
        if chart_specs:
            chart_dicts = []
            for spec in chart_specs:
                chart_dicts.append({
                    "chart_type": spec.chart_type,
                    "title": spec.title,
                    "data": state.get("raw_data", [])
                })
            
            blocks = []
            for cd in chart_dicts:
                blocks.append(f"```json\n{json.dumps(cd, ensure_ascii=False)}\n```")
            chart_json = "\n\n".join(blocks)
            
        final_reasoning = final_text + "\n\n" + chart_json
        
    q_lower = state["question"].lower()
    if "отправь" in q_lower and ("почт" in q_lower or "email" in q_lower or "e-mail" in q_lower):
        logger.info("[Presenter Node] Email delivery requested. Calling EmailDeliveryTool.")
        from app.crew.tools import EmailDeliveryTool
        delivery_tool = EmailDeliveryTool()
        delivery_status = delivery_tool._run(final_reasoning)
        final_reasoning += f"\n\n**Статус доставки**: {delivery_status}"
        
    excel_path = None
    if "excel" in q_lower or "эксель" in q_lower or "таблиц" in q_lower:
        if state.get("raw_data"):
            logger.info("[Presenter Node] Excel export requested.")
            try:
                from app.services.excel_renderer import ExcelRenderer
                from pathlib import Path
                import uuid
                excel_bytes = ExcelRenderer.render_json_to_excel(json.dumps(state["raw_data"]))
                out_dir = Path("out")
                out_dir.mkdir(exist_ok=True)
                excel_filename = f"report_{uuid.uuid4().hex[:8]}.xlsx"
                excel_filepath = out_dir / excel_filename
                with open(excel_filepath, "wb") as f:
                    f.write(excel_bytes)
                excel_path = str(excel_filepath)
                logger.info(f"[Presenter Node] Excel saved to {excel_path}")
            except Exception as e:
                logger.error(f"[Presenter Node] Error generating Excel: {e}")

    return {"final_result": AskResult(
        question=state["question"], 
        success=True, 
        reasoning=final_reasoning, 
        charts=chart_specs,
        sql=state.get("sql", ""),
        excel_path=excel_path
    )}

def search_node(state: GraphState) -> dict:
    # CRITICAL: Skip search entirely when drilldown is present.
    # Otherwise search_node may set final_result which persists in LangGraph state
    # and causes route_after_supervisor to short-circuit to END, returning the
    # cached/previous response instead of running a fresh drilldown query.
    if state.get("drilldown"):
        logger.info("[Search Node] Drilldown present — skipping search cache entirely.")
        return {}
    
    from app.agent_context import emit_node_event
    emit_node_event("Глобальный Поиск")
    logger.info(f"[Search Node] Checking for existing reports...")
    from app.crew.tools import SearchPastReportsTool
    tool = SearchPastReportsTool()
    res = tool._run(state["question"])
    
    if "Найден релевантный сохраненный дашборд" in res:
        logger.info("[Search Node] Exact match found! Skipping heavy SQL generation.")
        # Extract json part
        try:
            import json
            json_str = res.split("Найден релевантный сохраненный дашборд:\n")[1]
            dash_data = json.loads(json_str)
            # Create a pseudo ChartSpec from dashboard charts
            return {
                "final_result": AskResult(
                    question=state["question"], 
                    success=True, 
                    reasoning=json.dumps(dash_data["charts"], ensure_ascii=False),
                    charts=[]  # we pass it in reasoning for now
                )
            }
        except Exception as e:
            logger.error(f"[Search Node] Error parsing dashboard: {e}")
            
    return {}

def doc_search_node(state: GraphState) -> dict:
    from app.agent_context import emit_node_event
    emit_node_event("RAG Поиск")
    logger.info(f"[Doc Search Node] Searching RAG context concurrently...")
    try:
        from app.services.rag_service import get_rag_context
        ctx = get_rag_context(state["question"])
        return {"business_context": ctx} if ctx else {}
    except Exception as e:
        logger.error(f"[Doc Search Node] Error: {e}")
        return {}

def route_after_search(state: GraphState) -> str:
    # If drilldown context is present, always skip cache and go to planner
    if state.get("drilldown"):
        return "planner"
    if state.get("final_result"):
        return "end"
    return "planner"

def route_after_supervisor(state: GraphState) -> str:
    # CRITICAL: If drilldown is present, always go to data agent regardless of
    # any stale final_result that may have leaked from search_node.
    if state.get("drilldown"):
        return "data"
    if state.get("final_result"):
        return "end"
    # Route to data agent (sequential: data -> analyst)
    return "data"


from langgraph.checkpoint.memory import MemorySaver

def route_after_reviewer(state: GraphState) -> str:
    if state.get("eval_feedback"):
        return "analyst"
    return "presenter"

def build_graph() -> StateGraph:
    workflow = StateGraph(GraphState)
    
    workflow.add_node("search", search_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("data", data_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("presenter", presenter_node)

    
    workflow.add_edge(START, "search")
    
    workflow.add_conditional_edges(
        "search",
        route_after_search,
        {
            "end": END,
            "planner": "planner"
        }
    )
    
    workflow.add_edge("planner", "supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {
            "end": END,
            "data": "data"
        }
    )
    
    workflow.add_edge("data", "analyst")
    workflow.add_edge("analyst", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        route_after_reviewer,
        {
            "analyst": "analyst",
            "presenter": "presenter"
        }
    )
    workflow.add_edge("presenter", END)
    
    memory = MemorySaver()
    
    return workflow.compile(checkpointer=memory)

graph = build_graph()
