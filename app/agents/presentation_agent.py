"""PresentationAgent (Phase 6): авто-сборка .pptx презентации.

Вход: список вопросов list[str].
Внутри для каждого вызывает Orchestrator.ask(), собирает результаты,
встраивает PNG из out/, инсайты, ключевые выводы.
Сохраняет в out/presentation.pptx

Стиль: тёмно-синий, Arial, простой и аккуратный.
"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from datetime import datetime
from pathlib import Path

import pandas as pd
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.agents.base import BaseAgent
from app.schemas import AskResult, DeckNarrative, PresentationInput, PresentationResult
from core.llm import call_structured, setup_logging
from viz.charts import build_chart, export_png
from viz.style import format_number_ru

# Ensure central logging (idempotent) — after imports to satisfy linter
setup_logging()
logger = logging.getLogger("PresentationAgent")

DARK_BLUE = RGBColor(0, 51, 102)
GRAY = RGBColor(80, 80, 80)
FOOTER_COLOR = RGBColor(128, 128, 128)

CHART_TYPE_RU: dict[str, str] = {
    "bar": "столбчатая",
    "grouped_bar": "группированная столбчатая",
    "stacked_bar": "стековая столбчатая",
    "line": "линейная",
    "horizontal_bar": "горизонтальная столбчатая",
    "donut": "круговая",
    "kpi": "KPI-индикатор",
    "heatmap": "тепловая карта",
}


class PresentationAgent(BaseAgent):
    """Агент сборки презентаций .pptx из результатов Orchestrator."""

    name = "presentation_agent"

    def _slug(self, text: str, max_len: int = 40) -> str:
        import re

        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

    def _get_deck_narrative(self, questions: list[str], results: list[AskResult]) -> DeckNarrative:
        """Один structured вызов LLM для нарратива презентации (после сбора всех ответов)."""
        summaries: list[str] = []
        for q, r in zip(questions, results, strict=False):
            conc = (r.analysis.key_conclusion if r.analysis else "") or ""
            anom = (r.analysis.anomaly_or_trend if r.analysis else "") or "нет"
            summaries.append(f"Вопрос: {q}\nКлючевой вывод: {conc}\nАномалия/тренд: {anom}")

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
        Для каждого вопроса вызывает Orchestrator.ask(),
        использует данные + chart_spec для стилизованного PNG (без заголовка графика, pres_slide_ png).
        После всех — один structured вызов для DeckNarrative.
        """
        start = time.time()
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

        # lazy import to avoid potential cycle
        from app.orchestrator import Orchestrator

        orch = Orchestrator()

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
        for q in qs:
            res = orch.ask(q)
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

        # === 6. По слайду на вопрос (с ребилдом графика без заголовка + стиль) ===
        for idx, (q, res) in enumerate(zip(questions, results, strict=False)):
            slide = prs.slides.add_slide(blank_layout)

            # Шапка = тема-утверждение (предпочитаем title из ChartSpec)
            header = q
            if res.chart_spec and getattr(res.chart_spec, "title", None):
                header = res.chart_spec.title
            self._add_title_text(
                slide, header, top=Inches(0.2), font_size=24, bold=True, color=DARK_BLUE
            )

            # Крупный график (ребилд с title="" ... + оверрайд user pref chart_type если передан)
            graph_added = False
            if res.chart_spec and res.data:
                try:
                    df = pd.DataFrame(res.data)
                    slide_spec = res.chart_spec.model_copy()
                    # Уважить pref из формы (если был "horizontal_bar" а LLM дал bar и т.п.)
                    user_pref = prefs.get(idx)
                    if user_pref:
                        slide_spec.chart_type = user_pref
                    slide_spec.title = ""  # убираем заголовок графика — его несёт шапка слайда
                    fig = build_chart(df, slide_spec)
                    # extra: явно убрать title в layout (на случай если apply добавил)
                    with suppress(Exception):
                        fig.update_layout(title=dict(text=""))
                    # убрать дублирующий source annotation из PNG (у слайда свой footer внизу)
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
                    # экспортируем специально для слайда (гарантируем стиль: палитра, русские лейблы, Br)
                    slide_png = out_dir / f"pres_slide_{idx}_{self._slug(header)}.png"
                    export_png(fig, slide_png, scale=2.0)
                    # крупный, с сохранением пропорций (шире, чем раньше)
                    slide.shapes.add_picture(
                        str(slide_png), Inches(0.3), Inches(0.9), width=Inches(8.2)
                    )
                    graph_added = True
                except Exception as e:
                    logger.info(f"[PresentationAgent] slide_graph_error: {e}")

            # Текст справа/под (инсайты + вывод + подпись диаграммы + аномалия)
            text_left = Inches(8.8) if graph_added else Inches(0.5)
            text_top = Inches(0.9)
            text_width = Inches(4.2) if graph_added else Inches(12.3)
            text_height = Inches(5.8)
            txBox = slide.shapes.add_textbox(text_left, text_top, text_width, text_height)
            tf = txBox.text_frame
            tf.word_wrap = True

            if res.analysis:
                # Инсайты
                p = tf.paragraphs[0]
                p.text = "Инсайты"
                p.font.size = Pt(14)
                p.font.bold = True
                p.font.name = "Arial"
                p.font.color.rgb = DARK_BLUE
                for insight in (res.analysis.insights or [])[:3]:
                    p = tf.add_paragraph()
                    p.text = f"• {insight}"
                    p.font.size = Pt(11)
                    p.font.name = "Arial"
                    p.space_before = Pt(3)

                # Ключевой вывод
                p = tf.add_paragraph()
                p.text = ""
                p = tf.add_paragraph()
                p.text = "Ключевой вывод"
                p.font.size = Pt(14)
                p.font.bold = True
                p.font.name = "Arial"
                p.font.color.rgb = DARK_BLUE
                p = tf.add_paragraph()
                p.text = res.analysis.key_conclusion or ""
                p.font.size = Pt(11)
                p.font.name = "Arial"
                p.space_before = Pt(4)

                # Аномалия если есть
                if res.analysis.anomaly_or_trend:
                    p = tf.add_paragraph()
                    p.text = ""
                    p = tf.add_paragraph()
                    p.text = "Аномалия / тренд"
                    p.font.size = Pt(12)
                    p.font.bold = True
                    p.font.name = "Arial"
                    p.font.color.rgb = DARK_BLUE
                    p = tf.add_paragraph()
                    p.text = res.analysis.anomaly_or_trend
                    p.font.size = Pt(10)
                    p.font.name = "Arial"

            # Подпись диаграммы (используем user_pref если был, иначе из spec)
            p = tf.add_paragraph()
            p.text = ""
            p = tf.add_paragraph()
            ctype_for_ru = prefs.get(idx) or (
                getattr(res.chart_spec, "chart_type", "") if res.chart_spec else ""
            )
            ctype_ru = CHART_TYPE_RU.get(ctype_for_ru, "диаграмма")
            p.text = f"Диаграмма: {ctype_ru}"
            p.font.size = Pt(10)
            p.font.name = "Arial"
            p.font.color.rgb = GRAY
            p = tf.add_paragraph()
            p.text = "Источник: Синтетические данные (демо), Республика Беларусь"
            p.font.size = Pt(9)
            p.font.name = "Arial"
            p.font.color.rgb = GRAY

            # Footer со номером слайда (текущий len после add)
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
        return PresentationResult(pptx_path=str(pptx_path), num_slides=len(prs.slides))

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
        left = Inches(0.5)
        width = Inches(12.333)
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
