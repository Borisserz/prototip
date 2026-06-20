# Backend (FastAPI + LangGraph) — Python 3.11
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные зависимости: kaleido/plotly (PNG экспорт), шрифты, libgomp для numpy/torch
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates libgomp1 libexpat1 fontconfig fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Сначала зависимости (кешируется отдельным слоем)
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Код проекта
COPY . .

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=5 \
    CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
