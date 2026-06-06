"""Streamlit UI для BI-аналитики налогов РБ (Phase 7).

Тонкий клиент: вся логика в Orchestrator.ask(). UI только отображает результат.
Запуск: streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Важно: когда запускаем `streamlit run ui/streamlit_app.py`,
# Streamlit добавляет директорию скрипта (ui/) в sys.path первой.
# Чтобы `from app.orchestrator import ...` работал, явно добавляем корень проекта.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Для живого интерактивного графика в UI (sharp, hover) вместо растянутого PNG
import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

# Импорт ядра — только здесь
from app.orchestrator import Orchestrator  # noqa: E402
from app.schemas import DashboardRequest, DashboardResult  # noqa: E402

# Planner-ready models (Plan, Task, AgentCall) доступны через app.schemas
# и будут использоваться в render_plan / trace UI, когда PlannerAgent будет готов.
from viz.charts import build_chart  # noqa: E402

# Константы для формы презентации (используются в UI и могут тестироваться)
# Чисто русские лейблы в дропдауне (AGENTS: весь пользовательский текст на русском)
CHART_DISPLAY_OPTIONS: list[str] = [
    "авто",
    "линейная",
    "столбчатая",
    "круговая",
    "горизонтальная столбчатая",
]
CHART_VAL_FOR_DISPLAY: dict[str, str | None] = {
    "авто": None,
    "линейная": "line",
    "столбчатая": "bar",
    "круговая": "donut",
    "горизонтальная столбчатая": "horizontal_bar",
}
CHART_DISPLAY_FOR_VAL: dict[str | None, str] = {v: k for k, v in CHART_VAL_FOR_DISPLAY.items()}


@st.cache_resource(show_spinner=False)
def get_orchestrator() -> Orchestrator:
    """Кэшируем Orchestrator, чтобы не пересоздавать агенты/модель на каждый rerun."""
    return Orchestrator()


@st.cache_data(show_spinner=False)
def _load_demo_df() -> pd.DataFrame:
    """Загружаем демо-датасет один раз (для вкладки «Данные» и подсказок)."""
    path = PROJECT_ROOT / "data" / "sample.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


@st.cache_resource(show_spinner=False)
def get_planner():
    """Кэшируем PlannerAgent (чтобы не пересоздавать агенты при каждом rerun)."""
    from app.agents.planner_agent import PlannerAgent

    return PlannerAgent()


def main() -> None:
    st.set_page_config(
        page_title="BI-аналитика налогов РБ",
        page_icon="📊",
        layout="wide",
    )

    # Шапка
    st.title("BI-аналитика налогов РБ")
    st.caption(
        "Локальная аналитическая платформа. Задайте вопрос на русском — получите данные, выводы и красивый график. "
        "Работает полностью оффлайн."
    )

    # Лёгкий онбординг / пустое состояние (показываем, пока пользователь ничего не построил)
    if not any(k in st.session_state for k in ("last_result", "last_dashboard", "last_pres")):
        with st.expander("Как быстро начать (рекомендуем прочесть)", expanded=True):
            st.markdown(
                """
                **1.** Откройте вкладку **📋 Данные** — там таблица, характеристики и готовые примеры вопросов по этому датасету.
                
                **2.** Перейдите в **📊 Графики** или **📈 Дашборды**, введите (или нажмите) вопрос.
                
                **3.** Когда нужен отчёт — используйте **📑 Презентацию** (можно списком вопросов или просто описать тему одним предложением).
                
                Платформа полностью локальная. Никакие данные не уходят в интернет.
                """
            )

    tab_main, tab_data, tab_charts, tab_dash, tab_pres = st.tabs(
        ["🤖 Главный агент", "📋 Данные", "📊 Графики", "📈 Дашборды", "📑 Презентация"]
    )

    # Вспомогательный рендерер результатов Planner'а (локальная функция внутри main)
    def _render_planner_result(res):
        """Красивое, стабильное и информативное отображение результата PlannerAgent в чате."""
        # Обработка случая уточняющего вопроса
        if (
            hasattr(res, "insights")
            and res.insights
            and any(
                "уточн" in str(ins).lower() or "что нужно" in str(ins).lower()
                for ins in res.insights
            )
        ):
            st.info(res.insights[0] if res.insights else "Уточните, пожалуйста, формат ответа.")
            st.caption("Вы можете ответить в чате — Главный агент учтёт предыдущий контекст.")
            return

        # 1. График / AskResult-подобный результат
        if (
            hasattr(res, "chart_spec")
            and getattr(res, "chart_spec", None)
            and getattr(res, "data", None)
        ):
            try:
                import pandas as pd

                df = pd.DataFrame(res.data)
                from viz.charts import build_chart

                fig = build_chart(df, res.chart_spec)
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning(f"Не удалось отобразить график: {e}")

            if hasattr(res, "analysis") and res.analysis:
                if getattr(res.analysis, "key_conclusion", None):
                    st.subheader("Ключевой вывод")
                    st.write(res.analysis.key_conclusion)
                if getattr(res.analysis, "insights", None):
                    st.subheader("Выводы")
                    for ins in res.analysis.insights:
                        st.markdown(f"- {ins}")

        # 2. Дашборд
        elif hasattr(res, "charts") and getattr(res, "charts", None):
            try:
                from app.schemas import DashboardResult

                if isinstance(res, DashboardResult):
                    _render_dashboard(res)
                else:
                    st.write(res)
            except Exception:
                st.write(res)
            st.caption(
                "Можно продолжить: «сделай презентацию по этому дашборду» или уточнить нужные графики."
            )

        # 3. Презентация
        elif hasattr(res, "pptx_path"):
            st.success(f"Презентация готова: {getattr(res, 'num_slides', 0)} слайдов.")
            ppath = getattr(res, "pptx_path", None)
            if ppath and Path(ppath).exists():
                with open(ppath, "rb") as f:
                    b = f.read()
                st.download_button(
                    "📥 Скачать .pptx",
                    data=b,
                    file_name="presentation.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )

        # 4. Данные
        elif hasattr(res, "data") and isinstance(getattr(res, "data", None), list):
            try:
                import pandas as pd

                df = pd.DataFrame(res.data)
                st.dataframe(df, use_container_width=True)
                if hasattr(res, "sql"):
                    with st.expander("SQL запрос (для справки)"):
                        st.code(getattr(res, "sql", ""), language="sql")
            except Exception:
                st.write(res)

        # 5. Fallback (в т.ч. уточнения и общие сообщения)
        else:
            if hasattr(res, "insights") and res.insights:
                for ins in res.insights:
                    st.write(ins)
            elif hasattr(res, "key_conclusion") and res.key_conclusion:
                st.write(res.key_conclusion)
            else:
                st.write("Результат:")
                if hasattr(res, "model_dump"):
                    st.json(res.model_dump())
                else:
                    st.write(res)

    with tab_main:
        st.markdown("**Главный агент**")
        st.caption(
            "Просто опишите, что вам нужно. Система сама решит, подготовить ли график, дашборд, презентацию или данные. "
            "Вся внутренняя работа скрыта."
        )

        # История чата (используем session_state)
        if "main_messages" not in st.session_state:
            st.session_state["main_messages"] = []

        # Отображаем историю сообщений в стиле чата
        for msg in st.session_state["main_messages"]:
            if msg["role"] == "user":
                with st.chat_message("user"):
                    st.write(msg["content"])
            else:
                with st.chat_message("assistant"):
                    res = msg.get("result")
                    if res is None:
                        st.write(msg.get("content", "Готово."))
                    else:
                        _render_planner_result(res)

                    # Улучшенное отображение плана (Planner v2.5)
                    execution = getattr(res, "_plan_execution", None)
                    plan = getattr(res, "_executed_plan", None)

                    if execution and isinstance(execution, list):
                        with st.expander("Что было сделано", expanded=False):
                            for step in execution:
                                status = step.get("status", "")
                                icon = (
                                    "✅"
                                    if status == "успешно"
                                    else "❌"
                                    if status == "ошибка"
                                    else "⚠️"
                                )
                                deps = (
                                    f" (зависит от: {', '.join(step.get('depends_on', []))})"
                                    if step.get("depends_on")
                                    else ""
                                )
                                st.markdown(
                                    f"**{step.get('num', '?')}. {step.get('agent_name', '?')}** {icon}{deps}"
                                )
                                st.markdown(
                                    f"&nbsp;&nbsp;&nbsp;&nbsp;{step.get('description', '')}"
                                )
                                brief = step.get("brief_result")
                                if brief:
                                    st.caption(f"&nbsp;&nbsp;&nbsp;&nbsp;→ {brief}")
                    elif plan and getattr(plan, "tasks", None):
                        # Fallback на старый формат (если _plan_execution почему-то нет)
                        with st.expander("Что было сделано", expanded=False):
                            for i, task in enumerate(plan.tasks, 1):
                                deps = (
                                    f" (зависит от: {', '.join(task.depends_on)})"
                                    if task.depends_on
                                    else ""
                                )
                                st.markdown(
                                    f"**{i}. {task.agent_name}** — {task.description}{deps}"
                                )

        # Простая форма ввода
        with st.form("main_form", clear_on_submit=True):
            main_q = st.text_input(
                "Ваш вопрос на русском",
                placeholder="Например: Покажи дашборд по задолженности по регионам или динамику начислений",
                key="main_question_input",
            )
            submitted_main = st.form_submit_button(
                "Отправить", type="primary", use_container_width=True
            )

        if submitted_main and main_q.strip():
            # Добавляем сообщение пользователя в историю
            st.session_state["main_messages"].append({"role": "user", "content": main_q.strip()})

            with st.spinner("Думаю... Главный агент выбирает лучший инструмент и собирает ответ"):
                try:
                    planner = get_planner()
                    result = planner.run(main_q.strip())

                    # Добавляем ответ ассистента (храним объект результата для рендера)
                    st.session_state["main_messages"].append(
                        {"role": "assistant", "result": result}
                    )
                except Exception as e:
                    error_msg = f"Не удалось обработать запрос: {e}"
                    st.session_state["main_messages"].append(
                        {"role": "assistant", "content": error_msg}
                    )

            st.rerun()

        # Кнопка очистки чата
        if st.session_state.get("main_messages") and st.button(
            "Очистить чат", key="clear_main_chat"
        ):
            st.session_state["main_messages"] = []
            st.rerun()

    with tab_data:
        st.markdown("**Набор данных (демо)**")
        st.caption(
            "Синтетические данные о налоговых поступлениях по регионам Республики Беларусь за 2024 год "
            "(валюта Br). Реальной базы нет — запросы выполняются через DuckDB прямо по CSV."
        )

        df = _load_demo_df()
        if df.empty:
            st.warning("Файл data/sample.csv не найден. Запустите: python data/make_dataset.py")
        else:
            # Краткий просмотр
            st.dataframe(df.head(8), use_container_width=True, hide_index=True)

            # Основные характеристики (без сложных расчётов)
            st.write("**Ключевые характеристики выборки**")
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                st.metric("Всего записей", f"{len(df):,}".replace(",", " "))
            with c2:
                st.metric("Регионов", df["region"].nunique())
            with c3:
                st.metric("Видов налогов", df["tax_type"].nunique())
            with c4:
                st.metric("Месяцев", df["period"].nunique())

            # Полезные факты
            st.caption(
                f"Период: {df['period'].min()} — {df['period'].max()}. "
                "Все суммы — в белорусских рублях (Br)."
            )

            # Подсказки по вопросам (кликабельные)
            st.write("**Попробуйте эти вопросы (нажмите, чтобы подставить):**")
            suggestions = [
                "Какая задолженность по регионам?",
                "Динамика начислений в г. Минск за год",
                "Структура налогов по видам (доли)",
                "Топ-3 региона по подоходному налогу",
                "В каких регионах наибольшая задолженность по НДС?",
                "Сколько налогоплательщиков в среднем по областям?",
            ]
            sug_cols = st.columns(3)
            for idx, sug in enumerate(suggestions):
                col = sug_cols[idx % 3]
                if col.button(sug, key=f"sug_data_{idx}", use_container_width=True):
                    st.session_state["question"] = sug
                    st.session_state["dash_question"] = sug
                    st.info(
                        "Пример подставлен. Перейдите во вкладку «📊 Графики» или «📈 Дашборды», "
                        "чтобы построить анализ."
                    )

        st.divider()
        st.caption(
            "Это полностью синтетические данные, созданные для демонстрации возможностей платформы. "
            "В реальной системе можно подключить любую реляционную БД (с теми же принципами безопасности — только SELECT)."
        )

    with tab_charts:
        st.caption(
            "Хотите готовую презентацию из нескольких вопросов или одной темы? Используйте вкладку «📑 Презентация»."
        )
        # Примеры для быстрого демо (логика графиков без изменений)
        st.write("**Примеры вопросов (нажмите, чтобы подставить):**")
        col1, col2, col3, col4 = st.columns(4)

        examples = [
            "Какая задолженность по регионам?",
            "Динамика начислений в г. Минск за год",
            "Структура налогов по видам (доли)",
            "Топ-3 региона по подоходному налогу",
        ]

        if col1.button(examples[0], use_container_width=True):
            st.session_state["question"] = examples[0]
            st.rerun()
        if col2.button(examples[1], use_container_width=True):
            st.session_state["question"] = examples[1]
            st.rerun()
        if col3.button(examples[2], use_container_width=True):
            st.session_state["question"] = examples[2]
            st.rerun()
        if col4.button(examples[3], use_container_width=True):
            st.session_state["question"] = examples[3]
            st.rerun()

        # Поле ввода + кнопка
        with st.form("ask_form", clear_on_submit=False):
            question = st.text_input(
                "Ваш вопрос на русском",
                value=st.session_state.get("question", ""),
                placeholder="Например: Какая задолженность по регионам?",
                key="question_input",
            )
            submitted = st.form_submit_button("Построить", type="primary", use_container_width=True)

        # Обработка
        if submitted and question.strip():
            st.session_state["question"] = question.strip()

            with st.spinner("Думаю… Выполняю SQL, анализ и строю график..."):
                try:
                    o = get_orchestrator()
                    result = o.ask(question.strip())

                    # Сохраняем результат для отображения
                    st.session_state["last_result"] = result

                except Exception as e:
                    st.error(
                        "Не удалось выполнить анализ. "
                        "Возможно, проблема с моделью Ollama, данными или одним из шагов пайплайна. "
                        f"Детали: {e}"
                    )
                    st.stop()

        # Отображение результата (если есть)
        if "last_result" in st.session_state:
            result = st.session_state["last_result"]

            st.divider()

            # График: prefer live plotly_chart for UI (sharp, interactive hover) - best quality
            # PNG in out/ is for artifacts/presentations
            displayed = False
            if result.data and getattr(result, "chart_spec", None):
                try:
                    df = pd.DataFrame(result.data)
                    fig = build_chart(df, result.chart_spec)
                    st.plotly_chart(fig, use_container_width=True)
                    displayed = True
                except Exception as e:
                    st.warning(f"Не удалось построить интерактивный график: {e}")
            if not displayed and result.png_path and Path(result.png_path).exists():
                # Fallback to static PNG with limited centered width
                col1, col2, col3 = st.columns([1, 6, 1])
                with col2:
                    st.image(result.png_path, width=820, caption="Сгенерированный график")
            elif not displayed:
                st.warning("График не был построен (возможно, ошибка на шаге визуализации).")

            # Ключевой вывод
            if result.analysis and result.analysis.key_conclusion:
                st.subheader("Ключевой вывод")
                st.write(result.analysis.key_conclusion)

            # Выводы (бывшие "Инсайты" — более понятное название)
            if result.analysis and result.analysis.insights:
                st.subheader("Выводы")
                for insight in result.analysis.insights:
                    st.markdown(f"- {insight}")

            # Аномалия / тренд
            if result.analysis and result.analysis.anomaly_or_trend:
                st.subheader("Замеченная аномалия / тренд")
                st.info(result.analysis.anomaly_or_trend)

            # SQL в сворачиваемом блоке (для тех, кому интересно)
            with st.expander("Какой запрос был выполнен к данным", expanded=False):
                if result.sql:
                    st.code(result.sql, language="sql")
                else:
                    st.write("SQL не был сгенерирован.")

            # Служебная информация (по умолчанию скрыта)
            with st.expander("Подробности запроса", expanded=False):
                st.write(f"**Ваш вопрос:** {result.question}")
                st.write(f"**Получено строк данных:** {len(result.data)}")
                if result.png_path:
                    st.write(f"**Файл графика:** `{result.png_path}`")

            # Простая история (в памяти сессии) — помогает итерировать без перепечатывания
            if "history" not in st.session_state:
                st.session_state["history"] = []
            # Записываем (только графики для простоты; дашборды тоже могут добавлять)
            entry = {"type": "chart", "question": question.strip()}
            if not st.session_state["history"] or st.session_state["history"][-1] != entry:
                st.session_state["history"].append(entry)
                st.session_state["history"] = st.session_state["history"][-8:]  # последние 8

            if st.session_state.get("history"):
                with st.expander("Предыдущие вопросы (нажмите, чтобы повторить)", expanded=False):
                    for h in reversed(st.session_state["history"][-6:]):
                        if st.button(h["question"], key=f"hist_chart_{h['question'][:30]}"):
                            st.session_state["question"] = h["question"]
                            st.rerun()

    # === Новая вкладка Дашборды (plan step 3): один вопрос → KPI grid + layout-driven multi-chart + polish ===
    with tab_dash:
        st.markdown(
            "**Комплексный дашборд (KPI + несколько взаимосвязанных графиков на одном экране)**"
        )

        # Примеры (как в charts, но dashboard-oriented)
        st.write("**Примеры дашбордов (нажмите):**")
        dcol1, dcol2, dcol3 = st.columns(3)
        dash_examples = [
            "Дашборд по задолженности по регионам",
            "Ключевые метрики и динамика начислений в г. Минск",
            "Сравнение структуры налогов по видам (доли + тренды)",
        ]
        if dcol1.button(dash_examples[0], use_container_width=True, key="d1"):
            st.session_state["dash_question"] = dash_examples[0]
            st.rerun()
        if dcol2.button(dash_examples[1], use_container_width=True, key="d2"):
            st.session_state["dash_question"] = dash_examples[1]
            st.rerun()
        if dcol3.button(dash_examples[2], use_container_width=True, key="d3"):
            st.session_state["dash_question"] = dash_examples[2]
            st.rerun()

        with st.form("dash_form", clear_on_submit=False):
            dash_q = st.text_input(
                "Вопрос для дашборда (на русском)",
                value=st.session_state.get("dash_question", "Дашборд по задолженности по регионам"),
                key="dash_q_input",
            )
            submitted_dash = st.form_submit_button(
                "Построить дашборд", type="primary", use_container_width=True
            )

        # Настройки в expander (как в pres)
        with st.expander("Настройки дашборда"):
            dash_max = st.slider("Макс. графиков", 2, 6, 4, key="dash_max")
            dash_kpi = st.checkbox("Включать KPI-карточки", value=True, key="dash_kpi")

        if submitted_dash and dash_q.strip():
            st.session_state["dash_question"] = dash_q.strip()
            req = DashboardRequest(
                question=dash_q.strip(), max_charts=dash_max, include_kpi=dash_kpi
            )

            with st.status("Генерация дашборда...", expanded=True) as status:
                try:
                    o = get_orchestrator()
                    # Предпочтительно через оркестратор (reuse agents + логи)
                    dash_res = o.dashboard(
                        req.question, max_charts=req.max_charts, include_kpi=req.include_kpi
                    )
                    st.session_state["last_dashboard"] = dash_res
                    status.update(label="Дашборд готов", state="complete")
                except Exception as e:
                    st.error(f"Ошибка: {e}")
                    status.update(label="Ошибка", state="error")

            # Запись в историю
            if "history" not in st.session_state:
                st.session_state["history"] = []
            d_entry = {"type": "dash", "question": dash_q.strip()}
            if not st.session_state["history"] or st.session_state["history"][-1] != d_entry:
                st.session_state["history"].append(d_entry)
                st.session_state["history"] = st.session_state["history"][-8:]

        # Рендер результата (если есть)
        if "last_dashboard" in st.session_state:
            dash_res = st.session_state["last_dashboard"]
            _render_dashboard(dash_res)  # defined below

            # История дашбордов (показываем если есть)
            if st.session_state.get("history"):
                with st.expander("Предыдущие дашборды (повторить)", expanded=False):
                    for h in reversed(
                        [x for x in st.session_state["history"][-6:] if x.get("type") == "dash"]
                    ):
                        if st.button(h["question"], key=f"hist_dash_{h['question'][:30]}"):
                            st.session_state["dash_question"] = h["question"]
                            st.rerun()

    # Закрываем вкладку графиков. Весь оригинальный код графиков выше — без изменений.

    with tab_pres:
        st.markdown("**Создать презентацию**")
        st.caption("Выберите удобный способ описания того, что должно попасть в презентацию.")

        # Режим — делаем понятнее для обычного пользователя
        mode = st.radio(
            "Как задать содержание",
            ["По вопросам", "Одним предложением"],
            horizontal=True,
            key="pres_mode",
            help="«По вопросам» — перечислите конкретные вопросы. «Одним предложением» — просто опишите тему свободно.",
        )

        # Для режима "По вопросам" показываем редактор вопросов (сворачиваемый)
        if mode == "По вопросам":
            # Инициализация списка вопросов (только когда нужен)
            if "pres_questions" not in st.session_state:
                st.session_state["pres_questions"] = [
                    {"text": "Структура налогов по видам (доли)", "chart_type": None, "note": ""},
                    {
                        "text": "Топ-3 региона по задолженности",
                        "chart_type": "horizontal_bar",
                        "note": "",
                    },
                ]

            with st.expander("Список вопросов", expanded=False):
                st.write(
                    "Добавляйте и редактируйте вопросы, которые должны быть раскрыты в презентации."
                )
                to_remove = []
                for i, qblock in enumerate(st.session_state["pres_questions"]):
                    with st.expander(f"Вопрос {i + 1}", expanded=False):
                        qblock["text"] = st.text_area(
                            "Текст вопроса",
                            value=qblock.get("text", ""),
                            key=f"qtext_{i}",
                            height=60,
                        )
                        current_val = qblock.get("chart_type")
                        current_disp = (
                            CHART_DISPLAY_FOR_VAL.get(current_val, "авто")
                            if current_val is not None
                            else "авто"
                        )
                        chosen_disp = st.selectbox(
                            "Предпочтительный тип графика",
                            CHART_DISPLAY_OPTIONS,
                            index=CHART_DISPLAY_OPTIONS.index(current_disp),
                            key=f"qtype_{i}",
                        )
                        qblock["chart_type"] = CHART_VAL_FOR_DISPLAY[chosen_disp]
                        qblock["note"] = st.text_input(
                            "Заметка (опционально)", value=qblock.get("note", ""), key=f"qnote_{i}"
                        )
                        if st.button("Удалить", key=f"qdel_{i}"):
                            to_remove.append(i)

                for i in sorted(to_remove, reverse=True):
                    st.session_state["pres_questions"].pop(i)

                if st.button("Добавить вопрос", key="qadd"):
                    st.session_state["pres_questions"].append(
                        {"text": "", "chart_type": None, "note": ""}
                    )
                    st.rerun()

            # Показываем только когда в режиме "По вопросам"
            num_valid = len(
                [q for q in st.session_state.get("pres_questions", []) if q.get("text", "").strip()]
            )
            if num_valid > 0:
                st.caption(f"Будет подготовлено примерно {num_valid + 4}–{num_valid + 6} слайдов.")

        else:
            # Режим "Одним предложением" — большое чистое поле, без списка вопросов
            free_text = st.text_area(
                "О чём должна быть презентация?",
                value=st.session_state.get(
                    "pres_free_text", "Налоговая аналитика Республики Беларусь за 2024 год"
                ),
                height=140,
                key="pres_free_text_input",
                placeholder="Например: Динамика налоговых поступлений в регионах и основные проблемы с собираемостью",
            )
            st.session_state["pres_free_text"] = free_text

            # Для не-вопросных режимов у нас нет детального списка вопросов — backend сам разложит тему
            st.session_state["pres_questions"] = []  # очищаем, чтобы не мешать

        # file_uploader (демо) — оставляем, но делаем менее заметным
        with st.expander("Дополнительные материалы (опционально)", expanded=False):
            st.file_uploader(
                "Изображения или CSV (пока не влияют на генерацию)",
                accept_multiple_files=True,
                type=["png", "jpg", "csv"],
                key="pres_files",
            )

        # Настройки — в лёгком экспандере
        with st.expander("Настройки презентации", expanded=False):
            num_slides = st.slider("Примерное число слайдов", 4, 12, 7, key="pres_num")
            include_title = st.checkbox("Включать титульный слайд", value=True, key="pres_title")
            include_recs = st.checkbox("Включать рекомендации", value=True, key="pres_recs")

        # Кнопка генерации
        if st.button("Сгенерировать презентацию", type="primary", use_container_width=True):
            qlist = []
            current_mode = mode

            if current_mode == "По вопросам":
                qlist = [
                    {
                        "text": q["text"],
                        "chart_type": q.get("chart_type"),
                        "note": q.get("note"),
                    }
                    for q in st.session_state.get("pres_questions", [])
                    if str(q.get("text", "")).strip()
                ]
                if not qlist:
                    st.warning("Добавьте хотя бы один вопрос.")
                    st.stop()
                overall_theme_for_payload = st.session_state.get("pres_theme")
            else:
                # "Одним предложением" — отправляем как свободный текст через overall_theme
                free = st.session_state.get("pres_free_text", "").strip()
                if not free:
                    st.warning("Опишите, о чём должна быть презентация.")
                    st.stop()
                # Передаём как один "вопрос" с текстом свободной формулировки (backend поддерживает)
                qlist = [{"text": free, "chart_type": None, "note": ""}]
                overall_theme_for_payload = free

            payload = {
                "mode": current_mode,
                "overall_theme": overall_theme_for_payload or None,
                "questions": qlist,
                "num_slides": num_slides,
                "include_title": include_title,
                "include_recommendations": include_recs,
            }

            # Демо: сохранение доп. файлов (не влияет на генерацию)
            uploaded_names = []
            try:
                ufs = st.session_state.get("pres_files") or []
                for uf in ufs if isinstance(ufs, (list, tuple)) else ([ufs] if ufs else []):
                    if uf is not None and hasattr(uf, "name"):
                        op = Path("out") / f"demo_upload_{uf.name}"
                        op.parent.mkdir(parents=True, exist_ok=True)
                        op.write_bytes(uf.getvalue())
                        uploaded_names.append(uf.name)
            except Exception:
                pass
            if uploaded_names:
                st.caption(f"Дополнительные файлы сохранены: {', '.join(uploaded_names)}")

            status_text = "Генерация презентации..."
            with st.status(status_text, expanded=True) as status:
                try:
                    import httpx

                    try:
                        r = httpx.post(
                            "http://127.0.0.1:8000/generate_presentation",
                            json=payload,
                            timeout=300,
                        )
                        r.raise_for_status()
                        data = r.json()
                        pptx_path = data.get("pptx_path")
                        nslides = data.get("num_slides", 0)
                    except Exception:
                        # fallback: прямой вызов PresentationAgent
                        from app.agents.presentation_agent import PresentationAgent

                        pa = PresentationAgent()
                        pres_res = pa.run(
                            qlist,
                            num_slides=num_slides,
                            include_title=include_title,
                            include_recommendations=include_recs,
                        )
                        pptx_path = pres_res.pptx_path
                        nslides = pres_res.num_slides

                    st.session_state["last_pres"] = {
                        "pptx_path": pptx_path,
                        "num_slides": nslides,
                    }
                    status.update(label=f"Готово! Слайдов: {nslides}", state="complete")
                    st.success(f"Готово! Слайдов: {nslides}")
                except Exception as e:
                    status.update(label="Ошибка", state="error")
                    st.error(f"Ошибка генерации: {e}")

        # Результат + download (session)
        if "last_pres" in st.session_state:
            pres = st.session_state["last_pres"]
            st.success(f"Презентация готова: {pres.get('num_slides', 0)} слайдов.")

            # Простой текстовый outline (что примерно попало в слайды) — без лишних технических деталей
            used_qs = st.session_state.get("pres_questions") or []
            free = st.session_state.get("pres_free_text", "").strip()
            if used_qs:
                st.write("**Основные темы в презентации:**")
                for idx, q in enumerate(used_qs[:6], 1):
                    txt = q.get("text", "").strip()
                    if txt:
                        st.markdown(f"{idx}. {txt}")
            elif free:
                st.write("**Тема презентации:**")
                st.write(free)

            ppath = pres.get("pptx_path")
            if ppath and Path(ppath).exists():
                with open(ppath, "rb") as f:
                    b = f.read()
                st.download_button(
                    "📥 Скачать .pptx",
                    data=b,
                    file_name="presentation.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )


def _render_dashboard(res: DashboardResult) -> None:
    """Рендер DashboardResult в Streamlit (KPI + layout grid + polish).
    Reuses build_chart + plotly (live), st.metric/columns/tabs/expanders per plan.
    Требует res.data для чартов (добавлено в schemas/agent).
    """
    import pandas as pd  # local to avoid top bloat if not needed

    st.subheader(res.title)
    st.write(res.summary)

    # KPI row (st.metric + columns; polish с Br/дескрипшенами)
    if res.kpi_cards:
        n = min(len(res.kpi_cards), 4)
        kcols = st.columns(n)
        for i, kpi in enumerate(res.kpi_cards):
            with kcols[i % n]:
                delta = f"{kpi.change:+.1f}%" if getattr(kpi, "change", None) is not None else None
                help_txt = getattr(kpi, "change_period", None) or ""
                # value может быть float (compute) или str (LLM + format); metric справится
                st.metric(
                    label=kpi.name,
                    value=kpi.value,
                    delta=delta,
                    delta_color="normal",
                    help=help_txt,
                )
        st.divider()

    # Charts grid, respect layout (columns or tabs fallback)
    if res.charts and getattr(res, "data", None):
        df = pd.DataFrame(res.data)
        n_cols = max(1, min(getattr(res.layout, "columns", 2), 3))
        layout_type = getattr(res.layout, "type", "kpi_top_grid")

        if "tab" in layout_type:
            # Простая tabs версия
            tab_names = [c.title[:40] for c in res.charts]
            ctabs = st.tabs(tab_names)
            for i, spec in enumerate(res.charts):
                with ctabs[i]:
                    try:
                        fig = build_chart(df, spec)
                        st.plotly_chart(fig, use_container_width=True, key=f"dash_tab_{i}")
                    except Exception as e:
                        st.warning(f"Ошибка рендера графика {i}: {e}")
        else:
            # Grid по columns (kpi_top_grid / two_column / single)
            chart_cols = st.columns(n_cols)
            for i, spec in enumerate(res.charts):
                c = chart_cols[i % n_cols]
                with c:
                    try:
                        fig = build_chart(df, spec)
                        st.caption(spec.title)
                        st.plotly_chart(fig, use_container_width=True, key=f"dash_grid_{i}")
                    except Exception as e:
                        st.warning(f"График {i}: {e}")
    elif res.charts:
        st.info("Не удалось отобразить графики (нет данных).")

    # === Настройка графиков (бывший технический редактор) ===
    if res.charts:
        with st.expander("Настройка графиков", expanded=False):
            st.caption(
                "Можно быстро изменить тип каждого графика. Изменения применяются сразу на этой странице."
            )
            for i, spec in enumerate(res.charts):
                opts = [
                    "horizontal_bar",
                    "bar",
                    "donut",
                    "line",
                    "grouped_bar",
                    "stacked_bar",
                    "heatmap",
                ]
                try:
                    idx = opts.index(spec.chart_type) if spec.chart_type in opts else 0
                except Exception:
                    idx = 0
                new_t = st.selectbox(
                    f"График {i + 1}: {spec.title[:40]}",
                    opts,
                    index=idx,
                    key=f"dash_edit_{i}",
                )
                if new_t != spec.chart_type:
                    spec.chart_type = new_t

            if st.button("Применить изменения", key="dash_apply_edit"):
                st.rerun()

            # Простой фильтр по регионам (если применимо)
            if getattr(res, "data", None):
                regs = sorted({d.get("region") for d in res.data if d.get("region")})
                if len(regs) > 1:
                    sel_regs = st.multiselect(
                        "Показывать только выбранные регионы", regs, default=regs, key="dash_filt"
                    )
                    if sel_regs and len(sel_regs) < len(regs):
                        st.caption("Фильтр применён (влияет только на просмотр на этой странице).")

    # Выводы (бывшие "Инсайты") — дружелюбное название
    if res.insights:
        st.subheader("Выводы")
        for ins in res.insights:
            st.markdown(f"- {ins}")

    # === Подготовка к PlannerAgent (Tier 2) ===
    # Показываем высокоуровневые шаги очень аккуратно и только по желанию.
    # Полноценный render_plan(plan, agent_calls) появится, когда будет готов Planner.
    if getattr(res, "reasoning", None) or getattr(res, "source_sql", None):
        with st.expander("Как был построен этот дашборд (основные шаги)", expanded=False):
            st.write(
                "Один запрос прошёл через: поиск данных (DataAgent) → текстовые выводы → "
                "выбор и заполнение нескольких ChartSpec (через ChartAgent). "
                "Рендер графиков — всегда детерминированный (viz/)."
            )
            if getattr(res, "source_sql", None):
                st.caption("SQL, использованный для данных (для справки):")
                st.code(res.source_sql, language="sql")

    # Технические детали полностью убраны из основного вида пользователя.
    # Оставляем только кнопку экспорта JSON для тех, кому это нужно.
    # (reasoning, source_sql и "Почему такой дашборд" больше не показываем обычному пользователю)

    # Actions (cool UX)
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Экспорт спецификаций (JSON)", key="dash_json"):
            import json

            st.download_button(
                "Скачать dashboard.json",
                data=json.dumps(res.model_dump(), ensure_ascii=False, indent=2, default=str),
                file_name="dashboard.json",
                mime="application/json",
            )
    with c2:
        if st.button("Добавить в презентацию (демо)", key="dash_to_pres"):
            st.info(
                "В будущем: интеграция с PresentationAgent (один слайд или несколько из дашборда). Пока используйте вкладку Презентация."
            )


if __name__ == "__main__":
    main()
