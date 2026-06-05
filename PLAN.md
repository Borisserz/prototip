# План реализации улучшений Phase 6/7: Презентация + UI (по запросу пользователя)

## Общие принципы (из AGENTS.md)
- Контракты только через Pydantic v2.
- Графики ТОЛЬКО через viz/charts.py + viz/style.py (никакого exec, никакого хардкода стилей в других местах).
- Весь текст на русском.
- Structured output (call_structured + Pydantic) для всех LLM вызовов.
- Перед коммитом: ruff check . && ruff format . && pytest -q (non-live) зелёные.
- Не переходить к следующему пункту, пока текущий не покрыт тестом и не запускается (генерация презентации / streamlit / uvicorn).
- UI thin client: форма собирает payload, логика в агентах/эндпоинте.
- Логирование через централизованный logger (уже есть).

## План по блокам (выполнять строго по порядку)

### A. Исправить генерацию слайда-графика и стиль (приоритет, т.к. на скрине проблемы с horizontal_bar)

#### A.1. Русские подписи, формат денег без SI-префиксов (B/M/k), Br везде
- viz/style.py:
  - Расширить get_russian_label: добавить маппинг для "total_debt", "sum_debt", "debt_total" и т.п. -> "Задолженность, Br". Сделать нормализацию (strip "total_", "sum_", "avg_" и т.д. перед lookup).
  - Улучшить format_number_ru:
    - Для value >= 1e9: компакт "X, Y млрд Br" (с пробелом в тысячах где нужно).
    - Для 1e6 <= value < 1e9: "X, Y млн Br".
    - Иначе полный с пробелом + " Br".
    - Убрать любые SI (B для billion и т.п.).
    - Обновить docstring.
- viz/charts.py:
  - В местах value labels (bar, horizontal и т.д.) использовать обновлённый format_number_ru(suffix="Br").
  - В kpi и других местах где числа — тоже.
- tests/test_viz_style.py:
  - Добавить тесты на новые кейсы compact + новые колонки (total_debt и т.п.).
- tests/test_viz_charts.py:
  - В test_exported_figure_has_style_for_presentation (или новый) проверить, что для horizontal_bar и bar с debt: axis titles содержат "Задолженность, Br" или "Регион", нет "Total Debt", "total debt", "B" в titles.
- Сгенерировать тестовую презентацию (через python -c с PresentationAgent) и убедиться, что в PNG для horizontal_bar нет английских SI и есть Br (визуально + inspect fig перед export).
- Убедиться, что rebuild в presentation_agent использует это (уже делает rebuild с title="").

#### A.2. horizontal_bar: правильная ориентация, сортировка, подписи значений
- viz/charts.py (горизонтальная ветка):
  - Сортировка: dff = dff.sort_values(y, ascending=False)  # largest first → top в horizontal
  - Убедиться px.bar(x=y, y=x, orientation="h") — категория на Y (лево), значение на X (низ).
  - После apply_common_style + override titles: явно сделать update_xaxes(title= get_russian_label(y) ...), update_yaxes(title= get... (x))
  - Подписи значений у концов баров: уже есть update_traces(text=..., textposition="outside") — убедиться, что для h работает (textposition="outside" или "end").
  - Добавить в регрессионный тест: для horizontal_bar fig: xaxis.title.text содержит "Задолженность, Br", yaxis "Регион", и trace имеет text labels.
- В presentation_agent (rebuild для слайдов): при horizontal_bar принудительно set title="" в slide_spec (уже есть), и возможно дополнительно fig.update_layout(title="") после build.
- Протестировать: сгенерировать презентацию с вопросом "Топ-3 региона по задолженности", открыть слайд, проверить:
  - Категории на левой оси Y, значения на нижней X.
  - Бары отсортированы largest top.
  - Подписи значений у правого конца баров (с Br).
  - Нет "Total Debt".
- Обновить тест в test_presentation.py (mock) или добавить assert на PNG? (для mock сложно, поэтому визуальный + unit на fig).

#### A.3. Слайды Обзор и Рекомендации не полупустые
- app/agents/presentation_agent.py:
  - Для слайда "Обзор": вместо одного большого текста — использовать несколько text box / колонки: карточки с метриками (если есть данные из results), разделители (shapes с линиями), акцентные блоки с цветом DARK_BLUE.
  - Для "Рекомендации": нумерованный список в карточках (rect + text), с иконками (простой текст ★ или bullet), заполнить пространство.
  - Использовать цвета из style (DARK_BLUE, GRAY, FOOTER_COLOR).
  - Добавить footer на все слайды (включая эти).
- Обновить тест_presentation (mock): проверить наличие большего количества shapes/text на этих слайдах, или просто что num_slides правильный и нет заглушки.
- Сгенерировать реальную презентацию и визуально проверить, что слайды Обзор/Рекомендации заполнены аккуратно (не пустые).

