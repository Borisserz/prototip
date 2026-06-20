import json
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.orchestrator import Orchestrator

logger = logging.getLogger("EmailScheduler")

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")

def generate_and_send_weekly_report(recipient_email: str, role: str, question: str):
    logger.info(f"Generating weekly report for {recipient_email} (Role: {role})")
    
    # Run the orchestrator pipeline with user context
    orchestrator = Orchestrator()
    try:
        res = orchestrator.ask(question, user={"role": role})
        report_text = getattr(res, "reasoning", str(res))
    except Exception as e:
        logger.error(f"Error generating report: {e}")
        report_text = f"Произошла ошибка при генерации отчета: {str(e)}"
    
    # Send Email
    msg = MIMEMultipart()
    msg['Subject'] = 'Еженедельный налоговый отчет (BI Платформа)'
    msg['From'] = SMTP_USER
    msg['To'] = recipient_email
    
    body = f"Здравствуйте!\n\nВаш еженедельный аналитический отчет готов.\n\n{report_text}\n\nС уважением,\nBI Ассистент"
    msg.attach(MIMEText(body, 'plain'))
    
    if SMTP_USER and SMTP_PASS:
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            logger.info(f"Email sent successfully to {recipient_email}!")
        except Exception as e:
            logger.error(f"Failed to send email to {recipient_email}: {e}")
    else:
        logger.warning(f"SMTP credentials not configured. Skipping actual email to {recipient_email}.")
        logger.info(f"MOCK EMAIL CONTENT for {recipient_email}:\n{body}")

def load_subscriptions():
    path = os.path.join(os.path.dirname(__file__), '../../data/user_subscriptions.json')
    try:
        with open(path, encoding='utf-8') as f:
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

    scheduler = BackgroundScheduler(timezone=pytz.timezone('Europe/Minsk'))
    
    subs = load_subscriptions()
    for sub in subs:
        sched = sub.get("schedule", {})
        day = sched.get("day_of_week", "mon")
        hour = sched.get("hour", 9)
        minute = sched.get("minute", 0)
        
        scheduler.add_job(
            generate_and_send_weekly_report,
            trigger=CronTrigger(day_of_week=day, hour=hour, minute=minute),
            args=[sub["email"], sub["role"], sub["question"]]
        )
        logger.info(f"Scheduled report for {sub['email']} on {day} at {hour}:{minute:02d}")
    
    # Мониторинг аномалий (каждый час)
    if detect_anomalies:
        scheduler.add_job(
            detect_anomalies,
            trigger='interval',
            hours=1
        )
    
    scheduler.start()
    logger.info("Email Scheduler started.")

if __name__ == "__main__":
    start_scheduler()
    while True:
        time.sleep(1)
