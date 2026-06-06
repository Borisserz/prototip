"""Streamlit UI для BI-аналитики налогов РБ — премиальный чат-интерфейс.

Тонкий клиент: вся логика в Orchestrator.ask() / presentation().
Запуск: streamlit run ui/streamlit_app.py
"""

from __future__ import annotations

import hashlib
import html
import json
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

# Важно: когда запускаем `streamlit run ui/streamlit_app.py`,
# Streamlit добавляет директорию скрипта (ui/) в sys.path первой.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from app.chart_repair import repair_chart_spec  # noqa: E402
from app.config import config  # noqa: E402
from app.drilldown import (  # noqa: E402
    DRILLDOWN_DIMENSIONS,
    build_detailed_analysis_question,
    drilldown_context_fingerprint,
    drilldown_context_from_selection,
    session_drilldown_context,
)
from app.logging_utils import new_correlation_id, run_logger  # noqa: E402
from app.orchestrator import Orchestrator  # noqa: E402
from app.pipeline_progress import pipeline_store  # noqa: E402
from app.schemas import AskResult, ChartSpec, DashboardResult, DrilldownContext  # noqa: E402
from core.llm import is_ollama_available  # noqa: E402
from ui.components.pipeline import pipeline_status_headline, update_pipeline_live_ui  # noqa: E402
from ui.components.trace import render_planner_trace  # noqa: E402
from viz.charts import build_chart  # noqa: E402
from viz.style import format_number_ru, get_russian_label  # noqa: E402

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

DASHBOARD_CHART_TYPES: list[str] = [
    "bar",
    "grouped_bar",
    "stacked_bar",
    "line",
    "area",
    "scatter",
    "waterfall",
    "horizontal_bar",
    "donut",
    "kpi",
    "heatmap",
    "treemap",
]
DASHBOARD_CHART_TYPE_LABELS: dict[str, str] = {
    "bar": "Столбчатая",
    "grouped_bar": "Группированная",
    "stacked_bar": "Стековая",
    "line": "Линейная",
    "area": "С заливкой (area)",
    "scatter": "Точечная",
    "waterfall": "Водопад",
    "horizontal_bar": "Горизонтальная (рейтинг)",
    "donut": "Круговая (donut)",
    "kpi": "KPI",
    "heatmap": "Тепловая карта",
    "treemap": "Treemap",
}

SUGGESTION_PROMPTS: list[str] = [
    "Какая задолженность по регионам?",
    "Динамика начислений в г. Минск за год",
    "Структура налогов по видам (доли)",
    "Покажи дашборд по задолженности по регионам",
    "Топ-3 региона по подоходному налогу",
]

# Карточки empty state по категориям: (заголовок, описание, запрос)
PROMPT_CARD_CATEGORIES: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "Рейтинги",
        [
            ("Топ регионов по долгу", "Рейтинг задолженности по областям", "Какая задолженность по регионам?"),
            ("Топ-3 по подоходному", "Лидеры по подоходному налогу", "Топ-3 региона по подоходному налогу"),
        ],
    ),
    (
        "Динамика",
        [
            ("Динамика в Минске", "Начисления по месяцам за 2024 год", "Динамика начислений в г. Минск за год"),
        ],
    ),
    (
        "Структура",
        [
            ("Структура налогов", "Доли видов налогов в разрезе", "Структура налогов по видам (доли)"),
        ],
    ),
    (
        "Комплексный обзор",
        [
            ("Дашборд по долгу", "KPI и графики в одном обзоре", "Покажи дашборд по задолженности по регионам"),
            ("Сводка по Минску", "Ключевые метрики г. Минска", "Ключевые метрики и дашборд по начислениям в г. Минск"),
        ],
    ),
]
PROMPT_CARDS: list[tuple[str, str, str]] = [
    card for _category, cards in PROMPT_CARD_CATEGORIES for card in cards
]

# Обратная совместимость для тестов/импортов
PROMPT_CHIPS: list[tuple[str, str]] = [(t, q) for t, _, q in PROMPT_CARDS[:3]]

GOV_DISCLAIMER = (
    "Синтетические данные (демо), Республика Беларусь · AI draft · не для официальной отчётности"
)
ESTIMATED_RESPONSE_SEC = "30–90"


