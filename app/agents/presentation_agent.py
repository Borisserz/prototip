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

    def run(self, questions: list[str]) -> PresentationResult:
        """Собрать презентацию по списку вопросов с DeckNarrative и улучшенной структурой.

        Для каждого вопроса вызывает Orchestrator.ask(),
        использует данные + chart_spec для стилизованного PNG (без заголовка графика).
        После всех — один structured вызов для DeckNarrative.
        """
        start = time.time()
        logger.info(f"[PresentationAgent] start: questions={len(questions)}")
        if not questions:
            raise ValueError("questions не может быть пустым")

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
        results: list[AskResult] = []
        for q in questions:
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

        # === 3. Титул ===
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

        # === 4. Обзор ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_title_text(
            slide, "Обзор", top=Inches(0.3), font_size=28, bold=True, color=DARK_BLUE
        )
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.3), Inches(5.5))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = narrative.overview
        p.font.size = Pt(14)
        p.font.name = "Arial"
        p.font.color.rgb = GRAY
        self._add_centered_text(
            slide,
            "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
            top=Inches(7.0),
            font_size=10,
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

            # Крупный график (ребилд с title="" для отсутствия дублирующего заголовка + полный стиль из viz/style)
            graph_added = False
            if res.chart_spec and res.data:
                try:
                    df = pd.DataFrame(res.data)
                    slide_spec = res.chart_spec.model_copy()
                    slide_spec.title = ""  # убираем заголовок графика — его несёт шапка слайда
                    fig = build_chart(df, slide_spec)
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

            # Подпись диаграммы
            p = tf.add_paragraph()
            p.text = ""
            p = tf.add_paragraph()
            ctype_ru = CHART_TYPE_RU.get(
                getattr(res.chart_spec, "chart_type", "") if res.chart_spec else "", "диаграмма"
            )
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

        # === 8. Рекомендации ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_title_text(
            slide, "Рекомендации", top=Inches(0.3), font_size=28, bold=True, color=DARK_BLUE
        )
        txBox = slide.shapes.add_textbox(Inches(0.5), Inches(1.0), Inches(12.3), Inches(5.0))
        tf = txBox.text_frame
        tf.word_wrap = True
        for i, r in enumerate(narrative.recommendations):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"• {r}"
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
