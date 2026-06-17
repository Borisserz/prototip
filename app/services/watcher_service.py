import logging
from app.crew.tools import EmailDeliveryTool

logger = logging.getLogger("WatcherService")

class WatcherService:
    @staticmethod
    def run_anomaly_scan() -> dict:
        logger.info("[WatcherService] Запуск проактивного сканирования аномалий...")
        
        try:
            from app.main import get_orchestrator
            orchestrator = get_orchestrator()
            
            prompt = (
                "Проведи аудит базы данных по всем налогам и задолженностям. "
                "Найди самую крупную аномалию или резкое падение сборов по любому "
                "из регионов за последний год. Сформируй краткий Executive Summary "
                "с выделением главной проблемы (Аномалии)."
            )
            
            # Эмулируем роль admin для полного доступа при системном сканировании
            res = orchestrator.ask(prompt, user={"role": "admin"})
            
            if not res.success:
                error_msg = f"Ошибка генерации отчета: {getattr(res, 'error', 'Unknown')}"
                logger.error(f"[WatcherService] {error_msg}")
                return {"status": "error", "detail": error_msg}
                
            report = getattr(res, "reasoning", "Нет отчета.")
            
            # Отправка
            email_tool = EmailDeliveryTool()
            final_text = f"🚨 АВТОМАТИЧЕСКИЙ ПРОАКТИВНЫЙ АЛЕРТ 🚨\n\n{report}"
            delivery_status = email_tool._run(final_text)
            
            logger.info(f"[WatcherService] Завершено. Email: {delivery_status}")
            return {"status": "success", "report": report, "email_status": delivery_status}
            
        except Exception as e:
            logger.error(f"[WatcherService] Системная ошибка: {e}")
            return {"status": "error", "detail": str(e)}
