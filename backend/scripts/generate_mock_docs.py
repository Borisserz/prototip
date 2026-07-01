import os
import random
import uuid

DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "docs")

TAX_TYPES = [
    "НДС",
    "Налог на прибыль",
    "Подоходный налог",
    "Налог на недвижимость",
    "Земельный налог",
    "Экологический налог",
]
REGIONS = [
    "Минск",
    "Гомельская область",
    "Брестская область",
    "Витебская область",
    "Могилевская область",
    "Гродненская область",
    "Минская область",
]
PENALTY_RATES = [0.01, 0.05, 0.1, 0.15]

TEMPLATES = [
    """# Статья {article_num}. Порядок исчисления и уплаты налога: {tax_type}.
    
Для региона **{region}** устанавливаются следующие правила.
Налоговой базой признается стоимость реализованных товаров (работ, услуг), имущественных прав.
Базовая ставка налога составляет {rate}%.

В случае возникновения просроченной задолженности свыше {days} дней, применяется штрафная пеня в размере {penalty}% за каждый день просрочки.
""",
    """# Указ №{article_num} по региону {region}. О льготах по налогу: {tax_type}.
    
В целях стимулирования экономики, предприятия, работающие в сфере IT и сельского хозяйства в регионе **{region}**, освобождаются от уплаты {tax_type} на срок {days} дней.
Стандартная ставка {rate}% не применяется, если выручка реинвестирована.
В противном случае наступает ответственность согласно ст. 42 с начислением пени {penalty}%.
""",
    """# Внутренний регламент инспекции {region}. Взыскание по налогу: {tax_type}.
    
При выявлении задолженности по {tax_type} свыше 10 000 Br, инспектор обязан направить уведомление в течение {days} дней.
Процент взыскания составляет {rate}%, пеня {penalty}%.
Если налогоплательщик уклоняется, дело передается в суд. Уникальный код регламента: {doc_uuid}.
""",
]


def generate_docs(count=100):
    os.makedirs(DOCS_DIR, exist_ok=True)

    print(f"Генерация {count} синтетических нормативных документов...")

    for i in range(count):
        tax_type = random.choice(TAX_TYPES)
        region = random.choice(REGIONS)
        rate = random.randint(5, 30)
        days = random.randint(10, 90)
        penalty = random.choice(PENALTY_RATES)
        template = random.choice(TEMPLATES)

        content = template.format(
            article_num=random.randint(100, 999),
            tax_type=tax_type,
            region=region,
            rate=rate,
            days=days,
            penalty=penalty,
            doc_uuid=str(uuid.uuid4())[:8],
        )

        filename = f"doc_{tax_type.replace(' ', '_')}_{region.replace(' ', '_')}_{i}.md"
        filepath = os.path.join(DOCS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    print(f"Успешно готово {count} документов в {DOCS_DIR}")


if __name__ == "__main__":
    generate_docs(150)
