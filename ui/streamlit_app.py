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
from app.agents.presentation_agent import PresentationAgent  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from viz.charts import build_chart  # noqa: E402


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
        st.markdown(
            "**Генерация презентации (несколько вопросов → .pptx со слайдами, графиками и выводами)**"
        )

        questions_text = st.text_area(
            "Вопросы для презентации (по одному на строку)",
            value="""Структура налогов по видам (доли)
Какие регионы имеют наибольшую задолженность по НДС?
Динамика начислений подоходного налога в г. Минск по месяцам?""",
            height=120,
            key="pres_questions_text",
            help="Каждый вопрос будет обработан полностью (SQL + анализ + график). Общее время: ~30-60 сек на вопрос.",
        )

        if st.button("Сгенерировать презентацию", type="primary", use_container_width=True):
            questions = [line.strip() for line in questions_text.splitlines() if line.strip()]

            if not questions:
                st.warning("Введите хотя бы один вопрос (по одному на строку).")
            else:
                with st.status(
                    f"Генерация презентации из {len(questions)} вопросов (каждый ~30-60 сек)...",
                    expanded=True,
                ) as status:
                    try:
                        status.write("Обрабатываемые вопросы:")
                        for i, q in enumerate(questions, 1):
                            status.write(f"  {i}. {q}")

                        pa = PresentationAgent()
                        pres_res = pa.run(questions)

                        st.session_state["last_pres"] = {
                            "num_slides": pres_res.num_slides,
                            "pptx_path": pres_res.pptx_path,
                        }

                        status.update(
                            label=f"Презентация готова! Слайдов: {pres_res.num_slides}",
                            state="complete",
                        )
                    except Exception as e:
                        status.update(label="Ошибка при генерации презентации", state="error")
                        st.error(
                            "Не удалось сгенерировать презентацию. "
                            "Убедитесь, что Ollama запущен с моделью qwen2.5-coder:7b-instruct, "
                            "данные доступны и вопросы корректны. "
                            f"Детали: {str(e)[:300]}"
                        )

        # Показ предыдущего результата (чтобы не исчезал при rerun)
        if "last_pres" in st.session_state:
            pres = st.session_state["last_pres"]
            st.success(f"Презентация готова: {pres['num_slides']} слайдов.")

            pptx_path = pres.get("pptx_path")
            if pptx_path and Path(pptx_path).exists():
                with open(pptx_path, "rb") as f:
                    pptx_bytes = f.read()

                st.download_button(
                    label="📥 Скачать презентацию (.pptx)",
                    data=pptx_bytes,
                    file_name="presentation.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    use_container_width=True,
                )
            else:
                st.warning("Файл презентации не найден на диске.")


if __name__ == "__main__":
    main()
