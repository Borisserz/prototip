# secrets/

Сюда положите ключ сервис-аккаунта GCP для Vertex AI:

    secrets/gcp.json

Этот файл **не коммитится** (см. .gitignore) и монтируется в backend-контейнер как
`/app/secrets/gcp.json` (read-only).

## Как включить Vertex
В `.env`:

    USE_VERTEX=true
    AI_MODEL=gemini-3.5-flash
    GOOGLE_APPLICATION_CREDENTIALS=/app/secrets/gcp.json

Затем `docker compose up -d backend`. При `USE_VERTEX=false` используется локальная Ollama.

Сервис-аккаунту нужна роль **Vertex AI User** (`roles/aiplatform.user`) в соответствующем проекте.
