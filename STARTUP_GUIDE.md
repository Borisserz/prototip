## 1. Базовый стек (Ядро)
Поднимает основную логику: Frontend, Backend, ClickHouse (БД) и MinIO (S3 хранилище).

```bash
docker compose up -d
```
*(Для пересборки добавьте флаг `--build`: `docker compose up -d --build`)*

## 2. ETL и процессы (Airflow)
Поднимает инструменты для работы с процессами данных: Apache Airflow и PostgreSQL для него.

```bash
docker compose --profile etl up -d
```

## 3. Мониторинг (Observability)
Поднимает систему мониторинга: Grafana (дашборды) и Prometheus (сбор метрик).

```bash
docker compose --profile observability up -d
```

## 4. Запуск всего проекта целиком
Если вам нужно поднять вообще все сервисы разом (Ядро + ETL + Мониторинг):

```bash
docker compose --profile etl --profile observability up -d
```

## 5. Локальная нейросеть (Ollama) - Опционально
Если вы не используете Vertex AI/Gemini, а хотите запускать ИИ локально:

```bash
docker compose --profile ollama up -d
```
## 6. Доступ к сервисам (Порты)

После запуска вы можете получить доступ к сервисам по следующим адресам (на `localhost`):

| Сервис | Порт | Ссылка | Описание / Учетные данные |
| :--- | :--- | :--- | :--- |
| **Frontend** | `3000` | [http://localhost:3000](http://localhost:3000) | Пользовательский веб-интерфейс |
| **Backend API** | `8000` | [http://localhost:8000/docs](http://localhost:8000/docs) | REST API (Swagger UI) |
| **ClickHouse** | `8123` | `localhost:8123` | База данных (native порт `9000`) |
| **MinIO Console** | `9101` | [http://localhost:9101](http://localhost:9101) | Веб-консоль S3-хранилища (admin/admin) |
| **MinIO API** | `9100` | [http://localhost:9100](http://localhost:9100) | S3 API endpoint |
| **Airflow UI** | `8081` | [http://localhost:8081](http://localhost:8081) | Управление ETL-процессами (admin/admin) |
| **Grafana** | `3001` | [http://localhost:3001](http://localhost:3001) | Дашборды мониторинга (admin/admin) |
| **Prometheus** | `9090` | [http://localhost:9090](http://localhost:9090) | Сборщик метрик |
| **PostgreSQL** | `5434` | `localhost:5434` | База данных для Airflow |
| **Ollama** | `11434`| [http://localhost:11434](http://localhost:11434) | Локальная LLM (опционально) |
| **Keycloak** | `8080` | [http://localhost:8080](http://localhost:8080) | Сервис авторизации (опционально, admin/admin) |

---

### Остановка сервисов
Чтобы остановить конкретный профиль, используйте ту же команду, но с `down`, например:
```bash
docker compose --profile etl down
```
Чтобы остановить абсолютно всё:
```bash
docker compose --profile etl --profile observability --profile ollama down
```
