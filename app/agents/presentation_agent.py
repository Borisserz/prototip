"""PresentationAgent (Phase 6): авто-сборка .pptx презентации.

Вход: список вопросов list[str].
Внутри для каждого вызывает PlannerAgent через AgentExecutor,
собирает результаты, встраивает PNG из out/, инсайты, ключевые выводы.
Сохраняет в out/presentation.pptx

Стиль: тёмно-синий, Arial, простой и аккуратный.
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.agents.base_agent import BaseAgent
from app.agents.factory import get_executor
from app.agents.models import AskResult, DeckNarrative, PresentationInput, PresentationResult
from app.pipeline_progress import emit_pipeline_stage, suppress_pipeline_emit
from core.llm import call_structured, setup_logging
from viz.charts import build_chart, export_png
from viz.style import format_number_ru

# Ensure central logging (idempotent) — after imports to satisfy linter
setup_logging()
logger = logging.getLogger("PresentationAgent")

DARK_BLUE = RGBColor(0, 51, 102)
GRAY = RGBColor(80, 80, 80)
BODY_GRAY = RGBColor(60, 60, 60)
CARD_BG = RGBColor(245, 247, 250)
FOOTER_COLOR = RGBColor(128, 128, 128)

SLIDE_WIDTH_IN = 13.333
SLIDE_MARGIN_H_IN = 0.45
SLIDE_CONTENT_GAP_IN = 0.15
SLIDE_CONTENT_TOP_IN = 1.05
SLIDE_CONTENT_HEIGHT_IN = 5.75

CHART_TYPE_RU: dict[str, str] = {
    "bar": "столбчатая",
    "grouped_bar": "группированная столбчатая",
    "stacked_bar": "стековая столбчатая",
    "line": "линейная",
    "horizontal_bar": "горизонтальная столбчатая",
    "donut": "круговая",
    "kpi": "KPI-индикатор",
    "heatmap": "тепловая карта",
    "area": "областная",
    "scatter": "точечная",
    "waterfall": "водопад",
    "treemap": "древовидная (treemap)",
}


class PresentationAgent(BaseAgent):
    """Агент сборки презентаций .pptx из результатов PlannerAgent/AgentExecutor."""

    name = "presentation_agent"
    description = "По списку вопросов собирает .pptx: для каждого вызывает planner_agent через AgentExecutor, рендерит PNG через viz, добавляет нарратив (DeckNarrative via LLM), титульные/темы/выводы/рекомендации. Уважает prefs по chart_type."

    def _slug(self, text: str, max_len: int = 40) -> str:
        import re

        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

    def _get_deck_narrative(self, questions: list[str], results: list[AskResult]) -> DeckNarrative:
        """Один structured вызов LLM для нарратива презентации (после сбора всех ответов)."""
        summaries: list[str] = []
        for q, r in zip(questions, results):  # noqa: B905
            conc = (r.analysis.key_conclusion if r.analysis else "") or ""
            anom = (r.analysis.anomaly_or_trend if r.analysis else "") or "нет"
            action = (
                getattr(r.chart_spec, "action_title", None) if r.chart_spec else None
            ) or ""
            action_line = f"Action title: {action}\n" if action else ""
            summaries.append(
                f"Вопрос: {q}\n{action_line}Ключевой вывод: {conc}\nАномалия/тренд: {anom}"
            )

        prompt = f"""Ты — старший аналитик, готовящий презентацию для руководства по налоговой статистике Республики Беларусь (синтетические данные).

Проанализируй результаты по вопросам и верни DeckNarrative строго по схеме:
- overview: 2-4 предложения (цель, охват по периоду/регионам/видам налогов/объёмам, метод: локальная мультиагентная система на базе Text-to-SQL + Analyst + Chart).
- themes: 2-4 коротких темы/повестки.
- key_takeaways: 4-6 главных выводов.
- recommendations: 2-4 конкретных, actionable рекомендаций.

Вопросы и выводы:
{chr(10).join(summaries)}

