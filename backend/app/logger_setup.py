import logging

from pythonjsonlogger import jsonlogger

from app.logging_utils import get_correlation_id


class CorrelationIdFilter(logging.Filter):
    """Добавляет correlation_id во все логи."""

    def filter(self, record):
        record.correlation_id = get_correlation_id()
        return True


def setup_json_logger():
    """Настраивает структурированное JSON логирование для всего приложения."""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # Удаляем стандартные хэндлеры
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    logHandler = logging.StreamHandler()

    # Формат JSON лога
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(correlation_id)s %(message)s",
        rename_fields={"levelname": "level", "asctime": "timestamp"},
    )

    logHandler.setFormatter(formatter)
    logHandler.addFilter(CorrelationIdFilter())
    logger.addHandler(logHandler)

    # Отключаем лишний шум от uvicorn
    logging.getLogger("uvicorn.access").disabled = True
