import yaml
from crewai import Agent
from app.crew.tools import QueryClickhouseTool, FetchWrenContextTool
import os

# Загружаем MDL (Semantic Layer)
def load_mdl():
    path = os.path.join(os.path.dirname(__file__), '../../data/semantic_model.yaml')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception:
        return "Семантическая модель недоступна."

semantic_model_str = load_mdl()

# Инициализация кастомных инструментов
query_tool = QueryClickhouseTool()
wren_context_tool = FetchWrenContextTool()

try:
    from app.crew.tools import ChromaSearchTool
    chroma_tool = ChromaSearchTool()
except ImportError:
    chroma_tool = None

def create_rag_consultant_agent(llm) -> Agent:
    return Agent(
        role="Нормативный Консультант (Налоговый Кодекс)",
        goal="Изучить вопрос пользователя и найти точные правила и формулы в базе знаний (ChromaDB) перед тем, как SQL-специалист начнет писать запрос.",
        backstory="Вы эксперт по методологии и нормативным документам. Вы точно знаете, какие фильтры и типы данных нужно использовать для разных бизнес-терминов.",
        verbose=True,
        allow_delegation=False,
        tools=[chroma_tool] if chroma_tool else [],
        llm=llm
    )

def create_manager_agent(llm):
    return Agent(
        role='Оркестратор Аналитики (Manager)',
        goal='Координировать работу агентов для выполнения сложных аналитических запросов пользователя.',
        backstory="""Вы — руководитель аналитического отдела. Ваша задача — получить запрос от пользователя, 
делегировать написание SQL запроса SQL-специалисту, затем передать сырые данные Аналитику для поиска инсайтов, 
и в конце передать Презентеру для финального форматирования ответа.""",
        verbose=True,
        allow_delegation=True,
        llm=llm
    )

def create_sql_specialist_agent(llm):
    return Agent(
        role='SQL Специалист по ClickHouse (Text-to-SQL)',
        goal='Переводить вопросы на естественном языке в валидные ClickHouse SQL запросы и получать данные.',
        backstory=f"""Вы эксперт по ClickHouse. Вы работаете со следующей семантической моделью:
        
{semantic_model_str}

Правила ClickHouse:
1. Для фильтрации по году используй: toYear(period) = 2024 (period имеет тип Date).
2. Никогда не используй LIKE 'YYYY-%' для дат.
3. Добавляй LIMIT 100 к каждому запросу.
4. Используй инструмент fetch_wren_context для запроса бизнес-контекста, если структура БД не ясна.
""",
        verbose=True,
        allow_delegation=False,
        tools=[query_tool, wren_context_tool],
        llm=llm
    )

def create_data_analyst_agent(llm):
    return Agent(
        role='Бизнес-Аналитик Данных',
        goal='Находить аномалии, тренды и ключевые инсайты в предоставленных сырых данных.',
        backstory="""Вы опытный data scientist и бизнес-аналитик. Вам дают сырые таблицы (результат SQL-запроса), 
и вы должны проанализировать их: указать на отклонения, выделить лидеров/аутсайдеров и сформулировать 2-3 ключевых вывода.""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

def create_presenter_agent(llm):
    return Agent(
        role='Презентер и Коммуникатор',
        goal='Формировать красивый, понятный бизнес-ответ для конечного пользователя.',
        backstory="""Вы отвечаете за финальную коммуникацию. Вы берете выводы аналитика и формируете 
структурированный markdown-ответ. Если уместно, вы рекомендуете тип графика для UI (Line chart, Bar chart).""",
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

def create_report_search_agent(llm) -> Agent:
    try:
        from app.crew.tools import SearchPastReportsTool
        search_tool = SearchPastReportsTool()
    except ImportError:
        search_tool = None
        
    return Agent(
        role="Агент-поисковик отчетов (Report Search Agent)",
        goal="Проверить, нет ли уже готовых ответов или графиков по похожему вопросу в дашбордах пользователя.",
        backstory="Вы первый рубеж. Перед тем как запускать ресурсоемкий SQL-движок, вы проверяете закэшированные или сохраненные на дашборде отчеты.",
        verbose=True,
        allow_delegation=False,
        tools=[search_tool] if search_tool else [],
        llm=llm
    )