def _init_ux_session_state() -> None:
    defaults: dict[str, Any] = {
        "ui_mode": "leadership",
        "global_filters": {"region": None, "tax_type": None, "period": None},
        "pres_queue": [],
        "workspace_dashboard_result": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _is_leadership_mode() -> bool:
    return st.session_state.get("ui_mode", "leadership") == "leadership"


def _is_analyst_mode() -> bool:
    return not _is_leadership_mode()


def _render_gov_disclaimer() -> None:
    st.markdown(
        f'<div class="gov-disclaimer-bar">{html.escape(GOV_DISCLAIMER)}</div>',
        unsafe_allow_html=True,
    )


def _render_app_header() -> None:
    left, mid, right = st.columns([2.2, 2.6, 1.2])
    with left:
        st.markdown(
            '<div class="gov-app-title">BI-аналитика налогов РБ</div>',
            unsafe_allow_html=True,
        )
    with mid:
        mode = st.radio(
            "Режим интерфейса",
            ["Для руководства", "Для аналитика"],
            horizontal=True,
            index=0 if _is_leadership_mode() else 1,
            key="ui_mode_radio",
            label_visibility="collapsed",
            help=(
                "Руководство — краткий отчёт: график, KPI и выводы. "
                "Аналитик — полный доступ: SQL, данные, трассировка агентов и редактор графиков."
            ),
        )
        st.session_state["ui_mode"] = "leadership" if mode == "Для руководства" else "analyst"
        if _is_leadership_mode():
            st.caption("Краткий вид: результат и выводы без технических деталей.")
        else:
            st.caption("Полный вид: SQL, таблица данных, трассировка и настройка графиков.")
    with right:
        ok = is_ollama_available(config.ollama_model)
        if ok:
            st.markdown(
                f'<div class="ollama-status ok">Ollama: {html.escape(config.ollama_model)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="ollama-status err">Ollama: недоступна</div>',
                unsafe_allow_html=True,
            )


def _effective_drilldown() -> DrilldownContext | None:
    gf = st.session_state.get("global_filters") or {}
    filters: dict[str, str] = {}
    for key in ("region", "tax_type", "period"):
        val = gf.get(key)
        if val:
            filters[key] = str(val)
    session_ctx = _session_drilldown_context()
    if session_ctx and session_ctx.filters:
        filters = {**filters, **session_ctx.filters}
    if not filters:
        return session_ctx
    trail = session_ctx.trail if session_ctx else []
    return DrilldownContext(filters=filters, trail=trail or [])


def _selectbox_index(options: list[Any], current: Any) -> int:
    if current is None or current not in options:
        return 0
    return options.index(current)


def _render_global_filters() -> None:
    df = _load_demo_df()
    if df.empty:
        return
    st.markdown("**Глобальные фильтры**")
    gf = dict(st.session_state.get("global_filters") or {})
    regions = sorted(df["region"].dropna().unique().tolist()) if "region" in df.columns else []
    taxes = sorted(df["tax_type"].dropna().unique().tolist()) if "tax_type" in df.columns else []
    periods = sorted(df["period"].dropna().unique().tolist()) if "period" in df.columns else []
    region_opts = [None] + regions
    tax_opts = [None] + taxes
    period_opts = [None] + periods
    gf["region"] = st.selectbox(
        "Регион",
        region_opts,
        index=_selectbox_index(region_opts, gf.get("region")),
        format_func=lambda x: "Все регионы" if x is None else x,
        key="gf_region",
    )
    gf["tax_type"] = st.selectbox(
        "Вид налога",
        tax_opts,
        index=_selectbox_index(tax_opts, gf.get("tax_type")),
        format_func=lambda x: "Все виды" if x is None else x,
        key="gf_tax",
    )
    gf["period"] = st.selectbox(
        "Период",
        period_opts,
        index=_selectbox_index(period_opts, gf.get("period")),
        format_func=lambda x: "Весь период" if x is None else x,
        key="gf_period",
    )
    st.session_state["global_filters"] = gf


def _recent_user_questions(limit: int = 5) -> list[str]:
    out: list[str] = []
    for msg in reversed(st.session_state.get("main_messages", [])):
        if msg.get("role") == "user":
            text = str(msg.get("content", "")).strip()
            if text and text not in out:
                out.append(text)
        if len(out) >= limit:
            break
    return out


def _session_export_payload() -> dict[str, Any]:
    return {
        "ui_mode": st.session_state.get("ui_mode"),
        "messages": st.session_state.get("main_messages", []),
        "pinned_items": st.session_state.get("pinned_items", []),
        "pres_queue": st.session_state.get("pres_queue", []),
        "global_filters": st.session_state.get("global_filters", {}),
    }


def _add_to_pres_queue(question: str, chart_type: str | None = None) -> None:
    q = question.strip()
    if not q:
        return
    queue: list[dict[str, Any]] = st.session_state.setdefault("pres_queue", [])
    if any(item.get("text") == q for item in queue):
        return
    queue.append({"text": q, "chart_type": chart_type})
    st.session_state["pres_queue"] = queue


def _chart_subtitle(chart_spec: ChartSpec | None, question: str) -> str | None:
    if not chart_spec:
        return question or None
    if chart_spec.action_title and chart_spec.title and chart_spec.title != chart_spec.action_title:
        return chart_spec.title
    if chart_spec.action_title and question and question != chart_spec.action_title:
        return f"Вопрос: {question}"
    return None


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
        /* ── Standalone product chrome (оставляем шапку для кнопки «раскрыть панель») ── */
        #MainMenu, footer {visibility: hidden; height: 0;}
        header[data-testid="stHeader"] {
            visibility: visible !important;
            height: 3.25rem !important;
            background: transparent !important;
            border: none !important;
        }
        .stDeployButton {display: none !important;}
        [data-testid="stExpandSidebarButton"] {
            visibility: visible !important;
        }
        .stApp {
            background: linear-gradient(180deg, #F5F7FA 0%, #EEF2F6 100%);
            font-family: Arial, "Helvetica Neue", Helvetica, sans-serif;
        }
        .block-container {
            padding-top: 0.75rem;
            padding-bottom: 5rem;
            max-width: 72rem;
        }
        .gov-disclaimer-bar {
            background: #E8EDF2;
            border: 1px solid #C5D0DC;
            border-left: 4px solid #003366;
            color: #334155;
            font-size: 0.82rem;
            font-weight: 600;
            padding: 0.55rem 0.85rem;
            border-radius: 6px;
            margin-bottom: 0.65rem;
        }
        .gov-app-title {
            font-size: 1.35rem;
            font-weight: 700;
            color: #003366;
            letter-spacing: -0.01em;
            padding-top: 0.35rem;
        }
        .ollama-status {
            font-size: 0.78rem;
            font-weight: 600;
            text-align: right;
            padding-top: 0.55rem;
        }
        .ollama-status.ok { color: #1B5E20; }
        .ollama-status.err { color: #B71C1C; }
        .card-subtitle {
            color: #64748B;
            font-size: 0.9rem;
            margin: -0.35rem 0 0.75rem;
            line-height: 1.4;
        }
        .category-label {
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: #006699;
            margin: 0.85rem 0 0.45rem;
        }

        /* ── Typography ── */
        h1, h2, h3, h4, .analytics-title {
            color: #0F172A !important;
            font-weight: 700 !important;
            letter-spacing: -0.02em;
        }
        p, .stMarkdown, [data-testid="stChatMessage"] { color: #334155; }

        /* ── Chat cards ── */
        [data-testid="stChatMessage"] {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            box-shadow: 0 4px 18px rgba(15, 23, 42, 0.06);
            padding: 0.35rem 0.5rem 0.75rem;
            margin-bottom: 0.85rem;
        }
        [data-testid="stChatMessage"] [data-testid="stVerticalBlock"] {
            gap: 0.45rem;
        }

        /* ── Analytics result card ── */
        .analytics-card-wrap {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            box-shadow: 0 6px 24px rgba(15, 23, 42, 0.07);
            padding: 1.25rem 1.35rem 1.1rem;
            margin: 0.25rem 0 0.5rem;
        }
        .analytics-card-header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
            margin-bottom: 0.85rem;
            flex-wrap: wrap;
        }
        .analytics-title {
            font-size: 1.35rem;
            line-height: 1.3;
            margin: 0;
            color: #0F172A;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            background: #E8F4EC;
            color: #1B5E20;
            border: 1px solid #A5D6A7;
            border-radius: 999px;
            padding: 0.3rem 0.75rem;
            font-size: 0.78rem;
            font-weight: 600;
            white-space: nowrap;
        }
        .status-badge.warn {
            background: #FFFBEB;
            color: #B45309;
            border-color: #FDE68A;
        }
        .chart-panel {
            background: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            padding: 0.65rem 0.5rem 0.25rem;
            margin-bottom: 0.75rem;
        }

        /* ── Chart error callout ── */
        .chart-error-block {
            display: flex;
            gap: 0.85rem;
            align-items: flex-start;
            background: #FEF2F2;
            border: 1px solid #FECACA;
            border-radius: 12px;
            padding: 1rem 1.1rem;
            margin: 0.5rem 0 0.75rem;
        }
        .chart-error-icon { font-size: 1.5rem; line-height: 1; }
        .chart-error-title {
            font-weight: 700;
            color: #991B1B;
            font-size: 0.95rem;
            margin-bottom: 0.25rem;
        }
        .chart-error-desc { color: #7F1D1D; font-size: 0.88rem; line-height: 1.45; }

        /* ── Analysis blocks ── */
        .key-conclusion-block {
            background: linear-gradient(135deg, #EEF4F8 0%, #E2EBF2 100%);
            border-left: 4px solid #003366;
            border-radius: 10px;
            padding: 1rem 1.1rem;
            margin-bottom: 0.75rem;
        }
        .key-conclusion-label {
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            color: #003366;
            margin-bottom: 0.35rem;
        }
        .key-conclusion-text {
            font-size: 1.05rem;
            font-weight: 600;
            color: #0F172A;
            line-height: 1.45;
            margin: 0;
        }
        .insight-item {
            display: flex;
            gap: 0.55rem;
            align-items: flex-start;
            padding: 0.55rem 0;
            border-bottom: 1px solid #F1F5F9;
        }
        .insight-item:last-child { border-bottom: none; }
        .insight-icon { font-size: 1rem; line-height: 1.4; flex-shrink: 0; }
        .insight-text { font-size: 0.92rem; color: #334155; line-height: 1.45; }
        .anomaly-block {
            background: #FFFBEB;
            border: 1px solid #FDE68A;
            border-radius: 10px;
            padding: 0.85rem 1rem;
            margin-top: 0.5rem;
        }
        .anomaly-label {
            font-size: 0.72rem;
            font-weight: 700;
            color: #B45309;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 0.3rem;
        }
        .anomaly-text { color: #92400E; font-size: 0.9rem; line-height: 1.4; }

        /* ── Empty state cards ── */
        .empty-hero {
            text-align: center;
            padding: 1.5rem 0 0.5rem;
        }
        .empty-hero h2 {
            font-size: 1.75rem !important;
            margin-bottom: 0.35rem !important;
        }
        .empty-hero p { color: #64748B; font-size: 1rem; }
        .empty-grid [data-testid="column"] .stButton > button {
            width: 100%;
            min-height: 7.5rem;
            padding: 1rem 1.1rem;
            border-radius: 14px;
            border: 1px solid #E2E8F0;
            background: #FFFFFF;
            color: #0F172A;
            font-weight: 600;
            line-height: 1.35;
            white-space: normal;
            text-align: left;
            box-shadow: 0 4px 16px rgba(15, 23, 42, 0.06);
            transition: border-color 0.2s, box-shadow 0.2s, transform 0.15s;
        }
        .empty-grid [data-testid="column"] .stButton > button:hover {
            border-color: #006699;
            background: #F8FAFC;
            box-shadow: 0 8px 28px rgba(0, 51, 102, 0.12);
            transform: translateY(-2px);
        }
        .empty-grid [data-testid="column"] .stButton > button p {
            margin: 0;
        }

        /* ── Secondary action buttons ── */
        .export-row [data-testid="stDownloadButton"] button,
        .export-row .stButton > button {
            background: #FFFFFF !important;
            border: 1px solid #CBD5E1 !important;
            color: #334155 !important;
            font-weight: 600 !important;
            border-radius: 10px !important;
            box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04) !important;
        }
        .export-row [data-testid="stDownloadButton"] button:hover,
        .export-row .stButton > button:hover {
            border-color: #94A3B8 !important;
            background: #F8FAFC !important;
        }

        /* ── Sidebar polish ── */
        [data-testid="stSidebar"] {
            background: #FFFFFF;
            border-right: 1px solid #E2E8F0;
            min-width: 17rem;
        }
        [data-testid="stSidebar"] [data-testid="stSelectbox"] label {
            white-space: normal;
            line-height: 1.25;
        }
        [data-testid="stSidebar"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
            white-space: normal;
        }
        /* Свёрнутый сайдбар не резервирует полосу слева */
        section[data-testid="stMain"] {
            flex: 1 1 auto !important;
            width: auto !important;
            min-width: 0 !important;
            margin-left: 0 !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"] {
            width: 0 !important;
            min-width: 0 !important;
            max-width: 0 !important;
            padding: 0 !important;
            border: none !important;
            overflow: hidden !important;
            visibility: hidden !important;
        }
        section[data-testid="stSidebar"][aria-expanded="false"] + section[data-testid="stMain"] {
            margin-left: 0 !important;
            padding-left: 0 !important;
        }

        /* ── Pinned dashboard mini-cards ── */
        .pinned-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 12px;
            box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
            padding: 0.85rem 0.95rem 0.75rem;
            margin-bottom: 0.75rem;
            min-height: 100%;
        }
        .pinned-card-title {
            font-size: 0.95rem;
            font-weight: 700;
            color: #0F172A;
            margin-bottom: 0.45rem;
            line-height: 1.3;
        }
        .pin-row .stButton > button[kind="secondary"] {
            border-color: #FCD34D !important;
            color: #92400E !important;
            background: #FFFBEB !important;
        }

        /* ── Drill-down breadcrumbs & CTA ── */
        .drill-breadcrumbs {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.35rem;
            margin: 0.35rem 0 0.65rem;
            font-size: 0.82rem;
        }
        .drill-crumb {
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
            background: #EFF6FF;
            border: 1px solid #BFDBFE;
            color: #1E40AF;
            border-radius: 999px;
            padding: 0.22rem 0.65rem;
            font-weight: 600;
        }
        .drill-crumb.active {
            background: #DBEAFE;
            border-color: #60A5FA;
            color: #003366;
        }
        .drill-sep { color: #94A3B8; font-weight: 700; }
        .drill-hint {
            color: #64748B;
            font-size: 0.8rem;
            margin-bottom: 0.45rem;
        }
        /* ── Presentation carousel preview ── */
        .pres-carousel-wrap {
            background: linear-gradient(180deg, #F8FAFC 0%, #F1F5F9 100%);
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            padding: 0.9rem 0.85rem 0.75rem;
            margin: 0.75rem 0 0.85rem;
        }
        .pres-preview-label {
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.07em;
            color: #64748B;
            margin-bottom: 0.45rem;
        }
        .pres-slide-counter {
            text-align: center;
            font-size: 0.92rem;
            font-weight: 700;
            color: #334155;
            letter-spacing: 0.01em;
            margin: 0.15rem 0 0.55rem;
            padding: 0.35rem 0.65rem;
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 999px;
            display: inline-block;
            width: auto;
            min-width: 9rem;
        }
        .pres-counter-row {
            text-align: center;
            margin-bottom: 0.35rem;
        }
        .pres-carousel-wrap [data-testid="stImage"] {
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 6px 22px rgba(15, 23, 42, 0.1);
            border: 1px solid #E2E8F0;
        }
        .pres-nav-hint {
            text-align: center;
            font-size: 0.78rem;
            color: #94A3B8;
            margin-top: 0.35rem;
        }
        .pres-download-cta {
            margin-top: 0.15rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _normalize_result(res: Any) -> Any:
    """Восстанавливает Pydantic-модель, если результат в session_state оказался dict."""
    if isinstance(res, dict):
        if res.get("charts") is not None or res.get("kpi_cards") is not None:
            return DashboardResult.model_validate(res)
        if res.get("pptx_path"):
            from app.schemas import PresentationResult

            return PresentationResult.model_validate(res)
        if res.get("chart_spec") is not None or res.get("data") is not None:
            return AskResult.model_validate(res)
    return res


def _coerce_chart_spec(spec: Any) -> ChartSpec | None:
    if spec is None:
        return None
    if isinstance(spec, ChartSpec):
        return spec
    if isinstance(spec, dict):
        return ChartSpec.model_validate(spec)
    return None


def _no_viz_user_message(res: AskResult) -> str | None:
    """Текст для пользователя, если визуализация невозможна; иначе None."""
    data = getattr(res, "data", None) or []
    chart_spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
    if _resolve_artifact_path(getattr(res, "png_path", None)) is not None:
        return None
    if not data:
        return (
            "По выбранным фильтрам данных не найдено. "
            "Измените регион, период или вид налога и повторите запрос."
        )
    if chart_spec is None:
        return (
            "Данные получены, но график построить не удалось. "
            "Попробуйте уточнить формулировку вопроса."
        )
    return None


def _chart_buildable(data: list[dict], spec: ChartSpec) -> bool:
    """Проверяет, что график можно построить до показа карточки результата."""
    if not data or spec is None:
        return False
    try:
        df = pd.DataFrame(data)
        repaired = repair_chart_spec(spec, data)
        build_chart(df, repaired)
        return True
    except Exception:
        return False


def _render_no_viz_only(res: AskResult, message: str) -> None:
    """Короткий ответ без анализа и кнопок экспорта."""
    question = getattr(res, "question", "Результат запроса") or "Результат запроса"
    st.markdown(
        f"""
        <div class="analytics-card-wrap">
            <div class="analytics-card-header">
                <h3 class="analytics-title">{html.escape(question)}</h3>
                <span class="status-badge warn">Нет данных</span>
            </div>
            <div class="chart-error-block">
                <div class="chart-error-icon">!</div>
                <div>
                    <div class="chart-error-title">Нет данных для отображения</div>
                    <div class="chart-error-desc">{html.escape(message)}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_CHART_BUILD_FAIL_MSG = (
    "Не удалось построить график по полученным данным. "
    "Попробуйте другой вопрос или смените фильтры в левой панели."
)


def _chart_display_title(chart_spec: ChartSpec | None, fallback: str) -> str:
    if chart_spec is None:
        return fallback
    if getattr(chart_spec, "action_title", None):
        return str(chart_spec.action_title)
    if chart_spec.title:
        return chart_spec.title
    return fallback


def _drilldown_supported(chart_spec: ChartSpec | None) -> bool:
    if chart_spec is None:
        return False
    return chart_spec.chart_type not in ("kpi", "heatmap")


def _filter_data_by_regions(data: list[dict], regions: list[str] | None) -> list[dict]:
    if not regions or not data or "region" not in data[0]:
        return data
    allowed = set(regions)
    return [row for row in data if str(row.get("region", "")) in allowed]


def _dashboard_editor_key(chart_key_prefix: str, chart_idx: int) -> str:
    return f"dash_editor_{chart_key_prefix}_{chart_idx}"


def _read_dashboard_chart_override(
    base_spec: ChartSpec,
    *,
    chart_key_prefix: str,
    chart_idx: int,
    available_regions: list[str],
) -> ChartSpec:
    """Читает post-gen правки из session_state и возвращает обновлённый ChartSpec."""
    ek = _dashboard_editor_key(chart_key_prefix, chart_idx)
    state = st.session_state.get(ek)
    if not isinstance(state, dict):
        return base_spec

    updates: dict[str, Any] = {}
    ctype = state.get("chart_type")
    if ctype and ctype in DASHBOARD_CHART_TYPES:
        updates["chart_type"] = ctype
    if state.get("action_title") is not None:
        updates["action_title"] = state.get("action_title") or None
    updates["show_average"] = bool(state.get("show_average", base_spec.show_average))
    hc = state.get("highlight_category")
    if hc is not None:
        updates["highlight_category"] = hc or None

    spec = base_spec.model_copy(update=updates) if updates else base_spec
    if spec.highlight_category and spec.color:
        spec = spec.model_copy(update={"highlight_category": None})
    return spec


def _prepare_ask_chart_render(
    res: AskResult,
    chart_spec: ChartSpec,
    data: list[dict],
    *,
    chart_key: str,
) -> tuple[ChartSpec, list[dict]]:
    """Post-gen редактор + фильтр регионов для карточки чата."""
    available_regions = sorted({str(r.get("region")) for r in data if r.get("region")})
    if _is_analyst_mode():
        _render_dashboard_chart_editor(
            chart_spec,
            chart_key_prefix=chart_key,
            chart_idx=0,
            available_regions=available_regions,
        )
    spec = _read_dashboard_chart_override(
        chart_spec,
        chart_key_prefix=chart_key,
        chart_idx=0,
        available_regions=available_regions,
    )
    ek = _dashboard_editor_key(chart_key, 0)
    regions = (st.session_state.get(ek) or {}).get("regions") or []
    filtered = _filter_data_by_regions(data, regions)
    question = getattr(res, "question", "") or ""
    spec = repair_chart_spec(spec, filtered, question=question)
    return spec, filtered


def _render_dashboard_chart_editor(
    spec: ChartSpec,
    *,
    chart_key_prefix: str,
    chart_idx: int,
    available_regions: list[str],
) -> None:
    """Post-gen редактор: тип графика, фильтр региона, storytelling."""
    ek = _dashboard_editor_key(chart_key_prefix, chart_idx)
    if ek not in st.session_state:
        st.session_state[ek] = {
            "chart_type": spec.chart_type,
            "regions": [],
            "action_title": spec.action_title or "",
            "show_average": spec.show_average,
            "highlight_category": spec.highlight_category or "",
        }

    with st.expander("Настроить график", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            type_labels = [DASHBOARD_CHART_TYPE_LABELS.get(t, t) for t in DASHBOARD_CHART_TYPES]
            cur_idx = (
                DASHBOARD_CHART_TYPES.index(st.session_state[ek]["chart_type"])
                if st.session_state[ek]["chart_type"] in DASHBOARD_CHART_TYPES
                else 0
            )
            picked = st.selectbox(
                "Тип графика",
                type_labels,
                index=cur_idx,
                key=f"{ek}_type",
            )
            st.session_state[ek]["chart_type"] = DASHBOARD_CHART_TYPES[type_labels.index(picked)]
        with c2:
            if available_regions:
                st.session_state[ek]["regions"] = st.multiselect(
                    "Фильтр по региону",
                    available_regions,
                    default=st.session_state[ek].get("regions") or [],
                    key=f"{ek}_regions",
                )

        st.session_state[ek]["action_title"] = st.text_input(
            "Говорящий заголовок (action_title)",
            value=st.session_state[ek].get("action_title", ""),
            key=f"{ek}_action",
        )
        st.session_state[ek]["show_average"] = st.checkbox(
            "Показать линию среднего",
            value=bool(st.session_state[ek].get("show_average")),
            key=f"{ek}_avg",
        )
        st.session_state[ek]["highlight_category"] = st.text_input(
            "Выделить категорию",
            value=st.session_state[ek].get("highlight_category", ""),
            key=f"{ek}_highlight",
            help="Только для односерийных bar/horizontal_bar без color",
        )


def _resolve_artifact_path(path: str | None) -> Path | None:
    """Ищет PNG/артефакт относительно cwd и корня проекта."""
    if not path or str(path).startswith("ERROR"):
        return None
    candidate = Path(path)
    if candidate.is_absolute() and candidate.exists():
        return candidate
    for base in (Path.cwd(), PROJECT_ROOT):
        resolved = (base / candidate).resolve()
        if resolved.exists():
            return resolved
    return candidate if candidate.exists() else None


def _collect_presentation_preview_paths(res: Any) -> list[Path]:
    """Собирает PNG-превью слайдов из результата или out/pres_slide_*.png."""
    raw_paths: list[str] = []
    if isinstance(res, dict):
        raw_paths = list(res.get("slide_png_paths") or [])
    elif hasattr(res, "slide_png_paths"):
        raw_paths = list(getattr(res, "slide_png_paths") or [])

    resolved: list[Path] = []
    seen: set[str] = set()
    for item in raw_paths:
        path = _resolve_artifact_path(item)
        if path and path.exists():
            key = str(path.resolve())
            if key not in seen:
                seen.add(key)
                resolved.append(path)
    return resolved


def _presentation_carousel_state_key(paths: list[Path], key_prefix: str) -> str:
    digest = hashlib.sha256("|".join(str(p) for p in paths).encode()).hexdigest()[:10]
    return f"pres_carousel_{key_prefix}_{digest}"


def _render_presentation_carousel(paths: list[Path], *, key_prefix: str) -> None:
    """Карусель предпросмотра PNG-слайдов с навигацией Назад / Вперед."""
    if not paths:
        st.caption("Превью графиков недоступно — слайды без диаграмм или PNG не сгенерированы.")
        return

    state_key = _presentation_carousel_state_key(paths, key_prefix)
    if state_key not in st.session_state:
        st.session_state[state_key] = 0

    total = len(paths)
    idx = int(st.session_state[state_key])
    idx = max(0, min(idx, total - 1))
    st.session_state[state_key] = idx

    st.markdown('<div class="pres-carousel-wrap">', unsafe_allow_html=True)
    st.markdown('<div class="pres-preview-label">Предпросмотр слайдов</div>', unsafe_allow_html=True)
    st.markdown(
        f'<div class="pres-counter-row"><span class="pres-slide-counter">Слайд {idx + 1} из {total}</span></div>',
        unsafe_allow_html=True,
    )

    nav_l, nav_img, nav_r = st.columns([1, 5, 1])
    with nav_l:
        if st.button(
            "← Назад",
            key=f"{key_prefix}_pres_prev",
            disabled=idx <= 0,
            use_container_width=True,
        ):
            st.session_state[state_key] = max(0, idx - 1)
            st.rerun()
    with nav_img:
        st.image(str(paths[idx]), use_container_width=True)
    with nav_r:
        if st.button(
            "Вперед →",
            key=f"{key_prefix}_pres_next",
            disabled=idx >= total - 1,
            use_container_width=True,
        ):
            st.session_state[state_key] = min(total - 1, idx + 1)
            st.rerun()

    st.markdown(
        '<div class="pres-nav-hint">Листайте превью, чтобы оценить качество графиков перед скачиванием</div>',
        unsafe_allow_html=True,
    )
    st.markdown("</div>", unsafe_allow_html=True)


def _render_presentation_download_button(
    pptx_path: str | None,
    *,
    key: str,
    label: str = "Скачать презентацию (.pptx)",
) -> None:
    """Финальный CTA — скачивание .pptx под каруселью."""
    resolved = _resolve_artifact_path(pptx_path)
    if not resolved or not resolved.exists():
        st.warning("Файл презентации не найден. Попробуйте сгенерировать заново.")
        return
    with open(resolved, "rb") as f:
        st.markdown('<div class="pres-download-cta">', unsafe_allow_html=True)
        st.download_button(
            label,
            data=f.read(),
            file_name="presentation.pptx",
            mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
            use_container_width=True,
            key=key,
            type="primary",
        )
        st.markdown("</div>", unsafe_allow_html=True)


def _render_presentation_block(res: Any, *, key_prefix: str = "pres") -> None:
    """Карточка презентации: статус, карусель PNG, скачивание .pptx."""
    res = _normalize_result(res)
    num_slides = getattr(res, "num_slides", 0) or 0
    preview_paths = _collect_presentation_preview_paths(res)
    ppath = getattr(res, "pptx_path", None)

    st.markdown('<div class="analytics-card-wrap">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="analytics-card-header">
            <h3 class="analytics-title">Презентация готова</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Всего слайдов в колоде: **{num_slides}** · превью графиков: **{len(preview_paths)}**")

    _render_presentation_carousel(preview_paths, key_prefix=key_prefix)
    _render_presentation_download_button(ppath, key=f"dl_pptx_{key_prefix}")

    st.markdown("</div>", unsafe_allow_html=True)


def _plotly_without_title(fig: Any) -> Any:
    """Убирает заголовок с фигуры — заголовок выводится отдельно в чате."""
    try:
        fig.update_layout(title="")
    except Exception:
        try:
            fig.layout.title.text = ""
        except Exception:
            pass
    return fig


def _fig_for_streamlit(fig: Any) -> Any:
    """Адаптирует фигуру под узкий чат Streamlit (без фиксированной ширины 1000px)."""
    fig = _plotly_without_title(fig)
    try:
        fig.update_layout(
            width=None,
            height=440,
            autosize=True,
            margin=dict(l=48, r=24, t=24, b=56),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#FFFFFF",
        )
    except Exception:
        pass
    return fig


def _render_chart_error(message: str) -> None:
    """Кастомный блок ошибки визуализации (без жёлтого st.warning)."""
    safe = html.escape(str(message))
    st.markdown(
        f"""
        <div class="chart-error-block">
            <div class="chart-error-icon">!</div>
            <div>
                <div class="chart-error-title">Недостаточно данных для графика</div>
                <div class="chart-error-desc">{safe}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _handle_plotly_selection(
    event: Any,
    chart_spec: ChartSpec,
    *,
    chart_key: str,
) -> None:
    """Сохраняет выбор на графике в session_state (без автозапроса к Orchestrator)."""
    ctx = drilldown_context_from_selection(event, chart_spec, chart_key=chart_key)
    prev = st.session_state.get("drilldown_context")
    prev_fp = drilldown_context_fingerprint(prev)
    new_fp = drilldown_context_fingerprint(ctx)

    if ctx is None:
        if isinstance(prev, dict) and prev.get("source_chart_key") == chart_key:
            st.session_state["drilldown_context"] = None
        return

    if new_fp != prev_fp:
        st.session_state["drilldown_context"] = ctx


def _render_drilldown_chrome(
    chart_key: str | None,
    chart_spec: ChartSpec | None,
    *,
    enable_drilldown: bool,
) -> None:
    """Контекст детализации и CTA для drill-down над графиком."""
    if not enable_drilldown or not chart_key or chart_spec is None:
        return

    trail: list[dict[str, Any]] = st.session_state.get("drilldown_trail", [])
    ctx: dict[str, Any] | None = st.session_state.get("drilldown_context")
    is_active_chart = isinstance(ctx, dict) and ctx.get("source_chart_key") == chart_key

    if trail:
        trail_parts = []
        for step in trail:
            dim = step.get("dimension", "")
            dim_label = DRILLDOWN_DIMENSIONS.get(dim, "Сегмент")
            val = str(step.get("label", step.get("value", "")))
            trail_parts.append(f"{dim_label}: {val}")
        st.caption("Контекст: " + " → ".join(trail_parts))

        reset_col, _ = st.columns([1, 3])
        with reset_col:
            if st.button("Сбросить детализацию", key=f"drill_reset_{chart_key}", use_container_width=True):
                st.session_state["drilldown_trail"] = []
                st.session_state["drilldown_context"] = None
                st.rerun()
    elif enable_drilldown and not is_active_chart:
        st.caption("Кликните по столбцу или точке на графике, чтобы выбрать сегмент для углубления.")

    if is_active_chart and ctx:
        segment = str(ctx.get("segment_label", "сегмент"))
        st.markdown(f"Выбранный сегмент: **{segment}**")
        if st.button(
            f"Детальный анализ: {segment}",
            type="primary",
            key=f"drill_go_{chart_key}",
            use_container_width=True,
        ):
            trail = list(st.session_state.get("drilldown_trail", []))
            dim = ctx.get("dimension", "_segment")
            trail.append(
                {
                    "dimension": dim,
                    "value": ctx.get("filters", {}).get(dim, segment),
                    "label": segment,
                }
            )
            st.session_state["drilldown_trail"] = trail[-8:]
            st.session_state["pending_drilldown"] = DrilldownContext(
                filters=dict(ctx.get("filters") or {}),
                dimension=str(ctx.get("dimension") or "_segment"),
                segment_label=segment,
                trail=[{k: str(v) for k, v in step.items()} for step in trail],
            )
            st.session_state["drilldown_context"] = None
            question = build_detailed_analysis_question(segment)
            st.session_state.setdefault("main_messages", []).append(
                {"role": "user", "content": question}
            )
            st.rerun()


def _render_chart_block(
    data: list[dict],
    chart_spec: ChartSpec,
    png_path: str | None = None,
    *,
    chart_key: str | None = None,
    enable_drilldown: bool = False,
    data_explanation: str | None = None,
) -> tuple[bool, str | None]:
    """Рисует график: Plotly → PNG fallback. Возвращает (успех, текст ошибки)."""
    last_error: str | None = None

    if data and chart_spec:
        try:
            df = pd.DataFrame(data)
            repaired = repair_chart_spec(chart_spec, data)
            fig = _fig_for_streamlit(build_chart(df, repaired))
            plotly_kwargs: dict[str, Any] = {
                "use_container_width": True,
                "key": chart_key,
                "config": {"displayModeBar": True, "responsive": True, "displaylogo": False},
            }
            drill_ok = enable_drilldown and _drilldown_supported(chart_spec)
            if drill_ok and chart_key:
                plotly_kwargs["on_select"] = "rerun"
                plotly_kwargs["selection_mode"] = ("points",)
                event = st.plotly_chart(fig, **plotly_kwargs)
                _handle_plotly_selection(event, chart_spec, chart_key=chart_key)
            else:
                st.plotly_chart(fig, **plotly_kwargs)
            if data_explanation:
                st.markdown(
                    f'<p style="color:#888;font-size:0.85rem;margin-top:0.25rem;">'
                    f"Примечание: {html.escape(data_explanation)}</p>",
                    unsafe_allow_html=True,
                )
            return True, None
        except Exception as exc:
            last_error = str(exc)

    artifact = _resolve_artifact_path(png_path)
    if artifact is not None:
        st.image(str(artifact), use_container_width=True)
        return True, last_error

    return False, last_error


def _pin_fingerprint(res: AskResult) -> str:
    """Стабильный id для дедупликации закреплённых графиков."""
    res = _normalize_result(res)
    if not isinstance(res, AskResult):
        return hashlib.sha256(repr(res).encode()).hexdigest()[:16]
    spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
    parts = [
        getattr(res, "question", "") or "",
        getattr(res, "sql", "") or "",
        spec.chart_type if spec else "",
        spec.title if spec else "",
        spec.x if spec else "",
        spec.y if spec else "",
        str(len(getattr(res, "data", None) or [])),
    ]
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _is_pinned(res: AskResult) -> bool:
    fp = _pin_fingerprint(res)
    pinned: list[Any] = st.session_state.get("pinned_items", [])
    return any(_pin_fingerprint(item) == fp for item in pinned)  # type: ignore[arg-type]


def _pin_result(res: AskResult) -> None:
    if _is_pinned(res):
        return
    res = _normalize_result(res)
    if isinstance(res, AskResult) and hasattr(res, "model_dump"):
        st.session_state.setdefault("pinned_items", []).append(res.model_dump())
    else:
        st.session_state.setdefault("pinned_items", []).append(res)


def _style_dataframe(df: pd.DataFrame) -> Any:
    """Умная таблица: градиент по числам + формат Br (в духе PALETTE Blues)."""
    if df.empty:
        return df
    metric_cols = {"accrued", "paid", "debt", "penalties", "taxpayers"}
    numeric_cols = [c for c in df.select_dtypes(include="number").columns if c in metric_cols]
    styler = df.style
    if numeric_cols:
        styler = styler.background_gradient(cmap="Blues", subset=numeric_cols, axis=None)

        def _fmt_cell(v: Any) -> str:
            if pd.isna(v):
                return "—"
            if isinstance(v, (int, float)):
                return format_number_ru(v)
            return str(v)

        styler = styler.format({col: _fmt_cell for col in numeric_cols})
    return styler


def _render_styled_data_table(data: list[dict], *, table_key: str) -> None:
    """Рендер сырых данных с Pandas Styler."""
    if not data:
        st.caption("Нет строк данных для отображения.")
        return
    df = pd.DataFrame(data)
    df = df.rename(columns={c: get_russian_label(c) for c in df.columns})
    styled = _style_dataframe(df)
    st.dataframe(styled, use_container_width=True, hide_index=True, key=f"styled_df_{table_key}")


def _render_pinned_item_card(res: AskResult, *, item_idx: int) -> None:
    """Компактная карточка для вкладки «Мой дашборд»."""
    res = _normalize_result(res)
    if not isinstance(res, AskResult):
        return

    chart_spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
    data = getattr(res, "data", None) or []
    title = _chart_display_title(
        chart_spec,
        getattr(res, "question", f"График {item_idx + 1}"),
    )

    st.markdown(
        f'<div class="pinned-card"><div class="pinned-card-title">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )

    if chart_spec:
        analysis = getattr(res, "analysis", None)
        _render_chart_block(
            data,
            chart_spec,
            getattr(res, "png_path", None),
            chart_key=f"pinned_chart_{item_idx}",
            data_explanation=getattr(analysis, "data_explanation", None) if analysis else None,
        )
    elif _resolve_artifact_path(getattr(res, "png_path", None)) is not None:
        st.image(str(_resolve_artifact_path(res.png_path)), use_container_width=True)

    analysis = getattr(res, "analysis", None)
    if analysis and getattr(analysis, "key_conclusion", None):
        st.caption(analysis.key_conclusion)
    elif chart_spec and chart_spec.insights:
        st.caption(chart_spec.insights[0])

    if data:
        with st.expander("Данные", expanded=False):
            _render_styled_data_table(data, table_key=f"pinned_{item_idx}")

    if st.button("Убрать с дашборда", key=f"unpin_{item_idx}", use_container_width=True):
        fp = _pin_fingerprint(res)
        st.session_state["pinned_items"] = [
            item
            for item in st.session_state.get("pinned_items", [])
            if _pin_fingerprint(item) != fp  # type: ignore[arg-type]
        ]
        st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)


def _render_pinned_dashboard() -> None:
    """Вкладка «Мой собранный дашборд» — сетка 2 колонки."""
    items: list[Any] = st.session_state.get("pinned_items", [])

    hdr_left, hdr_right = st.columns([3, 1])
    with hdr_left:
        st.markdown("### Мой собранный дашборд")
        st.caption("Графики и выводы, которые вы закрепили из чата — всегда под рукой.")
    with hdr_right:
        if items and st.button("Очистить дашборд", use_container_width=True, key="clear_pinned"):
            st.session_state["pinned_items"] = []
            st.toast("Дашборд очищен")
            st.rerun()

    if not items:
        st.markdown(
            """
            <div class="analytics-card-wrap" style="text-align:center; padding:2rem 1rem;">
                <div style="font-size:1.1rem; margin-bottom:0.5rem; color:#666;">Нет закреплённых графиков</div>
                <div style="font-weight:700; color:#0F172A; margin-bottom:0.35rem;">Дашборд пока пуст</div>
                <div style="color:#64748B; font-size:0.92rem;">
                    Задайте вопрос в чате и нажмите «Добавить на Мой Дашборд» под понравившимся графиком.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    st.metric("Закреплено виджетов", str(len(items)))

    compare_mode = False
    if len(items) >= 2:
        compare_mode = st.checkbox("Режим сравнения (2 карточки)", key="pinned_compare_mode")

    if compare_mode and len(items) >= 2:
        labels: list[str] = []
        for i, it in enumerate(items):
            norm = _normalize_result(it)
            spec = _coerce_chart_spec(getattr(norm, "chart_spec", None))
            title = _chart_display_title(spec, getattr(norm, "question", f"График {i + 1}"))
            labels.append(f"{i + 1}. {title[:50]}")
        picked = st.multiselect(
            "Выберите две карточки для сравнения",
            options=list(range(len(items))),
            format_func=lambda i: labels[i],
            max_selections=2,
            key="pinned_compare_pick",
        )
        if len(picked) == 2:
            cols = st.columns(2, gap="medium")
            for col_i, item_idx in enumerate(picked):
                with cols[col_i]:
                    _render_pinned_item_card(_normalize_result(items[item_idx]), item_idx=item_idx)
            return

    for row_start in range(0, len(items), 2):
        cols = st.columns(2, gap="medium")
        for col_idx, item in enumerate(items[row_start : row_start + 2]):
            with cols[col_idx]:
                _render_pinned_item_card(_normalize_result(item), item_idx=row_start + col_idx)


def _quick_metrics_from_data(data: list[dict], chart_spec: ChartSpec | None) -> list[tuple[str, str]]:
    """Короткие KPI из результата запроса для панели аналитики."""
    if not data:
        return []
    df = pd.DataFrame(data)
    metrics: list[tuple[str, str]] = [("Строк в выборке", str(len(df)))]
    y_col = chart_spec.y if chart_spec else None
    if y_col and y_col in df.columns and pd.api.types.is_numeric_dtype(df[y_col]):
        total = float(df[y_col].sum())
        label = get_russian_label(y_col)
        metrics.append((f"Сумма · {label}", format_number_ru(total)))
        if len(df) > 1:
            metrics.append((f"Среднее · {label}", format_number_ru(df[y_col].mean(), decimals=1)))
    else:
        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        if numeric_cols:
            col = numeric_cols[0]
            metrics.append((get_russian_label(col), format_number_ru(float(df[col].sum()))))
    return metrics[:3]


def _render_unified_action_bar(
    res: AskResult,
    *,
    action_key: str,
) -> None:
    """Единая панель: PNG, CSV, дашборд, очередь презентации."""
    data = getattr(res, "data", None) or []
    png_artifact = _resolve_artifact_path(getattr(res, "png_path", None))
    chart_spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
    question = getattr(res, "question", "") or ""
    slug = "chart"
    if chart_spec and chart_spec.title:
        slug = chart_spec.title[:40].replace(" ", "_")
    chart_type = chart_spec.chart_type if chart_spec else None

    st.markdown('<div class="export-row unified-action-bar">', unsafe_allow_html=True)
    cols = st.columns(4)
    with cols[0]:
        if png_artifact is not None:
            with open(png_artifact, "rb") as f:
                st.download_button(
                    "PNG",
                    data=f.read(),
                    file_name=f"{slug}.png",
                    mime="image/png",
                    use_container_width=True,
                    key=f"dl_png_{action_key}",
                )
        else:
            st.button("PNG", disabled=True, use_container_width=True, key=f"dl_png_dis_{action_key}")
    with cols[1]:
        if data:
            csv_bytes = pd.DataFrame(data).to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "CSV",
                data=csv_bytes,
                file_name=f"{slug}_data.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"dl_csv_{action_key}",
            )
        else:
            st.button("CSV", disabled=True, use_container_width=True, key=f"dl_csv_dis_{action_key}")
    with cols[2]:
        if _is_pinned(res):
            st.button("На дашборде", disabled=True, use_container_width=True, key=f"pin_done_{action_key}")
        elif st.button("На дашборд", use_container_width=True, key=f"pin_add_{action_key}"):
            _pin_result(res)
            st.toast("График добавлен на «Мой дашборд»")
            st.rerun()
    with cols[3]:
        if st.button("В презентацию", use_container_width=True, key=f"pres_q_{action_key}"):
            _add_to_pres_queue(question, chart_type)
            st.toast("Вопрос добавлен в очередь презентации")
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _render_follow_up_suggestions(
    analysis: Any,
    *,
    key_prefix: str = "followup",
) -> None:
    """Smart Follow-ups: кнопки с уточняющими вопросами для следующего шага анализа."""
    questions = list(getattr(analysis, "follow_up_questions", None) or [])
    if isinstance(analysis, dict):
        questions = list(analysis.get("follow_up_questions") or [])
    questions = [q.strip() for q in questions if isinstance(q, str) and q.strip()][:3]
    if not questions:
        return

    st.markdown("##### Продолжить исследование")
    cols = st.columns(len(questions))
    for idx, question in enumerate(questions):
        with cols[idx]:
            label = question if len(question) <= 72 else f"{question[:69]}..."
            if st.button(label, key=f"{key_prefix}_{idx}", use_container_width=True):
                st.session_state["pending_prompt"] = question
                st.rerun()


def _render_analysis_block(
    analysis: Any,
    data: list[dict],
    chart_spec: ChartSpec | None,
    *,
    follow_up_key: str = "followup",
) -> None:
    """Стильный блок выводов: главный итог, инсайты, аномалии, KPI."""
    if analysis is None:
        return

    key_conclusion = getattr(analysis, "key_conclusion", None)
    insights = getattr(analysis, "insights", None) or []
    anomaly = getattr(analysis, "anomaly_or_trend", None)
    metrics = _quick_metrics_from_data(data, chart_spec)

    if key_conclusion:
        safe = html.escape(key_conclusion)
        st.markdown(
            f"""
            <div class="key-conclusion-block">
                <div class="key-conclusion-label">Главный вывод</div>
                <p class="key-conclusion-text">{safe}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    left, right = st.columns([1.45, 1], gap="medium")

    with left:
        if insights:
            st.markdown("##### Ключевые наблюдения")
            items_html = "".join(
                f'<div class="insight-item"><span class="insight-icon">—</span>'
                f'<span class="insight-text">{html.escape(ins)}</span></div>'
                for ins in insights
            )
            st.markdown(f'<div>{items_html}</div>', unsafe_allow_html=True)

    with right:
        if metrics:
            st.markdown("##### Цифры")
            for label, value in metrics:
                st.metric(label=label, value=value)
        if anomaly:
            st.markdown(
                f"""
                <div class="anomaly-block">
                    <div class="anomaly-label">Тренд / аномалия</div>
                    <div class="anomaly-text">{html.escape(anomaly)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    _render_follow_up_suggestions(analysis, key_prefix=follow_up_key)


def _render_analytics_card(
    res: AskResult,
    *,
    chart_key: str | None = None,
    enable_drilldown: bool = False,
) -> None:
    """Карточка аналитики: заголовок, график, экспорт, выводы."""
    chart_spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
    data = getattr(res, "data", None) or []
    analysis = getattr(res, "analysis", None)

    question = getattr(res, "question", "Результат анализа")
    title = _chart_display_title(chart_spec, question)
    subtitle = _chart_subtitle(chart_spec, question)
    chart_ok = False
    badge_class = "status-badge"
    badge_text = "Успешно проанализировано"

    render_spec = chart_spec
    render_data = data
    if chart_spec and chart_key and data:
        render_spec, render_data = _prepare_ask_chart_render(
            res, chart_spec, data, chart_key=chart_key
        )

    png_artifact = _resolve_artifact_path(getattr(res, "png_path", None))
    if png_artifact is None and render_spec and not _chart_buildable(render_data, render_spec):
        _render_no_viz_only(res, _CHART_BUILD_FAIL_MSG)
        if _is_analyst_mode():
            _render_technical_details(res)
        return

    with st.container(border=False):
        st.markdown('<div class="analytics-card-wrap">', unsafe_allow_html=True)

        st.markdown(
            f"""
            <div class="analytics-card-header">
                <h3 class="analytics-title">{html.escape(title)}</h3>
                <span class="{badge_class}">{badge_text}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if subtitle:
            st.markdown(
                f'<div class="card-subtitle">{html.escape(subtitle)}</div>',
                unsafe_allow_html=True,
            )

        _render_drilldown_chrome(chart_key, render_spec, enable_drilldown=enable_drilldown)

        st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
        if render_spec:
            data_expl = (
                getattr(analysis, "data_explanation", None) if analysis else None
            )
            chart_ok, _ = _render_chart_block(
                render_data,
                render_spec,
                getattr(res, "png_path", None),
                chart_key=chart_key,
                enable_drilldown=enable_drilldown,
                data_explanation=data_expl,
            )
        elif png_artifact is not None:
            st.image(str(png_artifact), use_container_width=True)
            chart_ok = True
        else:
            _render_chart_error("Спецификация графика не была сформирована для этого запроса.")
        st.markdown("</div>", unsafe_allow_html=True)

        if not chart_ok and png_artifact is None:
            st.markdown("</div>", unsafe_allow_html=True)
            _render_no_viz_only(res, _CHART_BUILD_FAIL_MSG)
            if _is_analyst_mode():
                _render_technical_details(res)
            return

        if chart_ok or render_data or png_artifact is not None:
            _render_unified_action_bar(res, action_key=chart_key or "default")

        if render_data and _is_analyst_mode():
            with st.expander("Данные", expanded=False):
                _render_styled_data_table(render_data, table_key=chart_key or "default")

        if analysis or (render_spec and getattr(render_spec, "insights", None)):
            st.markdown("---")
            if analysis:
                _render_analysis_block(
                    analysis,
                    render_data,
                    render_spec,
                    follow_up_key=f"card_{chart_key or 'default'}",
                )
            elif render_spec and render_spec.insights:
                pseudo = type("A", (), {"insights": render_spec.insights, "key_conclusion": None, "anomaly_or_trend": None})()
                _render_analysis_block(
                    pseudo,
                    render_data,
                    render_spec,
                    follow_up_key=f"card_{chart_key or 'default'}",
                )

        if _is_analyst_mode():
            _render_technical_details(res)
        st.markdown("</div>", unsafe_allow_html=True)


def _render_planner_result(
    res: Any,
    *,
    chart_key: str | None = None,
    enable_drilldown: bool = False,
) -> None:
    """Алиас для рендера результата Planner/Ask — карточка + smart follow-ups в analysis block."""
    render_assistant_response(res, chart_key=chart_key, enable_drilldown=enable_drilldown)


def _render_empty_state() -> None:
    """Приветственный экран с категориями сценариев."""
    st.markdown(
        f"""
        <div class="empty-hero">
            <h2>Добро пожаловать в BI-Аналитику</h2>
            <p>Задайте вопрос на русском или выберите готовый сценарий ниже</p>
            <p style="font-size:0.88rem; color:#64748B;">Ожидаемое время ответа: {ESTIMATED_RESPONSE_SEC} с</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    card_idx = 0
    for category, cards in PROMPT_CARD_CATEGORIES:
        st.markdown(f'<div class="category-label">{html.escape(category)}</div>', unsafe_allow_html=True)
        st.markdown('<div class="empty-grid">', unsafe_allow_html=True)
        row_size = min(3, len(cards))
        cols = st.columns(row_size)
        for col_idx, (heading, desc, query) in enumerate(cards):
            with cols[col_idx]:
                label = f"{heading}\n\n{desc}"
                if st.button(label, key=f"card_{card_idx}", use_container_width=True):
                    st.session_state["pending_prompt"] = query
                    st.rerun()
                card_idx += 1
        st.markdown("</div>", unsafe_allow_html=True)


def _render_prompt_chips() -> None:
    """Обратная совместимость: компактные чипы (3 шт.)."""
    _render_empty_state()


def _session_drilldown_context() -> DrilldownContext | None:
    return session_drilldown_context(
        st.session_state.get("pending_drilldown"),
        st.session_state.get("drilldown_context"),
        st.session_state.get("drilldown_trail"),
    )


def _run_background_with_pipeline(
    worker_fn: Any,
    label: str,
    live_slot: Any,
    status: Any,
    *,
    poll_interval: float = 0.32,
    timeout_sec: float | None = None,
) -> Any:
    """Общий runner: фоновая задача + live pipeline UI."""
    if timeout_sec is None:
        timeout_sec = float(config.pipeline_timeout_sec)
    run_id = uuid.uuid4().hex[:10]
    pipeline_store.reset(run_id, label)

    result_holder: dict[str, Any] = {}
    error_holder: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result_holder["result"] = worker_fn()
        except BaseException as exc:
            error_holder["error"] = exc
        finally:
            success = "error" not in error_holder
            err_msg = str(error_holder["error"]) if not success else None
            pipeline_store.finish(success=success, error=err_msg)

    thread = threading.Thread(target=_worker, name=f"pipeline-{run_id}", daemon=True)
    thread.start()
    deadline = time.time() + timeout_sec

    while thread.is_alive():
        if time.time() > deadline:
            pipeline_store.finish(success=False, error=f"Таймаут ({int(timeout_sec)} с)")
            raise TimeoutError(
                f"Обработка запроса превысила {int(timeout_sec)} с. Проверьте Ollama и повторите."
            )
        snapshot = pipeline_store.snapshot()
        update_pipeline_live_ui(live_slot, status, snapshot)
        time.sleep(poll_interval)

    thread.join(timeout=1.0)
    snapshot = pipeline_store.snapshot()
    update_pipeline_live_ui(live_slot, status, snapshot)

    if "error" in error_holder:
        raise error_holder["error"]
    if "result" not in result_holder:
        raise RuntimeError("Фоновая задача завершилась без результата")
    return result_holder["result"]


def _run_query_with_live_pipeline(
    prompt: str,
    live_slot: Any,
    status: Any,
    *,
    drilldown: DrilldownContext | None = None,
    poll_interval: float = 0.32,
) -> Any:
    """Запускает Orchestrator в фоне и обновляет визуализатор пайплайна в реальном времени."""
    return _run_background_with_pipeline(
        lambda: _run_query(prompt, drilldown=drilldown),
        prompt,
        live_slot,
        status,
        poll_interval=poll_interval,
    )


def _render_technical_details(res: Any) -> None:
    """SQL, reasoning и прочее — только для любопытных."""
    with st.popover("Технические детали"):
        if hasattr(res, "sql") and getattr(res, "sql", None):
            st.caption("SQL-запрос")
            st.code(res.sql, language="sql")
        if hasattr(res, "source_sql") and getattr(res, "source_sql", None):
            st.caption("SQL-запрос")
            st.code(res.source_sql, language="sql")
        if hasattr(res, "data") and isinstance(getattr(res, "data", None), list) and res.data:
            st.caption(f"Строк данных: {len(res.data)} (превью 5)")
            preview_df = pd.DataFrame(res.data[:5])
            if not preview_df.empty:
                preview_df = preview_df.rename(
                    columns={c: get_russian_label(c) for c in preview_df.columns}
                )
                st.dataframe(preview_df, hide_index=True)
        if hasattr(res, "reasoning") and getattr(res, "reasoning", None):
            st.caption("Служебное пояснение")
            st.write(res.reasoning)
        if hasattr(res, "png_path") and getattr(res, "png_path", None):
            st.caption(f"Артефакт: `{res.png_path}`")
        if hasattr(res, "model_dump"):
            with st.expander("JSON", expanded=False):
                st.json(res.model_dump())


def _find_last_drilldown_message_idx(messages: list[dict[str, Any]]) -> int | None:
    """Индекс последнего assistant-сообщения с графиком (для интерактивного drill-down)."""
    for idx in range(len(messages) - 1, -1, -1):
        msg = messages[idx]
        if msg.get("role") != "assistant" or msg.get("result") is None:
            continue
        res = _normalize_result(msg["result"])
        if isinstance(res, AskResult) or getattr(res, "chart_spec", None):
            spec = _coerce_chart_spec(getattr(res, "chart_spec", None))
            data = getattr(res, "data", None) or []
            if spec and data:
                return idx
    return None


def render_assistant_response(
    res: Any,
    *,
    chart_key: str | None = None,
    enable_drilldown: bool = False,
) -> None:
    """Красивый рендер ответа ассистента для бизнес-пользователя."""
    if res is None:
        st.warning("Не удалось получить ответ.")
        return

    res = _normalize_result(res)
    show_analyst = _is_analyst_mode()

    if isinstance(res, AskResult):
        no_viz_msg = _no_viz_user_message(res)
        if no_viz_msg:
            if show_analyst:
                render_planner_trace(res, key_prefix=chart_key or "trace", show=True)
            _render_no_viz_only(res, no_viz_msg)
            if show_analyst:
                _render_technical_details(res)
            return

    render_planner_trace(res, key_prefix=chart_key or "trace", show=show_analyst)

    if hasattr(res, "success") and not getattr(res, "success", True):
        st.markdown(
            f"""
            <div class="chart-error-block">
                <div class="chart-error-icon">!</div>
                <div>
                    <div class="chart-error-title">Запрос не выполнен</div>
                    <div class="chart-error-desc">{html.escape(getattr(res, "error", None) or "Неизвестная ошибка")}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if show_analyst:
            _render_technical_details(res)
        return

    # Презентация
    if hasattr(res, "pptx_path") and getattr(res, "pptx_path", None):
        _render_presentation_block(res, key_prefix=chart_key or "chat_pres")
        if show_analyst:
            _render_technical_details(res)
        return

    # Дашборд
    if isinstance(res, DashboardResult) or (
        hasattr(res, "charts") and hasattr(res, "kpi_cards")
    ):
        _render_dashboard(res, chart_key_prefix=chart_key or "dash")
        if show_analyst:
            _render_technical_details(res)
        return

    # AskResult — премиальная карточка
    if isinstance(res, AskResult) or (
        hasattr(res, "chart_spec") or hasattr(res, "analysis")
    ):
        _render_analytics_card(
            res,
            chart_key=chart_key,
            enable_drilldown=enable_drilldown,
        )  # type: ignore[arg-type]
        return

    # Текстовый fallback
    with st.container():
        if hasattr(res, "insights") and res.insights:
            pseudo = type(
                "A",
                (),
                {
                    "insights": res.insights,
                    "key_conclusion": getattr(res, "key_conclusion", None),
                    "anomaly_or_trend": getattr(res, "anomaly_or_trend", None),
                },
            )()
            _render_analysis_block(pseudo, [], None)
        elif hasattr(res, "summary") and res.summary:
            st.write(res.summary)
        else:
            st.write("Готово. Уточните вопрос, если нужны дополнительные детали.")
    if show_analyst:
        _render_technical_details(res)


def _render_dashboard(res: DashboardResult, *, chart_key_prefix: str = "dash") -> None:
    """Рендер DashboardResult в чате: KPI + графики + выводы."""
    with st.container():
        st.markdown('<div class="analytics-card-wrap">', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="analytics-card-header">
                <h3 class="analytics-title">{html.escape(res.title)}</h3>
                <span class="status-badge">Дашборд сформирован</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if res.summary:
            st.markdown(res.summary)

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
            data_rows = df.to_dict(orient="records")
            available_regions = sorted(df["region"].dropna().unique().tolist()) if "region" in df.columns else []
            n_cols = max(1, min(getattr(res.layout, "columns", 2), 2))
            layout_type = getattr(res.layout, "type", "kpi_top_grid")

            st.markdown('<div class="chart-panel">', unsafe_allow_html=True)
            if "tab" in layout_type:
                tab_names = [c.title[:36] for c in res.charts]
                ctabs = st.tabs(tab_names)
                for i, spec in enumerate(res.charts):
                    coerced = _coerce_chart_spec(spec)
                    with ctabs[i]:
                        if coerced is None:
                            _render_chart_error("Некорректная спецификация графика.")
                        else:
                            if _is_analyst_mode():
                                _render_dashboard_chart_editor(
                                    coerced,
                                    chart_key_prefix=chart_key_prefix,
                                    chart_idx=i,
                                    available_regions=available_regions,
                                )
                            ek = _dashboard_editor_key(chart_key_prefix, i)
                            filtered = _filter_data_by_regions(
                                data_rows,
                                (st.session_state.get(ek, {}) or {}).get("regions"),
                            )
                            edited = _read_dashboard_chart_override(
                                coerced,
                                chart_key_prefix=chart_key_prefix,
                                chart_idx=i,
                                available_regions=available_regions,
                            )
                            _render_chart_block(
                                filtered,
                                edited,
                                chart_key=f"{chart_key_prefix}_tab_{i}",
                            )
            else:
                chart_cols = st.columns(n_cols)
                for i, spec in enumerate(res.charts):
                    coerced = _coerce_chart_spec(spec)
                    with chart_cols[i % n_cols]:
                        if coerced is None:
                            _render_chart_error("Некорректная спецификация графика.")
                        else:
                            if coerced.title:
                                st.caption(coerced.title)
                            if _is_analyst_mode():
                                _render_dashboard_chart_editor(
                                    coerced,
                                    chart_key_prefix=chart_key_prefix,
                                    chart_idx=i,
                                    available_regions=available_regions,
                                )
                            ek = _dashboard_editor_key(chart_key_prefix, i)
                            filtered = _filter_data_by_regions(
                                data_rows,
                                (st.session_state.get(ek, {}) or {}).get("regions"),
                            )
                            edited = _read_dashboard_chart_override(
                                coerced,
                                chart_key_prefix=chart_key_prefix,
                                chart_idx=i,
                                available_regions=available_regions,
                            )
                            _render_chart_block(
                                filtered,
                                edited,
                                chart_key=f"{chart_key_prefix}_grid_{i}",
                            )
            st.markdown("</div>", unsafe_allow_html=True)

            if data_rows:
                csv_bytes = df.to_csv(index=False).encode("utf-8-sig")
                st.download_button(
                    "Скачать данные дашборда (CSV)",
                    data=csv_bytes,
                    file_name="dashboard_data.csv",
                    mime="text/csv",
                    key=f"dl_dash_csv_{chart_key_prefix}",
                )
        elif res.charts:
            _render_chart_error("Графики подготовлены, но данные для отображения отсутствуют.")

        if res.insights:
            st.markdown("---")
            pseudo = type(
                "A",
                (),
                {"insights": res.insights, "key_conclusion": None, "anomaly_or_trend": None},
            )()
            _render_analysis_block(pseudo, getattr(res, "data", None) or [], None)

        st.markdown("</div>", unsafe_allow_html=True)


def _run_query(
    prompt: str,
    *,
    drilldown: DrilldownContext | None = None,
    correlation_id: str | None = None,
) -> Any:
    """Выполняет запрос через Orchestrator.ask() — Planner выбирает маршрут."""
    orch = get_orchestrator()
    return orch.ask(prompt, drilldown=drilldown, correlation_id=correlation_id)


def _build_presentation_qlist() -> list[dict[str, Any]]:
    pres_mode = st.session_state.get("pres_mode", "По вопросам")
    chart_type_val = CHART_VAL_FOR_DISPLAY.get(st.session_state.get("pres_chart_type", "авто"))
    if pres_mode == "По вопросам":
        queue = list(st.session_state.get("pres_queue") or [])
        if queue:
            return queue
        lines = [
            ln.strip()
            for ln in st.session_state.get("pres_questions_area", "").splitlines()
            if ln.strip()
        ]
        return [{"text": ln, "chart_type": chart_type_val, "note": ""} for ln in lines]
    theme = st.session_state.get("pres_theme", "").strip()
    return [{"text": theme, "chart_type": chart_type_val, "note": ""}] if theme else []


def _render_presentation_workspace() -> None:
    st.markdown("### Презентация для руководства")
    st.caption("Соберите executive-колоду из вопросов или очереди из чата.")

    queue = st.session_state.get("pres_queue") or []
    if queue:
        st.markdown("**Очередь из чата**")
        for i, item in enumerate(queue, 1):
            st.caption(f"{i}. {item.get('text', '')}")
        if st.button("Очистить очередь", key="clear_pres_queue"):
            st.session_state["pres_queue"] = []
            st.rerun()

    pres_mode = st.radio(
        "Формат",
        ["По вопросам", "Одной темой"],
        horizontal=True,
        key="pres_mode",
    )
    if pres_mode == "По вопросам" and not queue:
        default_q = "Структура налогов по видам (доли)\nТоп-3 региона по задолженности"
        if "pres_questions_area" not in st.session_state:
            st.session_state["pres_questions_area"] = default_q
        st.text_area(
            "Вопросы (по одному на строку)",
            height=120,
            key="pres_questions_area",
        )
    elif pres_mode == "Одной темой":
        st.text_input(
            "Тема презентации",
            value=st.session_state.get(
                "pres_theme", "Налоговая аналитика Республики Беларусь за 2024 год"
            ),
            key="pres_theme_input",
        )
        st.session_state["pres_theme"] = st.session_state.get("pres_theme_input", "")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.slider("Слайдов", 5, 12, 7, key="pres_slides")
    with c2:
        st.selectbox("Тип графика", CHART_DISPLAY_OPTIONS, index=0, key="pres_chart_type")
    with c3:
        st.checkbox("Титульный слайд", value=True, key="pres_title")
        st.checkbox("Рекомендации", value=True, key="pres_recs")

    if st.button("Создать презентацию", type="primary", use_container_width=True, key="pres_build"):
        qlist = _build_presentation_qlist()
        if not qlist:
            st.warning("Добавьте вопросы или заполните тему.")
        else:
            try:
                pres_res = get_orchestrator().presentation(
                    qlist,
                    num_slides=st.session_state.get("pres_slides", 7),
                    include_title=st.session_state.get("pres_title", True),
                    include_recommendations=st.session_state.get("pres_recs", True),
                )
                st.session_state["last_presentation"] = pres_res
                st.session_state["main_messages"].append({"role": "assistant", "result": pres_res})
                st.session_state["pres_queue"] = []
                st.success(f"Готово: {pres_res.num_slides} слайдов")
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка: {exc}")

    if st.session_state.get("last_presentation"):
        st.markdown("---")
        _render_presentation_block(st.session_state["last_presentation"], key_prefix="workspace_pres")


def _render_dashboard_workspace() -> None:
    st.markdown("### Комплексный дашборд")
    st.caption(f"Ожидаемое время ответа: {ESTIMATED_RESPONSE_SEC} с")
    default_q = "Покажи дашборд по задолженности по регионам"
    question = st.text_area(
        "Тема дашборда",
        value=st.session_state.get("dashboard_workspace_q", default_q),
        height=90,
        key="dashboard_workspace_input",
    )
    st.session_state["dashboard_workspace_q"] = question
    if st.button("Построить дашборд", type="primary", key="build_dashboard_ws"):
        q = question.strip()
        if not q:
            st.warning("Введите тему дашборда.")
        else:
            try:
                dd = _effective_drilldown()
                result = get_orchestrator().dashboard(
                    q,
                    drilldown=dd,
                )
                st.session_state["workspace_dashboard_result"] = result
                st.session_state["main_messages"].append({"role": "user", "content": q})
                st.session_state["main_messages"].append({"role": "assistant", "result": result})
                hist = st.session_state.get("dashboard_history", [])
                entry = {"question": q, "title": getattr(result, "title", q)}
                if not hist or hist[-1] != entry:
                    hist.append(entry)
                    st.session_state["dashboard_history"] = hist[-12:]
                st.rerun()
            except Exception as exc:
                st.error(f"Ошибка: {exc}")

    if st.session_state.get("workspace_dashboard_result"):
        st.markdown("---")
        _render_dashboard(st.session_state["workspace_dashboard_result"], chart_key_prefix="ws_dash")


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### Навигация")
        st.caption("Налоговая аналитика РБ · локально · 2024")

        _render_global_filters()

        with st.expander("Источник данных", expanded=False):
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
                if _is_analyst_mode():
                    st.dataframe(df.head(5), use_container_width=True, hide_index=True)

        st.markdown("**Быстрые вопросы**")
        for idx, sug in enumerate(SUGGESTION_PROMPTS):
            if st.button(sug, key=f"sug_{idx}", use_container_width=True):
                st.session_state["pending_prompt"] = sug

        recent = _recent_user_questions()
        if recent:
            with st.expander("История запросов", expanded=False):
                for idx, q in enumerate(recent):
                    if st.button(q[:72], key=f"hist_{idx}", use_container_width=True):
                        st.session_state["pending_prompt"] = q

        if st.session_state.get("dashboard_history"):
            with st.expander("История дашбордов", expanded=False):
                seen: set[str] = set()
                for item in reversed(st.session_state["dashboard_history"]):
                    q = item.get("question", "")
                    if not q or q in seen:
                        continue
                    seen.add(q)
                    if st.button(q[:60], key=f"dh_{hash(q)}", use_container_width=True):
                        st.session_state["pending_prompt"] = q

        st.divider()
        export_payload = json.dumps(_session_export_payload(), ensure_ascii=False, indent=2, default=str)
        st.download_button(
            "Сохранить сессию (JSON)",
            data=export_payload.encode("utf-8"),
            file_name="bi_session.json",
            mime="application/json",
            use_container_width=True,
            key="dl_session_json",
        )
        if st.button("Очистить чат", use_container_width=True):
            st.session_state["main_messages"] = []
            st.session_state["dashboard_history"] = []
            st.session_state["drilldown_context"] = None
            st.session_state["drilldown_trail"] = []
            st.session_state["pres_queue"] = []
            st.session_state["workspace_dashboard_result"] = None
            st.rerun()


def main() -> None:
    st.set_page_config(
        page_title="BI-Аналитика",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    _inject_custom_css()
    _init_ux_session_state()

    if "main_messages" not in st.session_state:
        st.session_state["main_messages"] = []
    if "messages" in st.session_state and not st.session_state["main_messages"]:
        st.session_state["main_messages"] = st.session_state.pop("messages")
    if "dashboard_history" not in st.session_state:
        st.session_state["dashboard_history"] = []
    if "pinned_items" not in st.session_state:
        st.session_state["pinned_items"] = []
    if "drilldown_context" not in st.session_state:
        st.session_state["drilldown_context"] = None
    if "drilldown_trail" not in st.session_state:
        st.session_state["drilldown_trail"] = []

    _render_gov_disclaimer()
    _render_app_header()
    _render_sidebar()

    tab_chat, tab_dashboard, tab_pres, tab_pinned = st.tabs(
        ["Аналитический вопрос", "Дашборд", "Презентация", "Мой дашборд"]
    )

    with tab_chat:
        if not st.session_state["main_messages"]:
            _render_empty_state()

        last_drill_idx = _find_last_drilldown_message_idx(st.session_state["main_messages"])

        for msg_idx, msg in enumerate(st.session_state["main_messages"]):
            with st.chat_message(msg["role"]):
                if msg["role"] == "user":
                    st.write(msg.get("content", ""))
                elif msg.get("result") is not None:
                    render_assistant_response(
                        msg["result"],
                        chart_key=f"chat_chart_{msg_idx}",
                        enable_drilldown=msg_idx == last_drill_idx
                        and _drilldown_supported(
                            _coerce_chart_spec(
                                _normalize_result(msg["result"]).chart_spec
                                if msg.get("result") is not None
                                and isinstance(_normalize_result(msg["result"]), AskResult)
                                else None
                            )
                        ),
                    )
                else:
                    st.write(msg.get("content", ""))

    with tab_dashboard:
        _render_dashboard_workspace()

    with tab_pres:
        _render_presentation_workspace()

    with tab_pinned:
        _render_pinned_dashboard()

    prompt = st.session_state.pop("pending_prompt", None)
    drilldown = st.session_state.pop("pending_drilldown", None)
    if drilldown is None:
        drilldown = _effective_drilldown()
    chat_prompt = st.chat_input(
        "Спросите что-нибудь о налогах (например, «Динамика по Минску»)"
    )
    if chat_prompt:
        prompt = chat_prompt

    messages = st.session_state["main_messages"]
    if not prompt and messages and messages[-1].get("role") == "user":
        prompt = messages[-1].get("content", "")

    if prompt and prompt.strip():
        prompt = prompt.strip()
        # Защита от зацикливания: не дублируем user-сообщение при повторном rerun
        if not (
            messages
            and messages[-1].get("role") == "user"
            and messages[-1].get("content") == prompt
        ):
            st.session_state["main_messages"].append({"role": "user", "content": prompt})

        cid = new_correlation_id()
        run_logger.log_event("ui_query_start", question=prompt[:200], correlation_id=cid)
        assistant_msg: dict[str, Any] | None = None
        with st.chat_message("assistant"):
            with st.status(
                "AI-конвейер запускается...",
                expanded=_is_analyst_mode(),
            ) as status:
                live_pipeline = st.empty()
                try:
                    result = _run_background_with_pipeline(
                        lambda: _run_query(prompt, drilldown=drilldown, correlation_id=cid),
                        prompt,
                        live_pipeline,
                        status,
                    )
                    final_snap = pipeline_store.snapshot()
                    has_stage_error = any(
                        s.get("status") == "error"
                        for s in (final_snap.get("stages") or {}).values()
                    )
                    if has_stage_error and not final_snap.get("fatal_error"):
                        status.update(
                            label="Готово с предупреждениями",
                            state="complete",
                            expanded=_is_analyst_mode(),
                        )
                    else:
                        status.update(
                            label="Готово",
                            state="complete",
                            expanded=False,
                        )
                    assistant_msg = {"role": "assistant", "result": result}
                    if isinstance(result, DashboardResult):
                        hist = st.session_state["dashboard_history"]
                        entry = {"question": prompt, "title": result.title}
                        if not hist or hist[-1] != entry:
                            hist.append(entry)
                            st.session_state["dashboard_history"] = hist[-12:]
                except TimeoutError as exc:
                    status.update(label="Превышен таймаут обработки", state="error", expanded=True)
                    assistant_msg = {
                        "role": "assistant",
                        "content": (
                            f"{exc}\n\nПроверьте Ollama и модель `{config.ollama_model}`."
                        ),
                    }
                except Exception as exc:
                    err_snap = pipeline_store.snapshot()
                    status.update(
                        label=pipeline_status_headline(err_snap)
                        if err_snap
                        else f"Ошибка: {exc}",
                        state="error",
                        expanded=True,
                    )
                    err_text = (
                        "Не удалось обработать запрос. Проверьте, что Ollama запущен "
                        f"и модель `{config.ollama_model}` доступна."
                    )
                    assistant_msg = {
                        "role": "assistant",
                        "content": f"{err_text}\n\n{exc}",
                    }

        if assistant_msg is not None:
            st.session_state["main_messages"].append(assistant_msg)
        st.rerun()


if __name__ == "__main__":
    main()