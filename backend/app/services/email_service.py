"""Корпоративная email-рассылка (единственная точка отправки почты).

BUG 5.4 FIX: ранее в проекте сосуществовали два несвязанных SMTP-модуля —
  • email_service.py  — реальный SMTP, но закомментированный (фактически заглушка)
  • email_scheduler.py — реальный SMTP через MIMEMultipart, дублировал конфиг

Теперь вся логика отправки живёт здесь. email_scheduler.py импортирует send_email.

Поведение при отсутствии SMTP-credentials (dev/test):
  письмо логируется, функция возвращает True — система не падает.
"""

from __future__ import annotations

import logging
import mimetypes
import os
import smtplib
from collections.abc import Iterable
from email.message import EmailMessage
from pathlib import Path

logger = logging.getLogger(__name__)

# SMTP-конфигурация из окружения
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
# Адрес отправителя: SMTP_FROM → SMTP_USER → заглушка (только для dev)
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER or "no-reply@bi.local"


def send_email(
    to: str | Iterable[str],
    subject: str,
    body: str,
    *,
    html: bool = False,
    attachments: Iterable[str | Path] | None = None,
) -> bool:
    """Отправить корпоративное письмо через SMTP с опциональными вложениями.

    Единственная точка отправки почты в проекте. Используй эту функцию везде:
    ETL-алерты, scheduled reports, уведомления пользователей.

    При отсутствии SMTP-credentials (SMTP_USER / SMTP_PASS) письмо логируется
    на уровне INFO и функция возвращает True — никаких исключений, dev-среда
    продолжает работать без настроенного почтового сервера.

    Args:
        to:          Адрес получателя или список адресов.
        subject:     Тема письма.
        body:        Текст письма (plain-text или HTML в зависимости от флага *html*).
        html:        Если True — тело отправляется как text/html.
        attachments: Пути к файлам-вложениям (пропускаются, если файл не найден).

    Returns:
        True при успешной отправке (или при режиме mock), False при ошибке SMTP.
    """
    recipients: list[str] = [to] if isinstance(to, str) else list(to)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = ", ".join(recipients)
    msg.set_content(body, subtype="html" if html else "plain", charset="utf-8")

    # Вложения
    for raw_path in attachments or []:
        path = Path(raw_path)
        if not path.exists():
            logger.warning("[EmailService] Вложение не найдено, пропускаю: %s", path)
            continue
        mime_type, _ = mimetypes.guess_type(path.name)
        maintype, subtype = (mime_type or "application/octet-stream").split("/", 1)
        with path.open("rb") as fh:
            msg.add_attachment(fh.read(), maintype=maintype, subtype=subtype, filename=path.name)

    # Отправка или mock-лог
    if not (SMTP_USER and SMTP_PASS):
        logger.info(
            "[EmailService] SMTP не настроен — письмо залогировано (dev-режим).\n"
            "  To: %s\n  Subject: %s\n  Body (первые 500 символов): %.500s",
            recipients,
            subject,
            body,
        )
        return True  # не ошибка: в dev-окружении почта не нужна

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info("[EmailService] Письмо отправлено → %s (тема: %s)", recipients, subject)
        return True
    except Exception as exc:
        logger.error("[EmailService] Ошибка отправки → %s: %s", recipients, exc)
        return False


# Обратно-совместимый алиас (используется ETL-алертами и роутерами)
def send_report_email(
    to_email: str,
    subject: str,
    content: str,
    attachment_path: str | None = None,
) -> bool:
    """Обёртка для совместимости: вызывается из etl_common.py и routers/etl.py."""
    attachments = [attachment_path] if attachment_path else None
    return send_email(to_email, subject, content, attachments=attachments)
