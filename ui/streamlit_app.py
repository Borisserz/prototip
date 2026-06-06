"""Streamlit UI для BI-аналитики налогов РБ — премиальный чат-интерфейс.

Тонкий клиент: вся логика в Orchestrator.ask() / dashboard().
Запуск: streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Важно: когда запускаем `streamlit run ui/streamlit_app.py`,
# Streamlit добавляет директорию скрипта (ui/) в sys.path первой.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.orchestrator import Orchestrator  # noqa: E402
from app.schemas import AskResult, DashboardRequest, DashboardResult  # noqa: E402
from viz.charts import build_chart  # noqa: E402

# Константы для формы презентации (используются в UI и могут тестироваться)
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

SUGGESTION_PROMPTS: list[str] = [
    "Какая задолженность по регионам?",
    "Динамика начислений в г. Минск за год",
    "Структура налогов по видам (доли)",
    "Покажи дашборд по задолженности по регионам",
    "Топ-3 региона по подоходному налогу",
]


@st.cache_resource(show_spinner=False)
def get_orchestrator() -> Orchestrator:
    """Кэшируем Orchestrator, чтобы не пересоздавать агенты/модель на каждый rerun."""
    return Orchestrator()


@st.cache_data(show_spinner=False)
def _load_demo_df() -> pd.DataFrame:
    """Загружаем демо-датасет один раз (для сайдбара и подсказок)."""
    path = PROJECT_ROOT / "data" / "sample.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _inject_custom_css() -> None:
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: transparent;}
        .block-container {padding-top: 2rem; padding-bottom: 4rem; max-width: 52rem;}
        [data-testid="stChatMessage"] {border-radius: 12px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _is_dashboard_request(text: str) -> bool:
    lowered = text.lower()
    return any(kw in lowered for kw in ("дашборд", "dashboard", "обзор", "сводк", "ключевые метрики"))


def _friendly_status_steps(is_dashboard: bool) -> list[str]:
    if is_dashboard:
        return [
            "📊 Получаю данные из датасета...",
            "📈 Подбираю графики и KPI...",
            "📝 Формирую выводы...",
        ]
    return [
        "📊 Получаю данные...",
        "📈 Рисую график...",
        "📝 Готовлю аналитические выводы...",
    ]


def _render_technical_details(res: Any) -> None:
    """SQL, reasoning и прочее — только для любопытных."""
    with st.popover("⚙️ Детали"):
        if hasattr(res, "sql") and getattr(res, "sql", None):
            st.caption("SQL-запрос")
            st.code(res.sql, language="sql")
        if hasattr(res, "source_sql") and getattr(res, "source_sql", None):
            st.caption("SQL-запрос")
            st.code(res.source_sql, language="sql")
        if hasattr(res, "data") and isinstance(getattr(res, "data", None), list):
            st.caption(f"Строк данных: {len(res.data)}")
        if hasattr(res, "reasoning") and getattr(res, "reasoning", None):
            st.caption("Служебное пояснение")
            st.write(res.reasoning)
        if hasattr(res, "png_path") and getattr(res, "png_path", None):
            st.caption(f"Артефакт: `{res.png_path}`")
        if hasattr(res, "model_dump"):
            with st.expander("JSON", expanded=False):
                st.json(res.model_dump())


def render_assistant_response(res: Any) -> None:
    """Красивый рендер ответа ассистента для бизнес-пользователя."""
    if res is None:
        st.warning("Не удалось получить ответ.")
        return

    if hasattr(res, "success") and not getattr(res, "success", True):
        st.error(getattr(res, "error", None) or "Не удалось выполнить запрос.")
        _render_technical_details(res)
        return

    # Презентация
    if hasattr(res, "pptx_path"):
        st.success(f"Презентация готова — {getattr(res, 'num_slides', 0)} слайдов.")
        ppath = getattr(res, "pptx_path", None)
        if ppath and Path(ppath).exists():
            with open(ppath, "rb") as f:
                st.download_button(
                    "📥 Скачать презентацию (.pptx)",
                    data=f.read(),
                    file_name="presentation.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
        return

    # Дашборд
    if isinstance(res, DashboardResult) or (
        hasattr(res, "charts") and hasattr(res, "kpi_cards")
    ):
        _render_dashboard(res)
        _render_technical_details(res)
        return

    # AskResult / одиночный график
    if isinstance(res, AskResult) or (
        hasattr(res, "chart_spec") or hasattr(res, "analysis")
    ):
        title = None
        if getattr(res, "chart_spec", None) and getattr(res.chart_spec, "title", None):
            title = res.chart_spec.title
        elif getattr(res, "question", None):
            title = res.question
        if title:
            st.markdown(f"### {title}")

        chart_rendered = False
        if getattr(res, "data", None) and getattr(res, "chart_spec", None):
            try:
                df = pd.DataFrame(res.data)
                fig = build_chart(df, res.chart_spec)
                st.plotly_chart(fig, use_container_width=True)
                chart_rendered = True
            except Exception as exc:
                st.warning(f"Не удалось отобразить график: {exc}")

        if not chart_rendered and getattr(res, "png_path", None) and Path(res.png_path).exists():
            st.image(res.png_path, use_container_width=True)

        analysis = getattr(res, "analysis", None)
        if analysis:
            insights = getattr(analysis, "insights", None) or []
            if insights:
                st.markdown("**Ключевые выводы**")
                st.info("\n\n".join(f"• {ins}" for ins in insights))
            if getattr(analysis, "key_conclusion", None):
                st.markdown("**Итог**")
                st.success(analysis.key_conclusion)
            if getattr(analysis, "anomaly_or_trend", None):
                st.caption(f"📌 {analysis.anomaly_or_trend}")

        _render_technical_details(res)
        return

    # Текстовый fallback
    if hasattr(res, "insights") and res.insights:
        st.info("\n\n".join(f"• {ins}" for ins in res.insights))
    elif hasattr(res, "summary") and res.summary:
        st.write(res.summary)
    else:
        st.write("Готово. Уточните вопрос, если нужны дополнительные детали.")
    _render_technical_details(res)


def _render_dashboard(res: DashboardResult) -> None:
    """Рендер DashboardResult в чате: KPI + графики + выводы."""
    st.markdown(f"### {res.title}")
    if res.summary:
        st.write(res.summary)

    if res.kpi_cards:
        n = min(len(res.kpi_cards), 4)
        kcols = st.columns(n)
        for i, kpi in enumerate(res.kpi_cards[:n]):
            with kcols[i % n]:
                delta = f"{kpi.change:+.1f}%" if getattr(kpi, "change", None) is not None else None
                st.metric(
                    label=kpi.name,
                    value=kpi.value,
                    delta=delta,
                    help=getattr(kpi, "change_period", None) or "",
                )

    if res.charts and getattr(res, "data", None):
        df = pd.DataFrame(res.data)
        n_cols = max(1, min(getattr(res.layout, "columns", 2), 2))
        layout_type = getattr(res.layout, "type", "kpi_top_grid")

        if "tab" in layout_type:
            tab_names = [c.title[:36] for c in res.charts]
            ctabs = st.tabs(tab_names)
            for i, spec in enumerate(res.charts):
                with ctabs[i]:
                    try:
                        st.plotly_chart(build_chart(df, spec), use_container_width=True)
                    except Exception as exc:
                        st.warning(f"График недоступен: {exc}")
        else:
            chart_cols = st.columns(n_cols)
            for i, spec in enumerate(res.charts):
                with chart_cols[i % n_cols]:
                    try:
                        st.caption(spec.title)
                        st.plotly_chart(build_chart(df, spec), use_container_width=True)
                    except Exception as exc:
                        st.warning(f"График недоступен: {exc}")
    elif res.charts:
        st.info("Графики подготовлены, но данные для отображения отсутствуют.")

    if res.insights:
        st.markdown("**Выводы по дашборду**")
        st.info("\n\n".join(f"• {ins}" for ins in res.insights))


def _run_query(prompt: str) -> Any:
    """Выполняет запрос через Orchestrator (ask или dashboard)."""
    orch = get_orchestrator()
    if _is_dashboard_request(prompt):
        return orch.dashboard(prompt, max_charts=4, include_kpi=True)
    return orch.ask(prompt)


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 📊 BI-Аналитика")
        st.caption("Налоговая аналитика РБ · локально · синтетические данные 2024")

        with st.expander("📋 Источник данных", expanded=False):
            df = _load_demo_df()
            if df.empty:
                st.warning("Файл `data/sample.csv` не найден.")
            else:
                c1, c2 = st.columns(2)
                c1.metric("Записей", f"{len(df):,}".replace(",", " "))
                c2.metric("Регионов", df["region"].nunique())
                c3, c4 = st.columns(2)
                c3.metric("Налогов", df["tax_type"].nunique())
                c4.metric("Месяцев", df["period"].nunique())
                st.caption(f"Период: {df['period'].min()} — {df['period'].max()} · валюта Br")
                st.dataframe(df.head(5), use_container_width=True, hide_index=True)

            st.markdown("**Быстрые вопросы**")
            for idx, sug in enumerate(SUGGESTION_PROMPTS):
                if st.button(sug, key=f"sug_{idx}", use_container_width=True):
                    st.session_state["pending_prompt"] = sug

        if st.session_state.get("dashboard_history"):
            with st.expander("📈 История дашбордов", expanded=False):
                seen: set[str] = set()
                for item in reversed(st.session_state["dashboard_history"]):
                    q = item.get("question", "")
                    if not q or q in seen:
                        continue
                    seen.add(q)
                    if st.button(q[:60], key=f"dh_{hash(q)}", use_container_width=True):
                        st.session_state["pending_prompt"] = q

        st.divider()
        st.markdown("### 📑 Экспорт в презентацию")

        pres_mode = st.radio(
            "Формат",
            ["По вопросам", "Одной темой"],
            horizontal=True,
            key="pres_mode",
            label_visibility="collapsed",
        )

        if pres_mode == "По вопросам":
            default_q = "Структура налогов по видам (доли)\nТоп-3 региона по задолженности"
            questions_raw = st.text_area(
                "Вопросы (по одному на строку)",
                value=st.session_state.get("pres_questions_text", default_q),
                height=100,
                key="pres_questions_area",
            )
            st.session_state["pres_questions_text"] = questions_raw
        else:
            theme = st.text_input(
                "Тема презентации",
                value=st.session_state.get(
                    "pres_theme", "Налоговая аналитика Республики Беларусь за 2024 год"
                ),
                key="pres_theme_input",
            )
            st.session_state["pres_theme"] = theme

        num_slides = st.slider("Слайдов", 5, 12, 7, key="pres_slides")
        include_title = st.checkbox("Титульный слайд", value=True, key="pres_title")
        include_recs = st.checkbox("Рекомендации", value=True, key="pres_recs")

        if st.button("Создать презентацию", type="primary", use_container_width=True):
            qlist: list[dict[str, Any]] = []
            if pres_mode == "По вопросам":
                lines = [
                    ln.strip()
                    for ln in st.session_state.get("pres_questions_text", "").splitlines()
                    if ln.strip()
                ]
                if not lines:
                    st.warning("Добавьте хотя бы один вопрос.")
                else:
                    qlist = [{"text": ln, "chart_type": None, "note": ""} for ln in lines]
            else:
                free = st.session_state.get("pres_theme", "").strip()
                if not free:
                    st.warning("Укажите тему презентации.")
                else:
                    qlist = [{"text": free, "chart_type": None, "note": ""}]

            if qlist:
                with st.spinner("Собираю слайды..."):
                    try:
                        from app.agents.presentation_agent import PresentationAgent

                        pres_res = PresentationAgent().run(
                            qlist,
                            num_slides=num_slides,
                            include_title=include_title,
                            include_recommendations=include_recs,
                        )
                        st.session_state["last_presentation"] = pres_res
                        st.session_state["messages"].append(
                            {"role": "assistant", "result": pres_res}
                        )
                        st.success(f"Готово: {pres_res.num_slides} слайдов")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Ошибка: {exc}")

        if st.session_state.get("last_presentation"):
            pres = st.session_state["last_presentation"]
            ppath = getattr(pres, "pptx_path", None)
            if ppath and Path(ppath).exists():
                with open(ppath, "rb") as f:
                    st.download_button(
                        "📥 Скачать .pptx",
                        data=f.read(),
                        file_name="presentation.pptx",
                        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        use_container_width=True,
                    )

        st.divider()
        if st.button("Очистить чат", use_container_width=True):
            st.session_state["messages"] = []
            st.session_state["dashboard_history"] = []
            st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="BI-Аналитика",
        page_icon="📊",
        layout="centered",
        initial_sidebar_state="expanded",
    )

    _inject_custom_css()

    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "dashboard_history" not in st.session_state:
        st.session_state["dashboard_history"] = []

    _render_sidebar()

    # Приветствие при пустом чате
    if not st.session_state["messages"]:
        st.markdown("### Чем могу помочь?")
        st.markdown(
            "Спросите о налоговых данных Беларуси — получите график, выводы или дашборд. "
            "Например: *«Динамика начислений в г. Минск»* или *«Дашборд по задолженности»*."
        )

    # История чата
    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                st.write(msg.get("content", ""))
            elif msg.get("result") is not None:
                render_assistant_response(msg["result"])
            else:
                st.write(msg.get("content", ""))

    # Ввод: подсказка из сайдбара или chat_input
    prompt = st.session_state.pop("pending_prompt", None)
    chat_prompt = st.chat_input(
        "Спросите что-нибудь о налогах (например, «Динамика по Минску»)"
    )
    if chat_prompt:
        prompt = chat_prompt

    if prompt and prompt.strip():
        prompt = prompt.strip()
        st.session_state["messages"].append({"role": "user", "content": prompt})

        is_dashboard = _is_dashboard_request(prompt)
        with st.chat_message("assistant"):
            with st.status(
                "🧠 Агенты работают над вашим запросом...",
                expanded=True,
            ) as status:
                for step in _friendly_status_steps(is_dashboard):
                    st.write(step)
                try:
                    result = _run_query(prompt)
                    status.update(label="✅ Готово!", state="complete", expanded=False)
                    render_assistant_response(result)
                    st.session_state["messages"].append({"role": "assistant", "result": result})
                    if is_dashboard and isinstance(result, DashboardResult):
                        hist = st.session_state["dashboard_history"]
                        entry = {"question": prompt, "title": result.title}
                        if not hist or hist[-1] != entry:
                            hist.append(entry)
                            st.session_state["dashboard_history"] = hist[-12:]
                except Exception as exc:
                    status.update(label="Ошибка", state="error", expanded=False)
                    err_text = (
                        "Не удалось обработать запрос. Проверьте, что Ollama запущен "
                        "и модель `qwen2.5-coder:7b-instruct` доступна."
                    )
                    st.error(err_text)
                    st.session_state["messages"].append(
                        {"role": "assistant", "content": f"{err_text}\n\n{exc}"}
                    )

        st.rerun()


if __name__ == "__main__":
    main()