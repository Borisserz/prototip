# Фаза 6: Модульность и B2B-масштабирование (Multi-tenant SaaS)

Подготовка платформы к развёртыванию под конкретных клиентов (Pivzavod и др.).
Один backend обслуживает множество изолированных клиентов; каждый клиент привязан
к **личному ClickHouse**, **личной коллекции семантики** и **уникальному JWT-токену**.

## Компоненты

| Файл | Назначение |
|------|-----------|
| `core/tenant.py` | Реестр клиентов (`TenantStore`): CRUD, шифрование кред CH, выпуск JWT/API-ключа, фабрика ClickHouse-клиента. Хранилище — `data/tenants/registry.json`. |
| `core/sql_guard.py` | Жёсткая валидация SQL: только SELECT, запрет опасных функций (`file/url/remote/s3/...`), проверка `allowed_tables`, инъекция `WHERE client_id = X`, авто-`LIMIT`. |
| `app/security.py` | Стабильный ключ Fernet (env `APP_SECRET_ENCRYPTION_KEY` или файл `secrets/.fernet_key`). |
| `app/agent_context.py` | Контекст активного клиента (`tenant_context` / `get_current_tenant`). |
| `app/agents/data_agent.py` | Перед выполнением SQL: `secure_sql(...)` + маршрутизация в ClickHouse клиента. |
| `app/orchestrator.py` | Резолв клиента по claim `client_id` из JWT, установка `tenant_context`. |
| `scripts/build_tenant.py` | Автосборка клиента: Postgres (RO) → DDL/слепок → docker ClickHouse → перелив → семантика → регистрация. |
| `docker-compose.tenant.template.yml` | Шаблон персонального ClickHouse-контейнера. |

## Изоляция доступов (SQL guard)

```python
from core.sql_guard import secure_sql
secure_sql("SELECT * FROM sales", tenant=tenant)
# -> "SELECT * FROM sales WHERE client_id = 'pivzavod' LIMIT 500"
```

- Любая операция кроме `SELECT` (`DROP/DELETE/INSERT/UPDATE/ALTER/TRUNCATE/...`) отклоняется.
- Доступ только к таблицам из `allowed_tables` клиента.
- При `enforce_client_id=true` во все SELECT жёстко добавляется `WHERE client_id = <value>`.

## Сборка нового клиента

```bash
# Предпросмотр (без выполнения)
python scripts/build_tenant.py \
  --client-id pivzavod --name "Пивзавод" \
  --pg-dsn "postgresql://ro_user:pwd@db.client:5432/erp" \
  --tables sales,products --ch-port 8201 --add-client-id --dry-run

# Реальная сборка (поднимет контейнер, перельёт данные, зарегистрирует клиента)
python scripts/build_tenant.py \
  --client-id pivzavod --name "Пивзавод" \
  --pg-dsn "postgresql://ro_user:pwd@db.client:5432/erp" \
  --tables sales,products --ch-port 8201 --ch-password "<pwd>" --add-client-id
```

Скрипт выведет `JWT token` и `api_key` клиента — они выдаются конечному клиенту
для доступа к платформе (claim `client_id` в JWT привязывает все запросы к его БД).

## Админ-панель

Вкладка **«Клиенты (B2B)»** в системном центре управления: создание клиента,
просмотр конфигурации, перевыпуск токена, удаление.
API: `GET/POST /api/v1/admin/tenants`, `POST /api/v1/admin/tenants/{id}/rotate-token`,
`DELETE /api/v1/admin/tenants/{id}`.

## Модель развёртывания

- **SaaS**: один backend, общий или персональный ClickHouse на клиента, изоляция через
  `client_id` + `allowed_tables` + личные коллекции семантики.
- **On-Premise**: `build_tenant.py` + `docker-compose.tenant.template.yml` позволяют
  собрать автономный образ клиента во внутреннем контуре.
