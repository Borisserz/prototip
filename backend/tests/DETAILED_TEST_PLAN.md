# План тестирования — prototip (LangGraph / ClickHouse)

Детальная стратегия тестирования для графа LangGraph, RAG в ClickHouse, Semantic Engine и React UI.  
Дополняет `pytest`-набор в `tests/`.

**Статус (Фазы 11-15):** Более 150 автотестов (`pytest -m "not live"`). 

**Гейты перед коммитом:**

```bash
ruff check . && ruff format --check .
python -m pytest -m "not live" -q
```

---

## Стратегия

- **pytest** + fixtures (mocked Semantic Engine, ClickHouse DB connection).
- **Детерминизм:** LLM-вызовы внутри узлов графа (`data_node`, `chart_node`) мокаются.
- **SQL Eval:** Особое внимание к тестированию узла `eval_node` (отработка ошибок SQL и Retry в LangGraph).
- **RBAC (RLS):** Обязательные юнит-тесты для `sqlglot` парсера, чтобы убедиться, что токены/роли инжектят правильные `WHERE` фильтры.
- **Интеграция:** Сквозное прохождение состояния (State) по узлам графа `StateGraph`.

---

## Покрытие по компонентам

| Компонент / Узел | Фокус |
|------------------|-------|
| `test_graph.py` | Переходы LangGraph: data_node → eval_node → chart_node → analyst_node |
| `test_sql_eval.py` | Защита от галлюцинаций, валидация синтаксиса AST, retry cycle |
| `test_semantic.py` | Парсинг `data/semantic_model.yaml` в Pydantic `Catalog` |
| `test_rbac.py` | Инъекции `user_context` через `sqlglot` |
| `test_clickhouse_rag.py` | Векторный поиск `cosineDistance` с мок-векторами |
| `test_viz_charts.py` | build_chart, exports, 12 типов графиков + React Plotly mock |
| `test_e2e.py` | Полный цикл `/ws/chat` через FastAPI TestClient (WebSockets) |

---

## 1. LangGraph и Состояния (StateGraph)

**Unit:** Проверка `State` после каждого узла.
**Integration:** Отправка вопроса в `graph.invoke()` и проверка полного цикла генерации SQL, графика и текста.

## 2. Безопасность и RBAC (Row-Level Security)

**Unit:** Подача запроса `SELECT * FROM sales` с контекстом `role=minsk_manager`. Ожидается `SELECT * FROM sales WHERE region='Минск'`.
Тест падает, если парсер не вставляет фильтр.

## 3. SQL Eval (eval_node)

**Unit:** Подача синтаксически неверного запроса. Узел должен вернуть `isValid = False` и вернуть State обратно в `data_node` на перегенерацию.

## 4. UI / UX (React + WebSocket)

**Smoke:**
- Подключение к WebSocket endpoint `/ws/chat`.
- Отправка JSON payload.
- Получение SSE событий со статусами (streaming).

---

## Чеклист перед демо

1. `docker-compose up -d` (запуск ClickHouse).
2. `ollama list` — проверить наличие `qwen2.5-coder:7b-instruct`.
3. Запуск бэкенда: `uvicorn app.main:app`.
4. Запуск фронтенда: `npm run dev` в папке `frontend_web`.
5. Тестовые вопросы с Drill-down:
   - Кликнуть по городу Минск на графике. Убедиться, что отправляется новый запрос с фильтром.
   - Выгрузить график в PNG.
   - Скачать данные в Excel.