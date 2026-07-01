# Phase 9 — кастомный образ Airflow для ETL-оркестрации.
# Расширяет официальный apache/airflow зависимостями, нужными DAG'ам
# (clickhouse-connect, psycopg2, langchain, sentence-transformers, парсеры docs).
#
# Backend-код монтируется томом в /opt/airflow/backend (см. docker-compose, профиль etl)
# и добавлен в PYTHONPATH — DAG'и импортируют app.etl / scripts / core напрямую.
FROM apache/airflow:2.9.1

USER root
# системные либы для psycopg2 / sentence-transformers
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow
COPY requirements-airflow.txt /requirements-airflow.txt
RUN pip install --no-cache-dir -r /requirements-airflow.txt

# backend-код виден DAG'ам как пакеты app.* / scripts.* / core.*
ENV PYTHONPATH="/opt/airflow/backend:${PYTHONPATH}"
ENV BACKEND_ROOT="/opt/airflow/backend"
