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

## Векторное хранилище (Qdrant)
Семантика БД и RAG-память хранятся в **Qdrant** — он поднимается как отдельный сервис
в корневом `docker-compose.yml` (официальный образ, без сборки). Инициализация коллекций —
скриптом `backend/scripts/init_qdrant.py`.

## Мультитенантность (Phase 6)
Для изолированного клиента поднимается отдельный ClickHouse-контейнер по шаблону
`../docker-compose.tenant.template.yml` (генерируется `backend/scripts/build_tenant.py`).
