import logging
import time

from crewai import Crew, Process
from langchain_openai import ChatOpenAI
from prometheus_client import Histogram

from app.crew.agents import (
    create_data_analyst_agent,
    create_manager_agent,
    create_presenter_agent,
    create_rag_consultant_agent,
    create_sql_specialist_agent,
)
from app.crew.tasks import (
    create_analysis_task,
    create_presentation_task,
    create_rag_consultation_task,
    create_sql_task,
)

logger = logging.getLogger("crew_orchestrator")

# Prometheus metric
agent_execution_duration = Histogram(
    "agent_execution_duration_seconds",
    "Time spent running the analytical crew",
    ["status"]
)

# По умолчанию используем локальный LLM (Ollama) или OpenAI, если задан ключ
llm = ChatOpenAI(model_name="gpt-4o", temperature=0.1)

def run_analytical_crew(user_question: str) -> str:
    """Запускает мультиагентный граф CrewAI для обработки вопроса."""
    start_time = time.time()
    logger.info(f"Starting CrewAI orchestration for question: {user_question}")
    
    try:
        # Инициализация агентов
        rag_agent = create_rag_consultant_agent(llm)
        create_manager_agent(llm)
        sql_agent = create_sql_specialist_agent(llm)
        analyst_agent = create_data_analyst_agent(llm)
        presenter_agent = create_presenter_agent(llm)
        
        # Инициализация тасков
        rag_task = create_rag_consultation_task(rag_agent, user_question)
        sql_task = create_sql_task(sql_agent, user_question)
        analysis_task = create_analysis_task(analyst_agent)
        presentation_task = create_presentation_task(presenter_agent)
        
        # Сборка Crew
        analytics_crew = Crew(
            agents=[rag_agent, sql_agent, analyst_agent, presenter_agent],
            tasks=[rag_task, sql_task, analysis_task, presentation_task],
            manager_llm=llm,
            process=Process.hierarchical,
            memory=True,
            verbose=True
        )
        
        # Запуск выполнения с отслеживанием токенов
        from langchain_community.callbacks import get_openai_callback
        with get_openai_callback() as cb:
            result = analytics_crew.kickoff()
            
            # Логируем затраты
            logger.info("CrewAI LLM Usage", extra={
                "event": "llm_cost_tracking",
                "total_tokens": cb.total_tokens,
                "prompt_tokens": cb.prompt_tokens,
                "completion_tokens": cb.completion_tokens,
                "total_cost_usd": cb.total_cost
            })
        
        duration = time.time() - start_time
        agent_execution_duration.labels(status="success").observe(duration)
        logger.info("CrewAI processing completed", extra={"event": "crew_execution", "duration_s": duration, "status": "success"})
        
        return str(result)
        
    except Exception as e:
        duration = time.time() - start_time
        agent_execution_duration.labels(status="error").observe(duration)
        logger.error(f"Crew execution failed: {e}", extra={"event": "crew_execution", "duration_s": duration, "status": "error"})
        return f"Ошибка при выполнении аналитики: {str(e)}"

if __name__ == "__main__":
    # Для ручного тестирования
    q = "Покажи задолженность по НДС по всем областям за 2024 год"
    print(run_analytical_crew(q))