Все тексты на русском, профессионально, без воды. Верни только валидный JSON по схеме DeckNarrative.
"""
        return call_structured(
            prompt,
            schema=DeckNarrative,
            system="Ты — точный аналитик презентаций. Выдавай только валидный JSON по схеме DeckNarrative. Тексты на русском.",
        )

    def run(
        self,
        questions: list[str] | list[dict] | list | PresentationInput,
        num_slides: int | None = None,
        include_title: bool = True,
        include_recommendations: bool = True,
    ) -> PresentationResult:
        """Собрать презентацию по списку вопросов с DeckNarrative и улучшенной структурой.

        Поддерживает list[str], list[dict с text/chart_type/note] (из UI payload) или PresentationInput.
        num_slides + include_* позволяют строить exact кол-во слайдов (с appendix если нужно).
        Для pref: если дан chart_type в блоке — оверрайдим spec.chart_type перед ребилдом (уважаем выбор пользователя).
        Для каждого вопроса вызывает planner_agent через AgentExecutor,
        использует данные + chart_spec для стилизованного PNG (без заголовка графика, pres_slide_ png).
        После всех — один structured вызов для DeckNarrative.
        """
        start = time.time()
        presentation_id = uuid.uuid4().hex[:10]
        emit_pipeline_stage(
            "synthesis",
            "running",
            f"Сборка презентации ({presentation_id})...",
            agent="presentation_agent",
        )
        # нормализация входа (поддержка prefs из формы)
        qlist: list[dict] = []
        if isinstance(questions, PresentationInput):
            qlist = [{"text": q} for q in questions.questions]
        elif questions and isinstance(questions[0], dict):
            qlist = questions  # type: ignore[assignment]
        else:
            qlist = [{"text": q} for q in (questions or [])]
        qs: list[str] = [q.get("text", str(q)) for q in qlist if str(q.get("text", "")).strip()]
        # prefs по индексу (для оверрайда chart_type и caption)
        prefs: dict[int, str | None] = {}
        notes: dict[int, str | None] = {}
        for _i, qb in enumerate(qlist):
            if str(qb.get("text", "")).strip():
                prefs[len(prefs)] = qb.get("chart_type")
                notes[len(notes)] = qb.get("note")
        logger.info(
            f"[PresentationAgent] start: questions={len(qs)} num_slides={num_slides} inc_title={include_title} inc_recs={include_recommendations}"
        )
        if not qs:
            raise ValueError("questions не может быть пустым")

        questions = qs  # для обратной совместимости с остальным кодом (narrative, слайды и т.д.)

        # Ранний срез по num_slides (чтобы не тратить LLM на лишние вопросы + для exact count)
        orig_qlist = list(qlist)
        if num_slides and num_slides > 0:
            base_fixed = (1 if include_title else 0) + 2 + 1 + (1 if include_recommendations else 0)
            max_q = max(0, num_slides - base_fixed)
            if len(questions) > max_q > 0:
                questions = questions[:max_q]
            elif max_q == 0:
                questions = questions[:1] if questions else []
            # пересобрать prefs/notes под урезанный список (индексы 0-based для used)
            prefs = {}
            notes = {}
            uidx = 0
            for qb in orig_qlist:
                if str(qb.get("text", "")).strip() and uidx < len(questions):
                    prefs[uidx] = qb.get("chart_type")
                    notes[uidx] = qb.get("note")
                    uidx += 1

        executor = get_executor(include_planner=True)

        out_dir = Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = out_dir / "presentation.pptx"

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank_layout = prs.slide_layouts[6]

        # === 1. Собрать результаты по всем вопросам (логика в Orchestrator) ===
        # (используем все qs; срез/appendix решим по num_slides после)
        results: list[AskResult] = []
        with suppress_pipeline_emit():
            for qi, q in enumerate(qs):
                emit_pipeline_stage(
                    "synthesis",
                    "running",
                    f"Вопрос {qi + 1}/{len(qs)}: {str(q)[:50]}...",
                    agent="presentation_agent",
                )
                raw = executor.run("planner_agent", q)
                if isinstance(raw, AskResult):
                    res = raw
                else:
                    res = AskResult(
                        question=q,
                        sql=getattr(raw, "source_sql", "") or "",
                        data=getattr(raw, "data", []) or [],
                        reasoning=getattr(
                            raw, "reasoning", "PresentationAgent received non-AskResult"
                        ),
                        error=getattr(raw, "error", None),
                        success=getattr(raw, "success", True),
                    )
                results.append(res)
        logger.info(f"[PresentationAgent] collected {len(results)} results")

        # === 2. DeckNarrative (один structured call, логируем) ===
        try:
            narrative = self._get_deck_narrative(questions, results)
            logger.info(
                f"[PresentationAgent] narrative: themes={len(narrative.themes)} takeaways={len(narrative.key_takeaways)} recs={len(narrative.recommendations)}"
            )
        except Exception as e:
            logger.info(f"[PresentationAgent] narrative_error_fallback: {e}")
            narrative = DeckNarrative(
                overview="Презентация содержит анализ налоговых поступлений Республики Беларусь по синтетическим данным за 2024 год с использованием локальной мультиагентной системы (Text-to-SQL + анализ + визуализация).",
                themes=[
                    "Тенденции поступлений по регионам и видам налогов",
                    "Проблемы собираемости и задолженности",
                ],
                key_takeaways=[
                    "г. Минск обеспечивает значительную долю начислений.",
                    "Наблюдается сезонный рост к концу года.",
                    "Задолженность сконцентрирована в отдельных регионах.",
                    "Высокая собираемость по подоходному налогу.",
                ],
                recommendations=[
                    "Усилить мониторинг в регионах с высокой задолженностью.",
                    "Проанализировать аномалии в конкретных видах налогов.",
                ],
            )

        # === 3. Титул (conditional по include_title) ===
        if include_title:
            slide = prs.slides.add_slide(blank_layout)
            self._add_centered_text(
                slide,
                "BI-аналитика налогов РБ",
                top=Inches(1.8),
                font_size=40,
                bold=True,
                color=DARK_BLUE,
            )
            self._add_centered_text(
                slide,
                "Синтетические данные (демо), Республика Беларусь",
                top=Inches(3.0),
                font_size=20,
                color=GRAY,
            )
            self._add_centered_text(
                slide,
                datetime.now().strftime("%d.%m.%Y"),
                top=Inches(3.7),
                font_size=16,
                color=GRAY,
            )
            self._add_centered_text(
                slide,
                "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
                top=Inches(6.5),
                font_size=10,
                color=FOOTER_COLOR,
            )

        # === 4. Обзор (заполненный: карточки + текст + разделители) ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_title_text(
            slide, "Обзор", top=Inches(0.2), font_size=26, bold=True, color=DARK_BLUE
        )

        # accent header bar
        bar = slide.shapes.add_shape(1, Inches(0.5), Inches(0.85), Inches(12.3), Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = DARK_BLUE
        bar.line.fill.background()

        # main overview text (card-like)
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.1), Inches(12.3), Inches(3.5))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = narrative.overview
        p.font.size = Pt(13)
        p.font.name = "Arial"
        p.font.color.rgb = GRAY

        # simple metric cards row (из первого результата если есть)
        if results and results[0].data:
            try:
                first_data = results[0].data
                total_acc = sum(d.get("accrued", 0) for d in first_data[:5])
                card1 = slide.shapes.add_textbox(Inches(0.5), Inches(4.8), Inches(3.8), Inches(1.3))
                ctf = card1.text_frame
                cp = ctf.paragraphs[0]
                cp.text = "Объём начислений (выборка)"
                cp.font.size = Pt(10)
                cp.font.bold = True
                cp.font.name = "Arial"
                cp.font.color.rgb = DARK_BLUE
                cp = ctf.add_paragraph()
                cp.text = format_number_ru(total_acc, suffix="Br")
                cp.font.size = Pt(16)
                cp.font.bold = True
                cp.font.name = "Arial"
            except Exception:
                pass

        # divider line
        div = slide.shapes.add_shape(1, Inches(0.5), Inches(6.3), Inches(12.3), Inches(0.02))
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(200, 200, 200)
        div.line.fill.background()

        # footer
        self._add_centered_text(
            slide,
            "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
            top=Inches(7.0),
            font_size=9,
            color=FOOTER_COLOR,
        )

        # === 5. Темы и повестка ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_title_text(
            slide, "Темы и повестка", top=Inches(0.3), font_size=28, bold=True, color=DARK_BLUE
        )
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.3), Inches(5.0))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "Ключевые темы:"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.name = "Arial"
        for th in narrative.themes:
            p = tf.add_paragraph()
            p.text = f"• {th}"
            p.font.size = Pt(13)
            p.font.name = "Arial"
            p.space_before = Pt(4)
        p = tf.add_paragraph()
        p.text = ""
        p = tf.add_paragraph()
        p.text = "Рассматриваемые вопросы:"
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.name = "Arial"
        for q in questions:
            p = tf.add_paragraph()
            p.text = f"• {q}"
            p.font.size = Pt(12)
            p.font.name = "Arial"
        self._add_centered_text(
            slide,
            "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
            top=Inches(7.0),
            font_size=10,
            color=FOOTER_COLOR,
        )

        slide_png_paths: list[str] = []

        # === 6. По слайду на вопрос (корпоративный layout 65/35 + sidebar card) ===
        usable_w = SLIDE_WIDTH_IN - 2 * SLIDE_MARGIN_H_IN
        chart_panel_w = usable_w * 0.65
        text_panel_w = usable_w * 0.35

        for idx, (q, res) in enumerate(zip(questions, results)):  # noqa: B905
            slide = prs.slides.add_slide(blank_layout)

            header = q
            subtitle_q: str | None = None
            if res.chart_spec:
                spec = res.chart_spec
                if getattr(spec, "action_title", None):
                    header = spec.action_title
                    subtitle_q = q
                elif getattr(spec, "title", None):
                    header = spec.title
            self._add_question_slide_header(slide, header, subtitle=subtitle_q)

            graph_added = False
            if res.chart_spec and res.data:
                try:
                    df = pd.DataFrame(res.data)
                    slide_spec = res.chart_spec.model_copy()
                    user_pref = prefs.get(idx)
                    if user_pref:
                        slide_spec.chart_type = user_pref
                    slide_spec.title = ""
                    fig = build_chart(df, slide_spec)
                    with suppress(Exception):
                        fig.update_layout(title=dict(text=""))
                    try:
                        if getattr(fig.layout, "annotations", None):
                            fig.layout.annotations = [
                                a
                                for a in (fig.layout.annotations or [])
                                if "Синтетические" not in str(getattr(a, "text", "") or "")
                                and "Источник" not in str(getattr(a, "text", "") or "")
                            ]
                    except Exception:
                        pass
                    slide_png = out_dir / f"pres_slide_{presentation_id}_{idx}_{self._slug(header)}.png"
                    export_png(fig, slide_png, scale=2.0)
                    slide_png_paths.append(str(slide_png.resolve()))
                    slide.shapes.add_picture(
                        str(slide_png),
                        Inches(SLIDE_MARGIN_H_IN),
                        Inches(SLIDE_CONTENT_TOP_IN),
                        width=Inches(chart_panel_w),
                    )
                    graph_added = True
                except Exception as e:
                    logger.info(f"[PresentationAgent] slide_graph_error: {e}")

            if graph_added:
                card_left = SLIDE_MARGIN_H_IN + chart_panel_w + SLIDE_CONTENT_GAP_IN
                card_width = text_panel_w - SLIDE_CONTENT_GAP_IN
            else:
                card_left = SLIDE_MARGIN_H_IN
                card_width = usable_w

            self._add_insights_sidebar_card(
                slide,
                left_in=card_left,
                top_in=SLIDE_CONTENT_TOP_IN,
                width_in=card_width,
                height_in=SLIDE_CONTENT_HEIGHT_IN,
                res=res,
                chart_pref=prefs.get(idx),
            )

            slide_num = len(prs.slides)
            self._add_centered_text(
                slide,
                f"Источник: Синтетические данные (демо), Республика Беларусь | prototip | слайд {slide_num}",
                top=Inches(7.0),
                font_size=9,
                color=FOOTER_COLOR,
            )

        # === 7. Ключевые выводы ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_title_text(
            slide, "Ключевые выводы", top=Inches(0.3), font_size=28, bold=True, color=DARK_BLUE
        )
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.3), Inches(5.0))
        tf = txBox.text_frame
        tf.word_wrap = True
        for i, t in enumerate(narrative.key_takeaways):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"• {t}"
            p.font.size = Pt(14)
            p.font.name = "Arial"
            p.space_before = Pt(6)
        self._add_centered_text(
            slide,
            "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
            top=Inches(7.0),
            font_size=10,
            color=FOOTER_COLOR,
        )

        # === 8. Рекомендации (карточки + нумерация + разделители) — conditional ===
        if include_recommendations:
            slide = prs.slides.add_slide(blank_layout)
            self._add_title_text(
                slide, "Рекомендации", top=Inches(0.2), font_size=26, bold=True, color=DARK_BLUE
            )

            # accent bar
            bar = slide.shapes.add_shape(1, Inches(0.5), Inches(0.85), Inches(12.3), Inches(0.08))
            bar.fill.solid()
            bar.fill.fore_color.rgb = DARK_BLUE
            bar.line.fill.background()

            # cards for each rec
            y_pos = 1.1
            for i, r in enumerate(narrative.recommendations, 1):
                # card bg
                card = slide.shapes.add_shape(
                    1, Inches(0.5), Inches(y_pos), Inches(12.3), Inches(1.1)
                )
                card.fill.solid()
                card.fill.fore_color.rgb = RGBColor(240, 245, 250)
                card.line.color.rgb = RGBColor(200, 210, 220)

                # number + text
                tbox = slide.shapes.add_textbox(
                    Inches(0.7), Inches(y_pos + 0.15), Inches(11.9), Inches(0.9)
                )
                ttf = tbox.text_frame
                ttf.word_wrap = True
                tp = ttf.paragraphs[0]
                tp.text = f"{i}. {r}"
                tp.font.size = Pt(13)
                tp.font.name = "Arial"
                tp.font.color.rgb = GRAY

                y_pos += 1.25

            # footer
            self._add_centered_text(
                slide,
                "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
                top=Inches(7.0),
                font_size=9,
                color=FOOTER_COLOR,
            )

        # === exact/ideal slide count (PLAN A.3/B) + appendix: размещаем ПОСЛЕ всех fixed (title/ov/themes/q/key/recs conditional)
        # чтобы appendix заполнял до target, не ломая структуру
        current = len(prs.slides)
        target = num_slides if (num_slides is not None and num_slides > 0) else current
        if current < target:
            for _ in range(target - current):
                slide = prs.slides.add_slide(blank_layout)
                self._add_title_text(
                    slide, "Приложение", top=Inches(0.3), font_size=26, bold=True, color=DARK_BLUE
                )
                txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.2), Inches(12.3), Inches(5))
                tf = txBox.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                p.text = "Дополнительные материалы и диаграммы (см. основные слайды выше)."
                p.font.size = Pt(14)
                p.font.name = "Arial"
                p.font.color.rgb = GRAY
                p = tf.add_paragraph()
                p.text = "Презентация сгенерирована с учётом запрошенного числа слайдов."
                p.font.size = Pt(12)
                p.font.name = "Arial"
                self._add_centered_text(
                    slide,
                    f"Источник: Синтетические данные (демо), Республика Беларусь | prototip | слайд {len(prs.slides)}",
                    top=Inches(7.0),
                    font_size=9,
                    color=FOOTER_COLOR,
                )

        prs.save(str(pptx_path))
        elapsed = int((time.time() - start) * 1000)
        logger.info(
            f"[PresentationAgent] end: pptx={pptx_path} slides={len(prs.slides)} ({elapsed}ms)"
        )
        # Минимальное заполнение reasoning (презентация — композитный агент)
        pres_reasoning = f"Собрано {len(prs.slides)} слайдов из {len(questions)} вопросов. Нарратив + графики (PNG via viz) + DeckNarrative."
        emit_pipeline_stage(
            "viz",
            "done",
            f"Презентация: {len(prs.slides)} слайдов, {len(slide_png_paths)} превью",
            agent="presentation_agent",
        )
        return PresentationResult(
            pptx_path=str(pptx_path),
            num_slides=len(prs.slides),
            slide_png_paths=slide_png_paths,
            presentation_id=presentation_id,
            reasoning=pres_reasoning,
        )

    def _add_question_slide_header(self, slide, title: str, subtitle: str | None = None) -> None:
        """Заголовок слайда: Pt 28, слева + опциональный подзаголовок (вопрос) + акцентная линия."""
        self._add_title_text(
            slide,
            title,
            top=Inches(0.28),
            font_size=28,
            bold=True,
            color=DARK_BLUE,
        )
        accent_top = 0.82
        if subtitle:
            sub_box = slide.shapes.add_textbox(
                Inches(SLIDE_MARGIN_H_IN),
                Inches(0.72),
                Inches(SLIDE_WIDTH_IN - 2 * SLIDE_MARGIN_H_IN),
                Inches(0.35),
            )
            sub_tf = sub_box.text_frame
            sub_tf.word_wrap = True
            sub_p = sub_tf.paragraphs[0]
            sub_p.text = subtitle
            sub_p.font.size = Pt(14)
            sub_p.font.name = "Arial"
            sub_p.font.color.rgb = GRAY
            accent_top = 1.02

        accent = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(SLIDE_MARGIN_H_IN),
            Inches(accent_top),
            Inches(SLIDE_WIDTH_IN - 2 * SLIDE_MARGIN_H_IN),
            Inches(0.03),
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = DARK_BLUE
        accent.line.fill.background()

    def _add_insights_sidebar_card(
        self,
        slide,
        *,
        left_in: float,
        top_in: float,
        width_in: float,
        height_in: float,
        res: AskResult,
        chart_pref: str | None,
    ) -> None:
        """Информационная карточка справа: фон + инсайты и выводы."""
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(left_in),
            Inches(top_in),
            Inches(width_in),
            Inches(height_in),
        )
        card.fill.solid()
        card.fill.fore_color.rgb = CARD_BG
        card.line.fill.background()

        pad = 0.2
        tx_box = slide.shapes.add_textbox(
            Inches(left_in + pad),
            Inches(top_in + pad),
            Inches(max(0.5, width_in - 2 * pad)),
            Inches(max(0.5, height_in - 2 * pad)),
        )
        tf = tx_box.text_frame
        tf.word_wrap = True

        if res.analysis:
            p = tf.paragraphs[0]
            p.text = "Инсайты"
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.name = "Arial"
            p.font.color.rgb = DARK_BLUE
            for insight in (res.analysis.insights or [])[:3]:
                p = tf.add_paragraph()
                p.text = f"• {insight}"
                p.font.size = Pt(12)
                p.font.name = "Arial"
                p.font.color.rgb = BODY_GRAY
                p.space_before = Pt(6)
                p.line_spacing = 1.15

            p = tf.add_paragraph()
            p.text = ""
            p = tf.add_paragraph()
            p.text = "Ключевой вывод"
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.name = "Arial"
            p.font.color.rgb = DARK_BLUE
            p.space_before = Pt(10)
            p = tf.add_paragraph()
            p.text = res.analysis.key_conclusion or ""
            p.font.size = Pt(11)
            p.font.name = "Arial"
            p.font.color.rgb = BODY_GRAY
            p.space_before = Pt(5)
            p.line_spacing = 1.2

            if res.analysis.anomaly_or_trend:
                p = tf.add_paragraph()
                p.text = ""
                p = tf.add_paragraph()
                p.text = "Аномалия / тренд"
                p.font.size = Pt(14)
                p.font.bold = True
                p.font.name = "Arial"
                p.font.color.rgb = DARK_BLUE
                p.space_before = Pt(10)
                p = tf.add_paragraph()
                p.text = res.analysis.anomaly_or_trend
                p.font.size = Pt(11)
                p.font.name = "Arial"
                p.font.color.rgb = BODY_GRAY
                p.space_before = Pt(5)
                p.line_spacing = 1.2

        ctype_for_ru = chart_pref or (
            getattr(res.chart_spec, "chart_type", "") if res.chart_spec else ""
        )
        ctype_ru = CHART_TYPE_RU.get(ctype_for_ru, "диаграмма")
        p = tf.add_paragraph()
        p.text = ""
        p = tf.add_paragraph()
        p.text = f"Диаграмма: {ctype_ru}"
        p.font.size = Pt(9)
        p.font.name = "Arial"
        p.font.color.rgb = FOOTER_COLOR
        p.space_before = Pt(12)
        p = tf.add_paragraph()
        p.text = "Источник: синтетические данные (демо), РБ"
        p.font.size = Pt(8)
        p.font.name = "Arial"
        p.font.color.rgb = FOOTER_COLOR

    def _add_centered_text(
        self,
        slide,
        text: str,
        top: Inches,
        font_size: int = 32,
        bold: bool = False,
        color: RGBColor = DARK_BLUE,
    ) -> None:
        """Helper: centered text box."""
        left = Inches(0.5)
        width = Inches(12.333)
        height = Inches(1.2)
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.name = "Arial"
        p.font.color.rgb = color
        p.alignment = PP_ALIGN.CENTER

    def _add_title_text(
        self,
        slide,
        text: str,
        top: Inches,
        font_size: int = 26,
        bold: bool = True,
        color: RGBColor = DARK_BLUE,
    ) -> None:
        """Helper: left-aligned title."""
        left = Inches(SLIDE_MARGIN_H_IN)
        width = Inches(SLIDE_WIDTH_IN - 2 * SLIDE_MARGIN_H_IN)
        height = Inches(0.8)
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.name = "Arial"
        p.font.color.rgb = color

    def run_input(self, inp: PresentationInput) -> PresentationResult:
        return self.run(inp.questions)
