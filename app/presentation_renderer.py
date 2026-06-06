"""Программная верстка презентаций (python-pptx, без master templates)."""

from __future__ import annotations

import enum
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from app.agents.models import AskResult
from app.kpi_utils import compute_overview_kpis
from core.models import ChartSpec
from viz.style import format_number_ru, get_russian_label

FOOTER_TEXT = "Источник: Синтетические данные (демо), Республика Беларусь | prototip"
BADGE_TEXT = "ДЛЯ СЛУЖЕБНОГО ПОЛЬЗОВАНИЯ | AI DRAFT"

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


class LayoutKind(enum.StrEnum):
    TOP_BOTTOM = "top_bottom"
    SIDE_BY_SIDE = "side_by_side"
    CHART_TABLE = "chart_table"
    KPI_FULL = "kpi_full"


class PresentationTheme:
    DARK_BLUE = RGBColor(0, 51, 102)
    ACCENT_BLUE = RGBColor(0, 102, 153)
    WHITE = RGBColor(255, 255, 255)
    BG_LIGHT = RGBColor(245, 247, 250)
    GRAY = RGBColor(80, 80, 80)
    BODY_GRAY = RGBColor(60, 60, 60)
    FOOTER_COLOR = RGBColor(128, 128, 128)
    TABLE_ROW_ALT = RGBColor(242, 244, 247)
    TABLE_ROW_WHITE = RGBColor(255, 255, 255)
    BADGE_BG = RGBColor(235, 235, 235)
    BADGE_TEXT = RGBColor(140, 30, 30)
    CARD_BORDER = RGBColor(200, 210, 220)
    DIVIDER = RGBColor(200, 200, 200)

    SLIDE_W = 13.333
    SLIDE_H = 7.5
    MARGIN_H = 0.45
    USABLE_W = 12.433
    CONTENT_TOP = 1.15
    CONTENT_HEIGHT = 5.40
    FOOTER_TOP = 7.0
    GAP = 0.15
    PANEL_GAP = 0.20

    FONT = "Arial"


