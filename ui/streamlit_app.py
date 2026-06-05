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


def main() -> None:
    st.set_page_config(
        page_title="BI-аналитика налогов РБ",
        page_icon="📊",
        layout="wide",
    )

    # Шапка
    st.title("BI-аналитика налогов РБ")
    st.caption(
        "Локальная мультиагентная платформа. Вопрос на русском → SQL по данным + инсайты + красивый график. "
        "Всё работает оффлайн через Ollama."
    )

    tab_charts, tab_pres = st.tabs(["📊 Графики", "📑 Презентация"])

    with tab_charts:
        st.caption(
            "Для предпочтительного типа графика (напр. горизонтальная столбчатая) и точного числа слайдов используйте вкладку «📑 Презентация»."
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

            # Инсайты
            if result.analysis and result.analysis.insights:
                st.subheader("Инсайты")
                for insight in result.analysis.insights:
                    st.markdown(f"- {insight}")

            # Аномалия / тренд
            if result.analysis and result.analysis.anomaly_or_trend:
                st.subheader("Замеченная аномалия / тренд")
                st.info(result.analysis.anomaly_or_trend)

            # SQL в сворачиваемом блоке
            with st.expander("Сгенерированный SQL (для проверки)", expanded=False):
                if result.sql:
                    st.code(result.sql, language="sql")
                else:
                    st.write("SQL не был сгенерирован.")

            # Дополнительно: краткая информация
            with st.expander("Техническая информация", expanded=False):
                st.write(f"**Вопрос:** {result.question}")
                st.write(f"**Строк в результате:** {len(result.data)}")
                if result.png_path:
                    st.write(f"**PNG:** `{result.png_path}`")

    # Закрываем вкладку графиков. Весь оригинальный код графиков выше — без изменений.

    with tab_pres:
        st.markdown("**Генерация презентации — структурированная форма (Phase 6/7)**")

        # Режим
        mode = st.radio(
            "Режим ввода",
            ["По вопросам", "Свободная тема", "Одним предложением"],
            horizontal=True,
            key="pres_mode",
        )

        overall_theme = st.text_input(
            "Общая тема презентации (опционально, для свободного режима)",
            value="Налоговая аналитика РБ 2024",
            key="pres_theme",
        )

        # Динамические блоки вопросов через session_state
        # chart_type храним как internal (None="авто") или str из ChartType; UI всегда показывает чисто русские лейблы
        if "pres_questions" not in st.session_state:
            st.session_state["pres_questions"] = [
                {"text": "Структура налогов по видам (доли)", "chart_type": None, "note": ""},
                {
                    "text": "Топ-3 региона по задолженности",
                    "chart_type": "horizontal_bar",
                    "note": "",
                },
            ]

        st.write("**Вопросы (добавляйте/редактируйте в блоках):**")
        to_remove = []
        for i, qblock in enumerate(st.session_state["pres_questions"]):
            with st.expander(f"Вопрос {i + 1}", expanded=True):
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
            st.session_state["pres_questions"].append({"text": "", "chart_type": None, "note": ""})
            st.rerun()

        # Динамическая метка ожидаемого числа слайдов (для UX, пока backend может не точно соблюдать)
        num_valid = len(
            [q for q in st.session_state["pres_questions"] if q.get("text", "").strip()]
        )
        expected = (
            5 + num_valid
        )  # титул + обзор + темы + N вопросов + ключевые выводы + рекомендации
        st.caption(
            f"Ожидаемое число слайдов: ~{expected} (титул+обзор+темы + {num_valid} вопросов + выводы + рекомендации). "
            "Слайдер ниже задаёт целевое; при несовпадении будет применяться срез/приложение (см. улучшения)."
        )

        # file_uploader (демо, не используется в генерации пока)
        st.file_uploader(
            "Доп. изображения / CSV (демо, не влияет на генерацию)",
            accept_multiple_files=True,
            type=["png", "jpg", "csv"],
            key="pres_files",
        )

        # Настройки
        with st.expander("Настройки презентации"):
            num_slides = st.slider("Число слайдов", 4, 12, 7, key="pres_num")
            include_title = st.checkbox("Включать титул", value=True, key="pres_title")
            include_recs = st.checkbox("Включать рекомендации", value=True, key="pres_recs")

        # Кнопка генерации — thin: собираем payload и постим в API (или fallback direct)
        if st.button("Сгенерировать презентацию", type="primary", use_container_width=True):
            qlist = [
                {
                    "text": q["text"],
                    "chart_type": q[
                        "chart_type"
                    ],  # None для авто, иначе internal str (line/bar/...)
                    "note": q["note"],
                }
                for q in st.session_state["pres_questions"]
                if q["text"].strip()
            ]
            if not qlist:
                st.warning("Добавьте хотя бы один вопрос.")
            else:
                payload = {
                    "mode": mode,
                    "overall_theme": overall_theme or None,
                    "questions": qlist,
                    "num_slides": num_slides,
                    "include_title": include_title,
                    "include_recommendations": include_recs,
                }
                # minimal wire for uploader (demo): save files to out/, mention in UI (будут использоваться в appendix позже)
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
                    st.caption(
                        f"Демо-файлы сохранены: {', '.join(uploaded_names)} (для будущих appendix-слайдов)"
                    )

                status_text = (
                    "Генерация через API / прямой вызов (долгие вызовы LLM ~30с+ на вопрос)..."
                )
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
                            # fallback direct (если uvicorn не запущен)
                            from app.agents.presentation_agent import PresentationAgent

                            pa = PresentationAgent()
                            # передаём полные блоки с prefs + настройки, чтобы exact count + prefs respected
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


if __name__ == "__main__":
    main()
