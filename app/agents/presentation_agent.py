"""PresentationAgent (Phase 6+): авто-сборка .pptx презентации.

Оркестрация: slide_pipeline (data→chart→analyst) → DeckNarrative → PresentationRenderer.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

import pandas as pd
from pptx import Presentation
from pptx.util import Inches

from app.agent_context import presentation_subplan
from app.agents.base_agent import BaseAgent
from app.agents.factory import get_executor
from app.agents.models import AskResult, DeckNarrative, PresentationInput, PresentationResult
from app.chart_repair import repair_chart_spec
from app.pipeline_progress import emit_pipeline_stage, suppress_pipeline_emit
from app.presentation_renderer import PresentationRenderer, PresentationTheme
from app.slide_pipeline import build_slide_ask_result
from core.llm import call_structured, setup_logging
from viz.charts import build_chart, export_png

setup_logging()
logger = logging.getLogger("PresentationAgent")


class PresentationAgent(BaseAgent):
    """Агент сборки презентаций .pptx из slide pipeline (без nested Planner)."""

    name = "presentation_agent"
    description = (
        "По списку вопросов собирает .pptx: slide pipeline → PNG (viz) → "
        "PresentationRenderer (динамические макеты, gov-стиль, KPI, таблицы)."
    )

    def __init__(self) -> None:
        self.renderer = PresentationRenderer()

    def _slug(self, text: str, max_len: int = 40) -> str:
        slug = re.sub(r"[^a-zA-Zа-яА-Я0-9]+", "_", text.lower()).strip("_")
        return slug[:max_len] or "result"

    def _normalize_input(
        self, questions: list[str] | list[dict] | list | PresentationInput
    ) -> tuple[list[str], dict[int, str | None], list[dict]]:
        qlist: list[dict] = []
        if isinstance(questions, PresentationInput):
            qlist = [{"text": q} for q in questions.questions]
        elif questions and isinstance(questions[0], dict):
            qlist = questions  # type: ignore[assignment]
        else:
            qlist = [{"text": q} for q in (questions or [])]
        qs = [str(q.get("text", "")).strip() for q in qlist if str(q.get("text", "")).strip()]
        prefs: dict[int, str | None] = {}
        for qb in qlist:
            if str(qb.get("text", "")).strip():
                prefs[len(prefs)] = qb.get("chart_type")
        return qs, prefs, qlist

    def _trim_for_num_slides(
        self,
        questions: list[str],
        prefs: dict[int, str | None],
        qlist: list[dict],
        *,
        num_slides: int | None,
        include_title: bool,
        include_recommendations: bool,
    ) -> tuple[list[str], dict[int, str | None]]:
        if not num_slides or num_slides <= 0:
            return questions, prefs
        base_fixed = (1 if include_title else 0) + 2 + 1 + (1 if include_recommendations else 0)
        max_q = max(0, num_slides - base_fixed)
        trimmed = questions[:max_q] if max_q > 0 else (questions[:1] if questions else [])
        new_prefs: dict[int, str | None] = {}
        uidx = 0
        for qb in qlist:
            if str(qb.get("text", "")).strip() and uidx < len(trimmed):
                new_prefs[uidx] = qb.get("chart_type")
                uidx += 1
        return trimmed, new_prefs

    def _collect_results(self, questions: list[str], executor: Any) -> list[AskResult]:
        results: list[AskResult] = []
        with presentation_subplan(), suppress_pipeline_emit():
            for qi, q in enumerate(questions):
                emit_pipeline_stage(
                    "synthesis",
                    "running",
                    f"Вопрос {qi + 1}/{len(questions)}: {str(q)[:50]}...",
                    agent="presentation_agent",
                )
                results.append(build_slide_ask_result(q, executor))
        return results

    def _get_deck_narrative(self, questions: list[str], results: list[AskResult]) -> DeckNarrative:
        summaries: list[str] = []
        for q, r in zip(questions, results):  # noqa: B905
            conc = (r.analysis.key_conclusion if r.analysis else "") or ""
            anom = (r.analysis.anomaly_or_trend if r.analysis else "") or "нет"
            action = (getattr(r.chart_spec, "action_title", None) if r.chart_spec else None) or ""
            action_line = f"Action title: {action}\n" if action else ""
            summaries.append(
                f"Вопрос: {q}\n{action_line}Ключевой вывод: {conc}\nАномалия/тренд: {anom}"
            )
        prompt = f"""Ты — старший аналитик, готовящий презентацию для руководства по налоговой статистике Республики Беларусь (синтетические данные).

Проанализируй результаты по вопросам и верни DeckNarrative строго по схеме:
- overview: 2-4 предложения (цель, охват, метод: Text-to-SQL + Analyst + Chart).
- themes: 2-4 коротких темы/повестки.
- key_takeaways: 4-6 главных выводов.
- recommendations: 2-4 конкретных рекомендаций.

Вопросы и выводы:
{chr(10).join(summaries)}

