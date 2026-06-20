import re


def anonymize_text(text: str) -> str:
    """
    Маскирует чувствительные данные (PII) в тексте.
    - ИНН (УНП в Беларуси: 9 цифр) -> ***
    - Номера счетов (BY...: 28 символов) -> BY***
    """
    if not isinstance(text, str):
        return text
        
    # Маскировка УНП (9 цифр)
    text = re.sub(r'\b\d{9}\b', '[УНП СКРЫТ]', text)
    
    # Маскировка IBAN (Беларусь: BY + 2 цифры + 4 буквы + 20 цифр/букв = 28)
    text = re.sub(r'\bBY\d{2}[A-Z0-9]{24}\b', '[СЧЕТ СКРЫТ]', text)
    
    return text

def anonymize_dict(data: dict) -> dict:
    """Рекурсивно анонимизирует значения в словаре."""
    anonymized = {}
    for k, v in data.items():
        if isinstance(v, str):
            anonymized[k] = anonymize_text(v)
        elif isinstance(v, dict):
            anonymized[k] = anonymize_dict(v)
        elif isinstance(v, list):
            anonymized[k] = [anonymize_text(i) if isinstance(i, str) else i for i in v]
        else:
            anonymized[k] = v
    return anonymized
