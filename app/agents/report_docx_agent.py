"""ReportDocxAgent (Phase 2): сборка отчёта в формате Word (.docx).

Назначение:
  - принимает размеченный Markdown (как правило, от LLM) и собирает .docx;
  - умеет рендерить графики по ChartSpec через viz/charts.py и вставлять их
    в документ (PNG зеркалится в MinIO бакет `charts`);
  - готовый .docx зеркалится в MinIO бакет `documents` (Phase 1 storage);
  - при отсутствии готового Markdown может сгенерировать его из вопроса+данных
    через LLM (core.llm.call_structured); при недоступности LLM — собирает
    простой отчёт из переданных данных (нелопающее поведение).

Вход (run) гибкий:
  - str  — трактуется как Markdown;
  - dict — {markdown, title, subtitle, charts, image_map, question, data};
  - ReportDocxInput — типизированный вариант того же.

Возвращает ReportDocxResult (наследник AgentResult) с путём к .docx и URL.

НЕ ломает существующие агенты/viz: использует только публичные API.
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

from app.agents.base_agent import BaseAgent
from app.agents.models import AgentResult
from app.services.docx_renderer import MarkdownDocxRenderer, _default_image_resolver
from core import storage

logger = logging.getLogger("ReportDocxAgent")

OUT_DIR = Path("out")


# ─── модели ввода/вывода ─────────────────────────────────────────────────────
class ReportChart(BaseModel):
    """Описание графика для вставки в отчёт.

    placeholder — ключ, который встречается в Markdown как ![alt](placeholder).
    Поддерживается рендер по ChartSpec (spec+data) или готовый путь/MinIO-ключ.
    """

    placeholder: str = Field(..., description="Ключ-ссылка в Markdown: ![..](placeholder)")
    title: str | None = Field(None, description="Подпись под графиком")
    spec: dict[str, Any] | None = Field(None, description="ChartSpec (dict) для рендера через viz")
    data: list[dict[str, Any]] | None = Field(None, description="Данные для графика")
    src: str | None = Field(None, description="Готовый путь к PNG или ключ объекта в MinIO")


class ReportDocxInput(BaseModel):
    markdown: str | None = Field(None, description="Готовый размеченный Markdown")
    title: str | None = Field(None, description="Заголовок документа")
    subtitle: str | None = Field(None, description="Подзаголовок")
    question: str | None = Field(None, description="Запрос пользователя (если markdown нужно сгенерировать)")
    data: list[dict[str, Any]] | None = Field(None, description="Табличные данные для отчёта")
    charts: list[ReportChart] = Field(default_factory=list, description="Графики для вставки")


class ReportDocxResult(AgentResult):
    docx_path: str = Field(..., description="Локальный путь к .docx")
    url: str | None = Field(None, description="Presigned URL в MinIO (или None)")
    markdown: str = Field("", description="Использованный Markdown")
    title: str = Field("", description="Заголовок отчёта")


# ─── LLM-схема для генерации Markdown ────────────────────────────────────────
class _ReportMarkdown(BaseModel):
    title: str = Field(..., description="Короткий заголовок отчёта на русском")
    markdown: str = Field(..., description="Тело отчёта в Markdown (заголовки, списки, таблицы)")


class ReportDocxAgent(BaseAgent):
    name = "report_docx_agent"
    description = (
        "Собирает отчёт в формате Word (.docx) из размеченного Markdown, "
        "вставляет графики (рендер через viz/charts, картинки из MinIO) и "
        "зеркалит результат в объектное хранилище."
    )

    def __init__(self, img_width_in: float = 6.0) -> None:
        self.img_width_in = img_width_in

    # ── основной контракт ─────────────────────────────────────────────────────
    def run(self, request: Any, *args: Any, **kwargs: Any) -> ReportDocxResult:
        try:
            inp = self._coerce_input(request, kwargs)
        except Exception as e:  # noqa: BLE001
            return ReportDocxResult(
                success=False, error=f"Некорректный ввод: {e}", docx_path="", reasoning=str(e)
            )

        # 1. Markdown: готовый или сгенерированный
        markdown = inp.markdown
        title = inp.title or "Аналитический отчёт"
        if not markdown:
            markdown, gen_title = self._generate_markdown(inp)
            if not inp.title and gen_title:
                title = gen_title

        # 2. Рендер графиков -> карта placeholder -> локальный путь
        image_map = self._prepare_charts(inp.charts)

        # 3. Сборка .docx
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        rid = uuid.uuid4().hex[:8]
        out_path = OUT_DIR / f"report_{rid}.docx"

        def resolver(src: str) -> str | None:
            if src in image_map:
                return image_map[src]
            return _default_image_resolver(src)

        renderer = MarkdownDocxRenderer(image_resolver=resolver, img_width_in=self.img_width_in)
        start = time.time()
        renderer.render(markdown, out_path, title=title, subtitle=inp.subtitle)

        # 4. Зеркалирование в MinIO (бакет documents); нелопающе
        url = None
        try:
            mirrored = storage.mirror_artifact(out_path, "documents")
            url = mirrored if mirrored and mirrored.startswith("http") else None
        except Exception as e:  # noqa: BLE001
            logger.warning("ReportDocxAgent: не удалось зеркалировать в MinIO: %s", e)

        elapsed = int((time.time() - start) * 1000)
        logger.info("ReportDocxAgent: .docx готов %s (%sms)", out_path, elapsed)

        return ReportDocxResult(
            success=True,
            docx_path=str(out_path),
            url=url,
            markdown=markdown,
            title=title,
            reasoning=f"Отчёт собран из Markdown ({len(markdown)} симв.), графиков: {len(image_map)}.",
        )

    # ── удобный явный метод ─────────────────────────────────────────────────────
    def build_from_markdown(
        self,
        markdown: str,
        *,
        title: str | None = None,
        subtitle: str | None = None,
        charts: list[ReportChart] | None = None,
    ) -> ReportDocxResult:
        return self.run(
            ReportDocxInput(markdown=markdown, title=title, subtitle=subtitle, charts=charts or [])
        )

    # ── приведение ввода ───────────────────────────────────────────────────────
    def _coerce_input(self, request: Any, kwargs: dict) -> ReportDocxInput:
        if isinstance(request, ReportDocxInput):
            return request
        if isinstance(request, str):
            return ReportDocxInput(markdown=request, **{k: v for k, v in kwargs.items() if k in ReportDocxInput.model_fields})
        if isinstance(request, dict):
            data = dict(request)
            data.update({k: v for k, v in kwargs.items() if k in ReportDocxInput.model_fields})
            return ReportDocxInput(**data)
        if request is None:
            return ReportDocxInput(**{k: v for k, v in kwargs.items() if k in ReportDocxInput.model_fields})
        raise TypeError(f"Неподдерживаемый тип запроса: {type(request)}")

    # ── рендер графиков ─────────────────────────────────────────────────────────
    def _prepare_charts(self, charts: list[ReportChart]) -> dict[str, str]:
        image_map: dict[str, str] = {}
        if not charts:
            return image_map
        for ch in charts:
            try:
                if ch.spec and ch.data:
                    png = self._render_chart_png(ch)
                    if png:
                        image_map[ch.placeholder] = png
                elif ch.src:
                    # готовый путь или MinIO-ключ — резолвим лениво в renderer,
                    # но если это локальный существующий файл, кладём сразу
                    p = Path(ch.src)
                    if p.exists():
                        image_map[ch.placeholder] = str(p)
                    else:
                        resolved = _default_image_resolver(ch.src)
                        if resolved:
                            image_map[ch.placeholder] = resolved
            except Exception as e:  # noqa: BLE001
                logger.warning("ReportDocxAgent: график %s пропущен: %s", ch.placeholder, e)
        return image_map

    def _render_chart_png(self, ch: ReportChart) -> str | None:
        try:
            from core.models import ChartSpec
            from viz import charts as viz_charts
        except Exception as e:  # noqa: BLE001
            logger.warning("ReportDocxAgent: viz/ChartSpec недоступны: %s", e)
            return None
        df = pd.DataFrame(ch.data or [])
        if df.empty:
            return None
        spec = ChartSpec(**ch.spec) if not isinstance(ch.spec, ChartSpec) else ch.spec
        fig = viz_charts.build_chart(df, spec)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        png_path = OUT_DIR / f"report_chart_{uuid.uuid4().hex[:8]}.png"
        viz_charts.export_png(fig, png_path)  # зеркалит в MinIO bucket charts
        return str(png_path)

    # ── генерация Markdown через LLM (опционально) ────────────────────────────────
    def _generate_markdown(self, inp: ReportDocxInput) -> tuple[str, str | None]:
        question = inp.question or "Сформируй аналитический отчёт по данным."
        sample = (inp.data or [])[:50]
        try:
            from core.llm import call_structured

            prompt = (
                f"Запрос: {question}\n\n"
                f"Данные (JSON, первые строки): {sample}\n\n"
                "Сформируй деловой аналитический отчёт на русском языке в формате Markdown. "
                "Используй заголовки (##), маркированные/нумерованные списки и при наличии "
                "табличных данных — Markdown-таблицу. Без вступительных фраз."
            )
            res = call_structured(
                prompt,
                schema=_ReportMarkdown,
                system="Ты — аналитик. Отвечай только структурированным результатом.",
                agent_name=self.name,
            )
            return res.markdown, res.title
        except Exception as e:  # noqa: BLE001
            logger.info("ReportDocxAgent: LLM недоступна (%s), сборка fallback-отчёта", e)
            return self._fallback_markdown(inp), None

    def _fallback_markdown(self, inp: ReportDocxInput) -> str:
        parts: list[str] = []
        if inp.question:
            parts.append(f"## Запрос\n\n{inp.question}\n")
        rows = inp.data or []
        if rows:
            cols = list(rows[0].keys())
            header = "| " + " | ".join(str(c) for c in cols) + " |"
            sep = "| " + " | ".join("---" for _ in cols) + " |"
            body = "\n".join(
                "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows[:30]
            )
            parts.append("## Данные\n\n" + header + "\n" + sep + "\n" + body + "\n")
        if not parts:
            parts.append("## Отчёт\n\nНет данных для отображения.\n")
        return "\n".join(parts)

    def get_capabilities(self) -> dict[str, Any]:
        caps = super().get_capabilities()
        caps["outputs"] = ["docx", "minio_url"]
        caps["inputs"] = ["markdown", "question+data", "charts(ChartSpec)"]
        return caps