class PresentationRenderer:
    """Единая точка программной отрисовки слайдов."""

    def __init__(self, *, theme: type[PresentationTheme] = PresentationTheme) -> None:
        self.t = theme

    # ------------------------------------------------------------------ utils
    @staticmethod
    def choose_layout(chart_type: str | None) -> LayoutKind:
        ct = chart_type or "bar"
        if ct in {"line", "area", "waterfall", "heatmap"}:
            return LayoutKind.TOP_BOTTOM
        if ct in {"donut", "treemap"}:
            return LayoutKind.SIDE_BY_SIDE
        if ct in {"bar", "horizontal_bar"}:
            return LayoutKind.CHART_TABLE
        if ct == "kpi":
            return LayoutKind.KPI_FULL
        return LayoutKind.TOP_BOTTOM

    @staticmethod
    def truncate_text(text: str, max_chars: int = 120) -> str:
        text = (text or "").strip()
        if len(text) <= max_chars:
            return text
        return text[: max_chars - 3] + "..."

    def _bullet_font_size(self, texts: list[str], base: int = 14) -> int:
        total = sum(len(t) for t in texts)
        if total > 500:
            return 11
        if total > 350:
            return 12
        return base

    def _resolve_headers(self, question: str, res: AskResult) -> tuple[str, str | None]:
        spec = res.chart_spec
        if spec and getattr(spec, "action_title", None):
            return self.truncate_text(spec.action_title, 80), question
        if spec and getattr(spec, "title", None):
            return self.truncate_text(spec.title, 80), question
        return self.truncate_text(question, 80), None

    # ------------------------------------------------------------------ primitives
    def _add_gov_badge(self, slide: Any) -> None:
        shape = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(10.55),
            Inches(0.12),
            Inches(2.35),
            Inches(0.38),
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = self.t.BADGE_BG
        shape.line.color.rgb = self.t.CARD_BORDER
        tf = shape.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.text = BADGE_TEXT
        p.font.size = Pt(7)
        p.font.name = self.t.FONT
        p.font.color.rgb = self.t.BADGE_TEXT
        p.alignment = PP_ALIGN.CENTER

    def _add_footer(self, slide: Any, *, slide_num: int | None = None) -> None:
        text = FOOTER_TEXT if slide_num is None else f"{FOOTER_TEXT} | слайд {slide_num}"
        self._add_centered_text(slide, text, top=Inches(self.t.FOOTER_TOP), font_size=9, color=self.t.FOOTER_COLOR)

    def _add_centered_text(
        self,
        slide: Any,
        text: str,
        *,
        top: Inches,
        font_size: int = 32,
        bold: bool = False,
        color: RGBColor | None = None,
    ) -> None:
        tx = slide.shapes.add_textbox(Inches(0.5), top, Inches(12.333), Inches(1.2))
        p = tx.text_frame.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.name = self.t.FONT
        p.font.color.rgb = color or self.t.DARK_BLUE
        p.alignment = PP_ALIGN.CENTER

    def _add_title_text(
        self,
        slide: Any,
        text: str,
        *,
        top: float,
        font_size: int = 26,
        bold: bool = True,
        color: RGBColor | None = None,
        left: float | None = None,
        width: float | None = None,
    ) -> None:
        tx = slide.shapes.add_textbox(
            Inches(left or self.t.MARGIN_H),
            Inches(top),
            Inches(width or self.t.USABLE_W),
            Inches(0.8),
        )
        p = tx.text_frame.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.bold = bold
        p.font.name = self.t.FONT
        p.font.color.rgb = color or self.t.DARK_BLUE

    def render_slide_header(self, slide: Any, title: str, subtitle: str | None = None) -> None:
        title = self.truncate_text(title, 80)
        font_size = 24 if len(title) > 60 else 28
        self._add_title_text(slide, title, top=0.28, font_size=font_size)
        accent_top = 0.82
        if subtitle:
            sub = slide.shapes.add_textbox(
                Inches(self.t.MARGIN_H), Inches(0.72), Inches(self.t.USABLE_W), Inches(0.35)
            )
            sub_tf = sub.text_frame
            sub_tf.word_wrap = True
            sub_p = sub_tf.paragraphs[0]
            sub_p.text = self.truncate_text(subtitle, 120)
            sub_p.font.size = Pt(14)
            sub_p.font.name = self.t.FONT
            sub_p.font.color.rgb = self.t.GRAY
            accent_top = 1.02
        accent = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE,
            Inches(self.t.MARGIN_H),
            Inches(accent_top),
            Inches(self.t.USABLE_W),
            Inches(0.03),
        )
        accent.fill.solid()
        accent.fill.fore_color.rgb = self.t.DARK_BLUE
        accent.line.fill.background()

    def _place_chart_image(
        self, slide: Any, png_path: str | Path, *, left: float, top: float, width: float, height: float
    ) -> None:
        path = Path(png_path)
        if path.exists():
            slide.shapes.add_picture(str(path), Inches(left), Inches(top), width=Inches(width), height=Inches(height))

    def _draw_kpi_card(
        self, slide: Any, left: float, top: float, width: float, height: float, title: str, value: str
    ) -> None:
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = self.t.BG_LIGHT
        card.line.color.rgb = self.t.CARD_BORDER
        card.line.width = Pt(0.75)
        pad = 0.12
        tx = slide.shapes.add_textbox(
            Inches(left + pad), Inches(top + pad), Inches(width - 2 * pad), Inches(height - 2 * pad)
        )
        tf = tx.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(10)
        p.font.name = self.t.FONT
        p.font.color.rgb = self.t.GRAY
        p2 = tf.add_paragraph()
        p2.text = value
        p2.font.size = Pt(20)
        p2.font.bold = True
        p2.font.name = self.t.FONT
        p2.font.color.rgb = self.t.DARK_BLUE
        p2.space_before = Pt(4)

    def _style_table_cell(
        self,
        cell: Any,
        text: str,
        *,
        bold: bool = False,
        font_size: int = 11,
        fill: RGBColor | None = None,
        font_color: RGBColor | None = None,
    ) -> None:
        cell.text = text
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill or self.t.TABLE_ROW_WHITE
        for paragraph in cell.text_frame.paragraphs:
            paragraph.font.size = Pt(font_size)
            paragraph.font.bold = bold
            paragraph.font.name = self.t.FONT
            paragraph.font.color.rgb = font_color or self.t.BODY_GRAY

    def _build_ranking_table_rows(self, res: AskResult, spec: ChartSpec) -> list[tuple[str, str]]:
        if not res.data or spec.x not in (res.data[0] if res.data else {}):
            return []
        try:
            df = pd.DataFrame(res.data)
            if spec.y not in df.columns:
                return []
            agg = spec.agg or "sum"
            if agg == "sum":
                g = df.groupby(spec.x, as_index=False)[spec.y].sum()
            elif agg == "mean":
                g = df.groupby(spec.x, as_index=False)[spec.y].mean()
            else:
                g = df.groupby(spec.x, as_index=False)[spec.y].sum()
            g = g.sort_values(spec.y, ascending=False).head(5)
            suffix = "Br" if any(k in spec.y.lower() for k in ("debt", "accrued", "paid", "penalt")) else ""
            return [
                (str(row[spec.x]), format_number_ru(float(row[spec.y]), suffix=suffix))
                for _, row in g.iterrows()
            ]
        except Exception:
            return []

    def _render_ranking_table(
        self, slide: Any, res: AskResult, spec: ChartSpec, *, left: float, top: float, width: float
    ) -> None:
        rows_data = self._build_ranking_table_rows(res, spec)
        if not rows_data:
            return
        n_rows = min(6, len(rows_data) + 1)
        table_shape = slide.shapes.add_table(n_rows, 2, Inches(left), Inches(top), Inches(width), Inches(2.85))
        table = table_shape.table
        table.columns[0].width = Inches(width * 0.55)
        table.columns[1].width = Inches(width * 0.45)
        cat_label = get_russian_label(spec.x).split(",")[0]
        val_label = get_russian_label(spec.y).split(",")[0]
        self._style_table_cell(
            table.cell(0, 0), cat_label, bold=True, fill=self.t.DARK_BLUE, font_color=self.t.WHITE
        )
        self._style_table_cell(
            table.cell(0, 1), f"{val_label}, Br", bold=True, fill=self.t.DARK_BLUE, font_color=self.t.WHITE
        )
        for i, (cat, val) in enumerate(rows_data[:5], start=1):
            fill = self.t.TABLE_ROW_ALT if i % 2 == 0 else self.t.TABLE_ROW_WHITE
            self._style_table_cell(table.cell(i, 0), self.truncate_text(cat, 40), fill=fill)
            self._style_table_cell(table.cell(i, 1), val, fill=fill)

    def _add_insights_block(
        self,
        slide: Any,
        res: AskResult,
        *,
        left: float,
        top: float,
        width: float,
        height: float,
        chart_pref: str | None = None,
        columns: int = 1,
    ) -> None:
        card = slide.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = self.t.BG_LIGHT
        card.line.fill.background()
        pad = 0.15
        if columns == 1:
            self._fill_insights_textbox(
                slide,
                left + pad,
                top + pad,
                width - 2 * pad,
                height - 2 * pad,
                res,
                chart_pref,
            )
        else:
            col_w = (width - 2 * pad - (columns - 1) * 0.2) / columns
            insights = (res.analysis.insights or [])[:3] if res.analysis else []
            for ci in range(columns):
                texts = [insights[ci]] if ci < len(insights) else []
                if ci == columns - 1 and res.analysis and res.analysis.key_conclusion:
                    texts.append(res.analysis.key_conclusion)
                self._fill_insights_textbox(
                    slide,
                    left + pad + ci * (col_w + 0.2),
                    top + pad,
                    col_w,
                    height - 2 * pad,
                    res,
                    chart_pref,
                    override_texts=texts if texts else None,
                    compact=True,
                )

    def _fill_insights_textbox(
        self,
        slide: Any,
        left: float,
        top: float,
        width: float,
        height: float,
        res: AskResult,
        chart_pref: str | None,
        *,
        override_texts: list[str] | None = None,
        compact: bool = False,
    ) -> None:
        tx = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = tx.text_frame
        tf.word_wrap = True
        if not res.analysis:
            return
        insights = override_texts or [self.truncate_text(i) for i in (res.analysis.insights or [])[:3]]
        font_size = self._bullet_font_size(
            insights + [res.analysis.key_conclusion or ""], base=12 if compact else 14
        )
        first = True
        if not compact:
            p = tf.paragraphs[0]
            p.text = "Инсайты"
            p.font.size = Pt(14)
            p.font.bold = True
            p.font.name = self.t.FONT
            p.font.color.rgb = self.t.DARK_BLUE
            first = False
        for insight in insights:
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.text = f"• {insight}"
            p.font.size = Pt(font_size)
            p.font.name = self.t.FONT
            p.font.color.rgb = self.t.BODY_GRAY
            p.space_before = Pt(4)
        if not compact and res.analysis.key_conclusion:
            p = tf.add_paragraph()
            p.text = "Ключевой вывод"
            p.font.size = Pt(13)
            p.font.bold = True
            p.font.name = self.t.FONT
            p.font.color.rgb = self.t.DARK_BLUE
            p.space_before = Pt(8)
            p2 = tf.add_paragraph()
            p2.text = self.truncate_text(res.analysis.key_conclusion)
            p2.font.size = Pt(max(10, font_size - 1))
            p2.font.name = self.t.FONT
            p2.font.color.rgb = self.t.BODY_GRAY
        if not compact:
            ctype = chart_pref or (getattr(res.chart_spec, "chart_type", "") if res.chart_spec else "")
            p3 = tf.add_paragraph()
            p3.text = f"Диаграмма: {CHART_TYPE_RU.get(ctype, 'диаграмма')}"
            p3.font.size = Pt(8)
            p3.font.color.rgb = self.t.FOOTER_COLOR

    # ------------------------------------------------------------------ layouts
    def _render_top_bottom_layout(
        self, slide: Any, res: AskResult, png_path: str | None, chart_pref: str | None
    ) -> None:
        m = self.t.MARGIN_H
        if png_path:
            self._place_chart_image(slide, png_path, left=m, top=self.t.CONTENT_TOP, width=self.t.USABLE_W, height=3.35)
        div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(m), Inches(4.58), Inches(self.t.USABLE_W), Inches(0.02))
        div.fill.solid()
        div.fill.fore_color.rgb = self.t.DIVIDER
        div.line.fill.background()
        self._add_insights_block(slide, res, left=m, top=4.75, width=self.t.USABLE_W, height=1.75, chart_pref=chart_pref, columns=3)

    def _render_side_by_side_layout(
        self, slide: Any, res: AskResult, png_path: str | None, chart_pref: str | None
    ) -> None:
        chart_w = 7.36
        text_left = 8.01
        text_w = 4.87
        if png_path:
            self._place_chart_image(
                slide, png_path, left=self.t.MARGIN_H, top=self.t.CONTENT_TOP, width=chart_w, height=self.t.CONTENT_HEIGHT
            )
        self._add_insights_block(
            slide, res, left=text_left, top=self.t.CONTENT_TOP, width=text_w, height=self.t.CONTENT_HEIGHT, chart_pref=chart_pref
        )

    def _render_chart_and_table_layout(
        self, slide: Any, res: AskResult, png_path: str | None, chart_pref: str | None
    ) -> None:
        panel_w = 6.12
        table_left = self.t.MARGIN_H + panel_w + self.t.PANEL_GAP
        if png_path:
            self._place_chart_image(
                slide, png_path, left=self.t.MARGIN_H, top=self.t.CONTENT_TOP, width=panel_w, height=self.t.CONTENT_HEIGHT
            )
        if res.chart_spec:
            self._render_ranking_table(
                slide, res, res.chart_spec, left=table_left, top=self.t.CONTENT_TOP, width=panel_w
            )
        if res.analysis and res.analysis.key_conclusion:
            tx = slide.shapes.add_textbox(Inches(table_left), Inches(4.2), Inches(panel_w), Inches(1.2))
            tf = tx.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.text = "Ключевой вывод"
            p.font.size = Pt(12)
            p.font.bold = True
            p.font.color.rgb = self.t.DARK_BLUE
            p2 = tf.add_paragraph()
            p2.text = self.truncate_text(res.analysis.key_conclusion)
            p2.font.size = Pt(11)
            p2.font.color.rgb = self.t.BODY_GRAY

    def _render_kpi_full_layout(
        self, slide: Any, res: AskResult, png_path: str | None, chart_pref: str | None
    ) -> None:
        if png_path:
            self._place_chart_image(slide, png_path, left=1.5, top=self.t.CONTENT_TOP, width=7.5, height=4.5)
        self._add_insights_block(slide, res, left=9.3, top=self.t.CONTENT_TOP, width=3.6, height=self.t.CONTENT_HEIGHT, chart_pref=chart_pref)

    # ------------------------------------------------------------------ deck slides
    def create_title_slide(self, slide: Any, *, date_str: str | None = None) -> None:
        band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(5.8), Inches(self.t.SLIDE_W), Inches(1.7))
        band.fill.solid()
        band.fill.fore_color.rgb = self.t.DARK_BLUE
        band.line.fill.background()
        accent_a = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(1.5), Inches(0.35), Inches(4.5))
        accent_a.fill.solid()
        accent_a.fill.fore_color.rgb = self.t.ACCENT_BLUE
        accent_a.line.fill.background()
        accent_b = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.35), Inches(2.2), Inches(0.25), Inches(3.2))
        accent_b.fill.solid()
        accent_b.fill.fore_color.rgb = self.t.DARK_BLUE
        accent_b.line.fill.background()
        self._add_title_text(slide, "BI-аналитика налогов РБ", top=2.0, font_size=36, left=1.0, width=11.0)
        self._add_title_text(
            slide,
            "Синтетические данные (демо), Республика Беларусь",
            top=3.0,
            font_size=18,
            bold=False,
            color=self.t.GRAY,
            left=1.0,
            width=11.0,
        )
        date_val = date_str or datetime.now().strftime("%d.%m.%Y")
        self._add_centered_text(slide, date_val, top=Inches(6.1), font_size=14, color=self.t.WHITE)
        self._add_gov_badge(slide)
        self._add_footer(slide)

    def create_summary_slide(self, slide: Any, overview: str, first_result: AskResult | None) -> None:
        self._add_title_text(slide, "Обзор", top=0.20, font_size=26)
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(self.t.MARGIN_H), Inches(0.85), Inches(self.t.USABLE_W), Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.t.DARK_BLUE
        bar.line.fill.background()
        tx = slide.shapes.add_textbox(Inches(self.t.MARGIN_H), Inches(1.10), Inches(self.t.USABLE_W), Inches(2.20))
        p = tx.text_frame.paragraphs[0]
        p.text = self.truncate_text(overview, 600)
        p.font.size = Pt(13)
        p.font.name = self.t.FONT
        p.font.color.rgb = self.t.GRAY
        tx.text_frame.word_wrap = True
        if first_result and first_result.data:
            kpis = compute_overview_kpis(first_result.data)
            card_w = (self.t.USABLE_W - 3 * self.t.GAP) / 4
            for i, (name, val) in enumerate(kpis[:4]):
                self._draw_kpi_card(
                    slide,
                    self.t.MARGIN_H + i * (card_w + self.t.GAP),
                    3.50,
                    card_w,
                    1.40,
                    name,
                    val,
                )
        self._add_gov_badge(slide)
        self._add_footer(slide)

    def create_themes_slide(self, slide: Any, themes: list[str], questions: list[str]) -> None:
        self._add_title_text(slide, "Темы и повестка", top=0.30, font_size=28)
        tx = slide.shapes.add_textbox(Inches(self.t.MARGIN_H), Inches(1.0), Inches(self.t.USABLE_W), Inches(5.0))
        tf = tx.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "Ключевые темы:"
        p.font.size = Pt(14)
        p.font.bold = True
        for th in themes:
            p = tf.add_paragraph()
            p.text = f"• {self.truncate_text(th)}"
            p.font.size = Pt(13)
        p = tf.add_paragraph()
        p.text = "Рассматриваемые вопросы:"
        p.font.size = Pt(14)
        p.font.bold = True
        p.space_before = Pt(12)
        for q in questions:
            p = tf.add_paragraph()
            p.text = f"• {self.truncate_text(q)}"
            p.font.size = Pt(12)
        self._add_gov_badge(slide)
        self._add_footer(slide)

    def render_question_slide(
        self,
        slide: Any,
        question: str,
        res: AskResult,
        chart_pref: str | None,
        png_path: str | None,
    ) -> None:
        header, subtitle = self._resolve_headers(question, res)
        self.render_slide_header(slide, header, subtitle)
        ctype = chart_pref or (getattr(res.chart_spec, "chart_type", None) if res.chart_spec else None)
        layout = self.choose_layout(ctype)
        if layout == LayoutKind.TOP_BOTTOM:
            self._render_top_bottom_layout(slide, res, png_path, chart_pref)
        elif layout == LayoutKind.SIDE_BY_SIDE:
            self._render_side_by_side_layout(slide, res, png_path, chart_pref)
        elif layout == LayoutKind.CHART_TABLE:
            self._render_chart_and_table_layout(slide, res, png_path, chart_pref)
        else:
            self._render_kpi_full_layout(slide, res, png_path, chart_pref)
        self._add_gov_badge(slide)

    def create_takeaways_slide(self, slide: Any, takeaways: list[str]) -> None:
        self._add_title_text(slide, "Ключевые выводы", top=0.30, font_size=28)
        tx = slide.shapes.add_textbox(Inches(self.t.MARGIN_H), Inches(1.0), Inches(self.t.USABLE_W), Inches(5.0))
        tf = tx.text_frame
        tf.word_wrap = True
        font_size = self._bullet_font_size(takeaways)
        for i, t in enumerate(takeaways):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"• {self.truncate_text(t)}"
            p.font.size = Pt(font_size)
            p.font.name = self.t.FONT
            p.space_before = Pt(6)
        self._add_gov_badge(slide)
        self._add_footer(slide)

    def create_recommendations_slide(self, slide: Any, recommendations: list[str]) -> None:
        self._add_title_text(slide, "Рекомендации", top=0.20, font_size=26)
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(self.t.MARGIN_H), Inches(0.85), Inches(self.t.USABLE_W), Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = self.t.DARK_BLUE
        bar.line.fill.background()
        y_pos = 1.1
        for i, rec in enumerate(recommendations, 1):
            card = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE, Inches(self.t.MARGIN_H), Inches(y_pos), Inches(self.t.USABLE_W), Inches(1.1)
            )
            card.fill.solid()
            card.fill.fore_color.rgb = RGBColor(240, 245, 250)
            card.line.color.rgb = self.t.CARD_BORDER
            tbox = slide.shapes.add_textbox(
                Inches(self.t.MARGIN_H + 0.2), Inches(y_pos + 0.15), Inches(self.t.USABLE_W - 0.4), Inches(0.9)
            )
            tbox.text_frame.word_wrap = True
            p = tbox.text_frame.paragraphs[0]
            p.text = f"{i}. {self.truncate_text(rec)}"
            p.font.size = Pt(13)
            p.font.color.rgb = self.t.GRAY
            y_pos += 1.25
        self._add_gov_badge(slide)
        self._add_footer(slide)

    def create_appendix_slide(self, slide: Any, slide_num: int) -> None:
        self._add_title_text(slide, "Приложение", top=0.30, font_size=26)
        tx = slide.shapes.add_textbox(Inches(self.t.MARGIN_H), Inches(1.2), Inches(self.t.USABLE_W), Inches(5.0))
        p = tx.text_frame.paragraphs[0]
        p.text = "Дополнительные материалы и диаграммы (см. основные слайды выше)."
        p.font.size = Pt(14)
        p.font.color.rgb = self.t.GRAY
        self._add_gov_badge(slide)
        self._add_footer(slide, slide_num=slide_num)

    def build_question_slides_footer(self, slide: Any, slide_num: int) -> None:
        self._add_footer(slide, slide_num=slide_num)