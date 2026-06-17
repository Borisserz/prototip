import logging

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class EmailRequest(BaseModel):
    to: str
    subject: str
    content: str

@router.post("/send-email")
async def send_email(req: EmailRequest):
    """Отправка отчета на Email (Mock)."""
    #  интеграция с SMTP 
    
    logger.info(f"[EMAIL MOCK] Отправка письма на {req.to}...")
    logger.info(f"[EMAIL MOCK] Тема: {req.subject}")
    logger.info(f"[EMAIL MOCK] Содержимое: {req.content}")
    logger.info("[EMAIL MOCK] Письмо успешно 'отправлено'!")
    
    return {"status": "ok", "message": f"Отправлено на {req.to}"}
