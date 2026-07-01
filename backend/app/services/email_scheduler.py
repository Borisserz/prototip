import json
import logging
import os
import time

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.orchestrator import Orchestrator

# BUG 5.4 FIX: use the canonical email sender — no more duplicate SMTP logic here
from app.services.email_service import send_email

logger = logging.getLogger("EmailScheduler")


def generate_and_send_weekly_report(
    recipient_email: str, role: str, question: str, client_id: str = None
) -> None:
    """Генерирует еженедельный отчёт через Orchestrator и отправляет на почту.

    Отправка делегируется email_service.send_email() — единственной точке
    SMTP в проекте. Дублирование smtplib/MIME-логики здесь устранено (Bug 5.4).
    """
    logger.info(
        "Generating weekly report for %s (role=%s, tenant=%s)",
        recipient_email,
        role,
        client_id,
    )

    orchestrator = Orchestrator()
    try:
        user_data: dict = {"role": role}
        if client_id:
            user_data["client_id"] = client_id
        res = orchestrator.ask(question, user=user_data)
        report_text = getattr(res, "reasoning", str(res))
    except Exception as e:
        logger.error("Error generating report: %s", e)
        report_text = f"Произошла ошибка при генерации отчёта: {e}"

    body = (
        f"Здравствуйте!\n\n"
        f"Ваш еженедельный аналитический отчёт готов.\n\n"
        f"{report_text}\n\n"
        f"С уважением,\nBI Ассистент"
    )
    send_email(
        recipient_email,
        "Еженедельный налоговый отчёт (BI Платформа)",
        body,
    )


def load_subscriptions():
    path = os.path.join(os.path.dirname(__file__), "../../data/user_subscriptions.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load subscriptions: {e}")
        return []


def start_scheduler():
    """Инициализация и запуск фонового планировщика отчетов и алертов."""
    try:
        from app.services.anomaly_detector import detect_anomalies
    except ImportError:
        detect_anomalies = None

    scheduler = BackgroundScheduler(timezone=pytz.timezone("Europe/Minsk"))

    subs = load_subscriptions()
    for sub in subs:
        sched = sub.get("schedule", {})
        day = sched.get("day_of_week", "mon")
        hour = sched.get("hour", 9)
        minute = sched.get("minute", 0)

        client_id = sub.get("client_id")
        scheduler.add_job(
            generate_and_send_weekly_report,
            trigger=CronTrigger(day_of_week=day, hour=hour, minute=minute),
            args=[sub["email"], sub["role"], sub["question"], client_id],
        )
        logger.info(f"Scheduled report for {sub['email']} on {day} at {hour}:{minute:02d}")

    # Мониторинг аномалий (каждый час)
    if detect_anomalies:
        scheduler.add_job(detect_anomalies, trigger="interval", hours=1)

    scheduler.start()
    logger.info("Email Scheduler started.")


if __name__ == "__main__":
    start_scheduler()
    while True:
        time.sleep(1)
