from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("SemanticCatalog")


class ColumnDef(BaseModel):
    name: str
    type: str
    description: str | None = None
    enum_values: list[str] | None = None


class MetricDef(BaseModel):
    name: str
    expression: str
    description: str | None = None


class ModelDef(BaseModel):
    name: str
    description: str | None = None
    columns: list[ColumnDef] = Field(default_factory=list)
    metrics: list[MetricDef] = Field(default_factory=list)


class SemanticCatalog(BaseModel):
    version: str = "1.0"
    models: list[ModelDef] = Field(default_factory=list)

    @classmethod
    def load(cls, file_path: str | Path) -> SemanticCatalog:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Semantic model file {path} not found.")
            return cls()

        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                return cls()
            return cls(**data)
        except Exception as e:
            logger.error(f"Error loading semantic catalog from {path}: {e}")
            return cls()

    def to_llm_prompt(self) -> str:
        """Returns a string representation optimized for LLM prompting."""
        prompt = ["=== ADVANCED SEMANTIC ENGINE CATALOG ==="]
        for model in self.models:
            prompt.append(f"Table/View: {model.name}")
            if model.description and model.description != "Нет описания.":
                prompt.append(f"  Description: {model.description}")
            prompt.append("  Columns:")
            for col in model.columns:
                col_str = f"    - {col.name} ({col.type})"
                if col.description and col.description != "Нет описания.":
                    col_str += f" | {col.description}"
                if col.enum_values:
                    enums = ", ".join(col.enum_values[:5])
                    if len(col.enum_values) > 5:
                        enums += ", ..."
                    col_str += f" | Enums: [{enums}]"
                prompt.append(col_str)
            if model.metrics:
                prompt.append("  Calculated Metrics (Используй эти формулы в SELECT):")
                for m in model.metrics:
                    m_str = f"    - {m.name} AS {m.expression}"
                    if m.description:
                        m_str += f" | {m.description}"
                    prompt.append(m_str)
            prompt.append("")
        return "\n".join(prompt)
