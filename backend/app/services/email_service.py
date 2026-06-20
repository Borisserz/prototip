import logging
import os
from email.message import EmailMessage

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.example.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "no-reply@tax.gov.by")
SMTP_PASS = os.getenv("SMTP_PASS", "secret")

def send_report_email(to_email: str, subject: str, content: str, attachment_path: str = None):
    """
    Отправляет email с отчетом или дашбордом.
    В соответствии с требованиями, Telegram запрещен, используем только корпоративную почту.
    """
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = SMTP_USER
    msg['To'] = to_email
    msg.set_content(content)

    if attachment_path and os.path.exists(attachment_path):
        with open(attachment_path, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(attachment_path)
            # Упрощенное определение mimetype
            maintype = 'application'
            subtype = 'octet-stream'
            if file_name.endswith('.png'):
                maintype, subtype = 'image', 'png'
            elif file_name.endswith('.xlsx'):
                maintype, subtype = 'application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                
            msg.add_attachment(file_data, maintype=maintype, subtype=subtype, filename=file_name)

    try:
        # Для прототипа просто логируем, так как реального SMTP нет
        logger.info(f"Отправка email на {to_email} с темой '{subject}'. Вложение: {attachment_path}")
        # server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        # server.starttls()
        # server.login(SMTP_USER, SMTP_PASS)
        # server.send_message(msg)
        # server.quit()
        return True
    except Exception as e:
        logger.error(f"Ошибка при отправке email: {e}")
        return False
