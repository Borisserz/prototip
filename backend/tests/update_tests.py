import glob

replacements = [
    ('"""Тесты: ', '"""Тесты: '),
    ('"""Тесты ChartAgent.', '"""Тесты ChartAgent.'),
    ("Ollama недоступен для живого теста", "Ollama недоступен для живого теста"),
    ("# Детерминированный рендер", "# Детерминированный рендер"),
    ("Минимальные тесты на новые компоненты ", "Минимальные тесты на новые компоненты "),
    ("унификация", "унификация"),
    ('"""Тесты AnalystAgent.', '"""Тесты AnalystAgent.'),
    ("теста", "теста"),
    ('"""E2E тесты:', '"""E2E тесты:'),
    ("для e2e", "для e2e"),
    ("Ключевой тест:", "Ключевой тест:"),
    ("Итоговый тест:", "Итоговый тест:"),
    ("# Extensions:", "# Extensions:"),
    ("Новые типы", "Новые типы"),
    ("unified facade", "unified facade"),
    ("live теста", "live теста"),
    ('"""Тесты DataAgent.', '"""Тесты DataAgent.'),
    ("spec 'Готово'", "spec 'Готово'"),
    ('"""Тесты PresentationAgent.', '"""Тесты PresentationAgent.'),
    ("теста", "теста"),
    ("area", "area"),
    (
        '"""Тесты детерминированного repair ChartSpec."""',
        '"""Тесты детерминированного repair ChartSpec."""',
    ),
]

for filepath in glob.glob(
    "/Users/borisserzhanovich/projects/projects-prototip/prototip/backend/tests/*.py"
):
    with open(filepath) as f:
        content = f.read()
    for old, new in replacements:
        content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
print("Done updating test files.")
