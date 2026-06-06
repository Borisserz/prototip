#!/usr/bin/env python3
"""Генерация портфолио showcase/ для встречи с руководством.

Создаёт:
  showcase/charts/     — 12 типов графиков (PNG scale 2.5, HTML, spec.json)
  showcase/presentations/ — 4 executive .pptx
  showcase/manifest.json

Офлайн: не требует Ollama. Запуск из корня репозитория:
  python scripts/generate_leadership_showcase.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.showcase_builder import generate_showcase  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация leadership showcase")
    parser.add_argument(
        "--output",
        "-o",
        default="showcase",
        help="Корневая папка showcase (по умолчанию: showcase)",
    )
    parser.add_argument(
        "--csv",
        default="data/sample.csv",
        help="Путь к датасету (по умолчанию: data/sample.csv)",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=2.5,
        help="Масштаб PNG для галереи графиков (по умолчанию: 2.5)",
    )
    args = parser.parse_args()

    manifest = generate_showcase(
        args.output,
        csv_path=Path(args.csv),
        chart_scale=args.scale,
    )
    print(f"✓ Showcase: {Path(args.output).resolve()}")
    print(f"  Графиков: {len(manifest['charts'])}")
    print(f"  Презентаций: {len(manifest['presentations'])}")
    for p in manifest["presentations"]:
        print(f"    • {p['filename']} — {p['num_slides']} слайдов")
    print(f"  Манифест: {manifest['manifest']}")


if __name__ == "__main__":
    main()