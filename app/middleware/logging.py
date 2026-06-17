import logging
import time
import uuid

from fastapi import Request
from app.logging_utils import set_correlation_id

logger = logging.getLogger(__name__)

async def log_requests_middleware(request: Request, call_next):
    # Пытаемся взять correlation_id из заголовков, иначе генерируем новый
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    set_correlation_id(request_id)
    
    start_time = time.time()
    
    # Лог старта запроса (только для важных эндпоинтов, но пока оставим)
    # logger.info("HTTP request started", extra={"event": "http_request_start", "method": request.method, "path": request.url.path})
    
    response = await call_next(request)
    
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-Id"] = request_id
    
    # Структурированный лог по окончании запроса
    logger.info("HTTP request completed", extra={
        "event": "http_request_completed",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "duration_s": round(process_time, 4)
    })
    
    return response
