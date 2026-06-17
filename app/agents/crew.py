import logging
from typing import Any

logger = logging.getLogger(__name__)

def mock_llm_json_orchestrator(query: str) -> dict[str, Any]:
    """
    Симуляция Оркестратора.
    В реальности здесь вызовется LLM с промптом: 
    "Верни JSON: {intent: str, needs_chart: bool, needs_presentation: bool, entities: dict}"
    """
    query_lower = query.lower()
    needs_chart = "график" in query_lower or "покажи" in query_lower
    needs_presentation = "презентаци" in query_lower
    
    return {
        "intent": "analytics" if "налог" in query_lower or "задолженность" in query_lower else "general",
        "needs_chart": needs_chart,
        "needs_presentation": needs_presentation,
        "entities": {"query": query}
    }

class PlannerAgent:
    """
    Planner Agent читает JSON и вызывает нужных агентов по цепочке.
    Вместо хардкода последовательного Crew, он динамически маршрутизирует поток.
    """
    def __init__(self):
        # Импорт специфичных агентов (заглушки для примера)
        pass

    def run_plan(self, orchestration_json: dict[str, Any]) -> str:
        logger.info(f"Планер получил JSON: {orchestration_json}")
        
        result = "Данные: "
        
        # 1. Data Agent (SQL / RAG)
        logger.info("-> Вызов Data Agent...")
        result += "Получены данные из ClickHouse. "
        
        # 2. Analysis Agent
        logger.info("-> Вызов Analysis Agent...")
        result += "Проведен анализ задолженности. "
        
        # 3. Chart Agent
        if orchestration_json.get("needs_chart"):
            logger.info("-> Вызов Chart Agent...")
            result += "Сгенерирован график Plotly. "
            
        # 4. Presentation Agent
        if orchestration_json.get("needs_presentation"):
            logger.info("-> Вызов Presentation Agent...")
            result += "Сгенерирована презентация. "
            
        return result

def run_crew_orchestrator(query: str):
    """
    Главная точка входа, соответствующая архитектуре из стенограммы.
    """
    # 1. Оркестратор парсит текст в JSON
    orchestrator_json = mock_llm_json_orchestrator(query)
    
    # 2. Планер выполняет маршрутизацию
    planner = PlannerAgent()
    final_output = planner.run_plan(orchestrator_json)
    
    return final_output