После A.1+A.2+A.3: 
- ruff + pytest (non-live + specific viz/presentation tests) зелёные.
- Запустить генерацию презентации: python -c с PresentationAgent.run([...]) — файл создаётся, слайды >= N+4, изображения есть, нет заглушки.
- Приложить 1-2 строки лога рендера (напр. "[Orchestrator] end: png=True" + "[PresentationAgent] narrative: ...") подтверждающие, что стиль применён (через rebuild + build_chart).

### B. Переделать ввод на сайте (ui/streamlit_app.py) со структурой

#### B.1. Форма на клиенте (Streamlit)
- Убрать старый один textarea + примеры.
- Добавить:
  - st.radio("Режим", ["По вопросам", "Свободная тема", "Одним предложением"])
  - st.text_input("Общая тема презентации") (виден всегда или в зависимости от режима).
  - Динамические блоки вопросов:
    - st.session_state["questions"] = list of dicts: {"text": , "chart_type": "auto", "note": ""}
    - Кнопка "Добавить вопрос" — append новый блок.
    - Для каждого: st.expander(f"Вопрос {i}"), внутри text_area для текста, selectbox для типа (["авто", "line", "bar", "donut", "horizontal_bar"]), text_input для заметки.
    - Кнопки удалить для каждого блока.
  - st.file_uploader("Дополнительные изображения / CSV (опционально)", accept_multiple_files=True, type=["png","jpg","csv"])
  - Настройки (st.expander или sidebar): 
    - slider "Число слайдов" (4-12)
    - select "Палитра" (Okabe-Ito / default / ...)
    - checkboxes "Включать титул", "Включать рекомендации"
  - Кнопка primary "Сгенерировать презентацию"
  - После: st.success, st.download_button для .pptx (из ответа API)
- Использовать st.session_state для всего состояния формы (чтобы не терялось).
- Валидация: хотя бы 1 вопрос или тема, etc.

#### B.2. Backend: новый эндпоинт + Pydantic
- app/schemas.py: добавить модель PresentationRequest (Pydantic):
  - mode: Literal["questions", "free_topic", "one_sentence"]
  - overall_theme: str | None
  - questions: list[dict] = [{"text": str, "chart_type": str | None, "note": str | None}, ...]
  - images: list[str] | None (base64 или пути, но для simplicity — metadata)
  - settings: dict (num_slides, palette, include_title, include_recommendations)
- app/main.py: добавить 
  @app.post("/generate_presentation")
  def generate_presentation(payload: PresentationRequest) -> dict:
    # здесь thin: вызвать PresentationAgent или расширить его
    # Для "free_topic" / "one_sentence": использовать LLM (call_structured) чтобы разложить в список вопросов + chart prefs (structured output).
    # Затем pa = PresentationAgent(); res = pa.run(questions_list)
    # Вернуть {"pptx_path": , "num_slides": , "download_url" или bytes? } 
    # Для скачивания — либо возвращать путь, UI качает, либо endpoint /download/{id} но для простоты возвращать base64 или путь, UI читает файл.
- Поскольку UI thin, в streamlit: собрать payload dict, requests.post("http://localhost:8000/generate_presentation", json=payload).json() затем download.
- Для изображений: в payload можно передавать список имен, файлы сохранять во временную папку или base64 (ограничить размер).
- Логика LLM для разложения темы в вопросы — только через structured (новая Pydantic для "expand questions").

#### B.3. Интеграция и тесты
- Обновить ui/streamlit_app.py полностью на новую форму (сохранить старый режим графиков в одной вкладке если нужно, но по задаче — переделать ввод).
- Добавить в app/main.py эндпоинт (использовать существующий PresentationAgent, расширить если нужно для free mode).
- tests/test_app.py или новый: тест эндпоинта с TestClient, mock PresentationAgent и call_structured.
- Обновить test_ui_smoke если нужно (мокать новые).
- Сделать так, чтобы streamlit run ui/streamlit_app.py запускался и форма работала (можно с uvicorn в фоне для теста).
- Для генерации в бэкенде: если mode free — один structured LLM call для получения списка вопросов из темы (Pydantic список), затем PresentationAgent.
- Убедиться, что для "По вопросам" — напрямую использует список из формы.

## Порядок выполнения (строго)
1. Показать этот план (в ответе).
2. Реализовать A.1 полностью (код + тесты + запуск генерации + проверка логов/фиг).
3. Только после зелёных тестов и успешного запуска — A.2.
4. Только после — A.3.
5. Только после A полностью — переходить к B.1 (UI форма), с тестами.
6. B.2 (эндпоинт).
7. B.3 интеграция + финальные гейты (ruff, pytest non-live, streamlit + uvicorn запускаются, презентация генерится из новой формы).
8. В конце — "залей в мейн" (копировать в primary, commit, показать).

Все изменения документировать кратко в коде (комменты где нужно).

Это соответствует "Сначала покажи план, потом код" и "не переходи к следующему пока не покрыт тестом и не запускается".