Все тексты на русском. Верни только валидный JSON по схеме DeckNarrative.
"""
        return call_structured(
            prompt,
            schema=DeckNarrative,
            system="Ты — точный аналитик презентаций. Выдавай только валидный JSON. Тексты на русском.",
        )

    def _fallback_narrative(self) -> DeckNarrative:
        return DeckNarrative(
            overview=(
                "Презентация содержит анализ налоговых поступлений Республики Беларусь "
                "по синтетическим данным за 2024 год (Text-to-SQL + анализ + визуализация)."
            ),
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

    def _export_slide_charts(
        self,
        *,
        questions: list[str],
        results: list[AskResult],
        prefs: dict[int, str | None],
        out_dir: Path,
        presentation_id: str,
    ) -> list[str | None]:
        paths: list[str | None] = []
        for idx, (q, res) in enumerate(zip(questions, results)):  # noqa: B905
            png_path: str | None = None
            if res.chart_spec and res.data:
                try:
                    df = pd.DataFrame(res.data)
                    slide_spec = res.chart_spec.model_copy()
                    user_pref = prefs.get(idx)
                    if user_pref:
                        slide_spec.chart_type = user_pref  # type: ignore[assignment]
                    slide_spec.title = ""
                    slide_spec = repair_chart_spec(slide_spec, res.data, question=q)
                    fig = build_chart(df, slide_spec)
                    with suppress(Exception):
                        fig.update_layout(title=dict(text=""))
                    header = q
                    if getattr(slide_spec, "action_title", None):
                        header = slide_spec.action_title or q
                    elif slide_spec.title:
                        header = slide_spec.title
                    slide_png = out_dir / f"pres_slide_{presentation_id}_{idx}_{self._slug(header)}.png"
                    export_png(fig, slide_png, scale=2.0)
                    png_path = str(slide_png.resolve())
                except Exception as e:
                    logger.info(f"[PresentationAgent] slide_graph_error: {e}")
            paths.append(png_path)
        return paths

    def run(
        self,
        questions: list[str] | list[dict] | list | PresentationInput,
        num_slides: int | None = None,
        include_title: bool = True,
        include_recommendations: bool = True,
    ) -> PresentationResult:
        start = time.time()
        presentation_id = uuid.uuid4().hex[:10]
        emit_pipeline_stage(
            "synthesis",
            "running",
            f"Сборка презентации ({presentation_id})...",
            agent="presentation_agent",
        )

        all_qs, prefs, qlist = self._normalize_input(questions)
        if not all_qs:
            raise ValueError("questions не может быть пустым")

        qs, prefs = self._trim_for_num_slides(
            all_qs,
            prefs,
            qlist,
            num_slides=num_slides,
            include_title=include_title,
            include_recommendations=include_recommendations,
        )
        logger.info(
            f"[PresentationAgent] start: questions={len(qs)} num_slides={num_slides} "
            f"inc_title={include_title} inc_recs={include_recommendations}"
        )

        executor = get_executor(include_planner=False)
        out_dir = Path("out")
        out_dir.mkdir(parents=True, exist_ok=True)
        pptx_path = out_dir / f"presentation_{presentation_id}.pptx"

        results = self._collect_results(qs, executor)

        try:
            narrative = self._get_deck_narrative(qs, results)
        except Exception as e:
            logger.info(f"[PresentationAgent] narrative_error_fallback: {e}")
            narrative = self._fallback_narrative()

        slide_png_paths = self._export_slide_charts(
            questions=qs,
            results=results,
            prefs=prefs,
            out_dir=out_dir,
            presentation_id=presentation_id,
        )
        png_exported = [p for p in slide_png_paths if p]

        prs = Presentation()
        prs.slide_width = Inches(PresentationTheme.SLIDE_W)
        prs.slide_height = Inches(PresentationTheme.SLIDE_H)
        blank = prs.slide_layouts[6]
        renderer = self.renderer

        if include_title:
            renderer.create_title_slide(prs.slides.add_slide(blank))
        renderer.create_summary_slide(
            prs.slides.add_slide(blank), narrative.overview, results[0] if results else None
        )
        renderer.create_themes_slide(prs.slides.add_slide(blank), narrative.themes, qs)

        for idx, (q, res) in enumerate(zip(qs, results)):  # noqa: B905
            slide = prs.slides.add_slide(blank)
            renderer.render_question_slide(slide, q, res, prefs.get(idx), slide_png_paths[idx])
            renderer.build_question_slides_footer(slide, len(prs.slides))

        renderer.create_takeaways_slide(prs.slides.add_slide(blank), narrative.key_takeaways)
        if include_recommendations:
            renderer.create_recommendations_slide(prs.slides.add_slide(blank), narrative.recommendations)

        target = num_slides if (num_slides is not None and num_slides > 0) else len(prs.slides)
        while len(prs.slides) < target:
            renderer.create_appendix_slide(prs.slides.add_slide(blank), len(prs.slides))

        prs.save(str(pptx_path))
        elapsed = int((time.time() - start) * 1000)
        logger.info(f"[PresentationAgent] end: pptx={pptx_path} slides={len(prs.slides)} ({elapsed}ms)")
        emit_pipeline_stage(
            "viz",
            "done",
            f"Презентация: {len(prs.slides)} слайдов, {len(png_exported)} превью",
            agent="presentation_agent",
        )
        return PresentationResult(
            pptx_path=str(pptx_path),
            num_slides=len(prs.slides),
            slide_png_paths=png_exported,
            presentation_id=presentation_id,
            reasoning=(
                f"Собрано {len(prs.slides)} слайдов из {len(qs)} вопросов (slide pipeline). "
                "PresentationRenderer: динамические макеты + gov-badge + KPI + таблицы."
            ),
        )

    def run_input(self, inp: PresentationInput) -> PresentationResult:
        return self.run(inp.questions)