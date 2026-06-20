# ClickHouse с предзагруженной схемой (db/clickhouse/init.sql).
# init.sql выполняется автоматически при ПЕРВОМ старте пустого тома.
FROM clickhouse/clickhouse-server:latest

COPY clickhouse/init.sql /docker-entrypoint-initdb.d/10-init.sql

# Порты: 8123 (HTTP), 9000 (native)
EXPOSE 8123 9000
