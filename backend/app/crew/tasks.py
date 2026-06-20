from crewai import Task


def create_rag_consultation_task(agent, user_question: str):
    return Task(
        description=f"""Пользователь задал вопрос: '{user_question}'.
1. Проанализируй вопрос на наличие терминов или методики, требующей пояснения из нормативной базы.
2. Воспользуйся инструментом поиска по базе знаний (Qdrant).
3. Подготовь выжимку с правилами, которые должен учесть SQL-специалист при написании запроса.""",
        expected_output="Юридическая и методологическая справка для SQL-специалиста (или сообщение об отсутствии таковой).",
        agent=agent
    )

def create_sql_task(agent, user_question: str):
    return Task(
        description=f"""Пользователь задал вопрос: '{user_question}'
1. Изучи семантическую модель данных.
2. Напиши валидный ClickHouse SELECT запрос.
3. Выполни этот запрос с помощью инструмента query_clickhouse.
4. Верни сырые данные, полученные из БД.""",
        expected_output="Сырые данные в виде таблицы или списка записей.",
        agent=agent
    )

def create_analysis_task(agent):
    return Task(
        description="""Проанализируй полученные от SQL-специалиста сырые данные.
1. Найди тенденции, максимальные/минимальные значения или аномалии.
2. Сделай краткие бизнес-выводы (инсайты).""",
        expected_output="Список из 2-4 бизнес-инсайтов на основе данных.",
        agent=agent
    )

def create_presentation_task(agent):
    return Task(
        description="""Возьми бизнес-выводы от аналитика и сформируй финальный ответ для пользователя.
Ответ должен быть в формате Markdown. Если данные хорошо подходят для визуализации, 
напиши рекомендацию в формате: [RECOMMEND_CHART: bar|line|pie].""",
        expected_output="Красиво отформатированный ответ в Markdown с инсайтами и рекомендацией по графику.",
        agent=agent
    )
