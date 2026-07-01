# DB — аналитическое и векторное хранилища

## ClickHouse (этот образ)
Аналитическое хранилище. Образ собирается из `Dockerfile` и автоматически применяет
схему `clickhouse/init.sql` при первом старте.

```
db/
├── Dockerfile              # ClickHouse + предзагрузка init.sql
└── clickhouse/
    ├── init.sql            # DDL: таблицы аналитики
    ├── seed.py             # наполнение демо-данными
    └── docker-compose.yml  # standalone-вариант запуска только ClickHouse
```

### Запуск

Из корневого compose (рекомендуется):
```bash
docker compose up -d --build clickhouse
```

Отдельно (standalone):
```bash
cd db && docker build -t prototip-clickhouse . && \
docker run -d -p 8123:8123 -p 9000:9000 prototip-clickhouse
```

Наполнение демо-данными:
```bash
cd db/clickhouse && python seed.py
```

Проверка: http://localhost:8123/ping → `Ok.`

## Векторное хранилище (поверх ClickHouse)
Семантика БД и RAG-память хранятся в **ClickHouse** (векторный поиск через `cosineDistance`).
Эмбеддинги индексируются скриптами `backend/app/utils/init_clickhouse_knowledge.py` и
`init_schema_knowledge.py`. Отдельное векторное хранилище (Qdrant) не используется.


Для изолированного клиента поднимается отдельный ClickHouse-контейнер по шаблону
`../docker-compose.tenant.template.yml` (генерируется `backend/scripts/build_tenant.py`).
