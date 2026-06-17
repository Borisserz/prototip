import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("ExcelExporter")

def export_to_excel(data: list[dict], filename: str = "export.xlsx") -> str:
    """Генерирует красиво отформатированный Excel файл (Phase 16)."""
    if not data:
        raise ValueError("Нет данных для экспорта")

    out_dir = Path("out/exports")
    out_dir.mkdir(parents=True, exist_ok=True)
    file_path = out_dir / filename

    df = pd.DataFrame(data)
    
    try:
        # Используем openpyxl для форматирования
        with pd.ExcelWriter(str(file_path), engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Аналитика')
            
            workbook = writer.book
            worksheet = writer.sheets['Аналитика']
            
            # Автоширина колонок
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = min(length + 2, 50)
                
            # Красивая шапка (header)
            from openpyxl.styles import Alignment, Font, PatternFill
            header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid") # Темно-синий
            header_font = Font(color="FFFFFF", bold=True)
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal='center', vertical='center')
                
        logger.info(f"Excel экспорт успешно создан: {file_path}")
        return str(file_path)
    except Exception as e:
        logger.error(f"Ошибка генерации Excel: {e}")
        # Fallback to simple CSV if openpyxl fails
        fallback_path = str(file_path).replace(".xlsx", ".csv")
        df.to_csv(fallback_path, index=False)
        return fallback_path
