"""PresentationAgent (Phase 6): авто-сборка .pptx презентации.

Вход: список вопросов list[str].
Внутри для каждого вызывает Orchestrator.ask(), собирает результаты,
встраивает PNG из out/, инсайты, ключевые выводы.
Сохраняет в out/presentation.pptx

Стиль: тёмно-синий, Arial, простой и аккуратный.
"""

from __future__ import annotations

import contextlib
import logging
import time
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.agents.base import BaseAgent
from app.schemas import PresentationInput, PresentationResult
from core.llm import setup_logging

# Ensure central logging (idempotent) — after imports to satisfy linter
setup_logging()
logger = logging.getLogger("PresentationAgent")

DARK_BLUE = RGBColor(0, 51, 102)
GRAY = RGBColor(80, 80, 80)
FOOTER_COLOR = RGBColor(128, 128, 128)


class PresentationAgent(BaseAgent):
    """Агент сборки презентаций .pptx из результатов Orchestrator."""

    name = "presentation_agent"

    def run(self, questions: list[str]) -> PresentationResult:
        """Собрать презентацию по списку вопросов.

        Для каждого вопроса вызывает Orchestrator.ask(),
        использует png_path, analysis.insights[:3], analysis.key_conclusion.
        """
        start = time.time()
        logger.info(f"[PresentationAgent] start: questions={len(questions)}")
        if not questions:
            raise ValueError("questions не может быть пустым")

        # lazy import to avoid potential cycle with Orchestrator
        from app.orchestrator import Orchestrator

        orch = Orchestrator()

        out_dir = Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = out_dir / "presentation.pptx"

        prs = Presentation()
        # 16:9 widescreen
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        blank_layout = prs.slide_layouts[6]  # blank

        # === Title slide ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_centered_text(
            slide,
            "BI-аналитика налогов РБ",
            top=Inches(2.5),
            font_size=44,
            bold=True,
            color=DARK_BLUE,
        )
        self._add_centered_text(
            slide,
            "Синтетические данные (демо), Республика Беларусь",
            top=Inches(4.2),
            font_size=24,
            color=GRAY,
        )

        # === Per-question slides ===
        for q in questions:
            res = orch.ask(q)
            slide = prs.slides.add_slide(blank_layout)

            # Question as title
            self._add_title_text(
                slide, q, top=Inches(0.3), font_size=26, bold=True, color=DARK_BLUE
            )

            # PNG image (left side)
            if res.png_path and Path(res.png_path).exists():
                with contextlib.suppress(Exception):
                    # image load failure shouldn't break the deck
                    slide.shapes.add_picture(
                        str(res.png_path), Inches(0.5), Inches(1.2), width=Inches(7.5)
                    )

            # Right side: insights + conclusion
            if res.analysis:
                text_left = Inches(8.3)
                text_top = Inches(1.2)
                text_width = Inches(4.7)
                text_height = Inches(5.5)
                txBox = slide.shapes.add_textbox(text_left, text_top, text_width, text_height)
                tf = txBox.text_frame
                tf.word_wrap = True

                # Insights header
                p = tf.paragraphs[0]
                p.text = "Инсайты"
                p.font.size = Pt(16)
                p.font.bold = True
                p.font.name = "Arial"
                p.font.color.rgb = DARK_BLUE

                for insight in (res.analysis.insights or [])[:3]:
                    p = tf.add_paragraph()
                    p.text = f"• {insight}"
                    p.font.size = Pt(12)
                    p.font.name = "Arial"
                    p.space_before = Pt(6)

                # Key conclusion
                p = tf.add_paragraph()
                p.text = ""
                p = tf.add_paragraph()
                p.text = "Ключевой вывод"
                p.font.size = Pt(16)
                p.font.bold = True
                p.font.name = "Arial"
                p.font.color.rgb = DARK_BLUE

                p = tf.add_paragraph()
                p.text = res.analysis.key_conclusion or ""
                p.font.size = Pt(12)
                p.font.name = "Arial"
                p.space_before = Pt(6)

            # Footer
            self._add_centered_text(
                slide,
                "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
                top=Inches(7.1),
                font_size=10,
                color=FOOTER_COLOR,
            )

        # === Final "Общие выводы" slide ===
        slide = prs.slides.add_slide(blank_layout)
        self._add_centered_text(
            slide, "Общие выводы", top=Inches(2.5), font_size=40, bold=True, color=DARK_BLUE
        )
        self._add_centered_text(
            slide,
            "Презентация собрана автоматически.\n\nСм. предыдущие слайды для детальных результатов по каждому вопросу.",
            top=Inches(4),
            font_size=18,
            color=GRAY,
        )
        self._add_centered_text(
            slide,
            "Источник: Синтетические данные (демо), Республика Беларусь | prototip",
            top=Inches(7.1),
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
