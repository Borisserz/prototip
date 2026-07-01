import io
import logging
from typing import Any

import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class ExportRequest(BaseModel):
    data: list[dict[str, Any]]
    filename: str = "export.xlsx"


@router.post("/export-excel")
async def export_excel(req: ExportRequest):
    """Экспорт данных в Excel."""
    if not req.data:
        raise HTTPException(status_code=400, detail="Нет данных для экспорта")

    try:
        df = pd.DataFrame(req.data)

        # Записываем в BytesIO
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Dashboard Data")
        output.seek(0)

        # FastAPI StreamingResponse для скачивания файла
        headers = {"Content-Disposition": f'attachment; filename="{req.filename}"'}
        return StreamingResponse(
            output,
            headers=headers,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        logger.error(f"Ошибка экспорта в Excel: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка генерации Excel: {str(e)}")
