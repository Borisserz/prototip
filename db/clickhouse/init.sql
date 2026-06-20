CREATE DATABASE IF NOT EXISTS default;

USE default;

CREATE TABLE IF NOT EXISTS default.tax_data
(
    period Date COMMENT 'Месяц (первое число месяца)',
    region LowCardinality(String) COMMENT 'Регион РБ',
    tax_type LowCardinality(String) COMMENT 'Вид налога',
    accrued Float64 COMMENT 'Начислено, Br',
    paid Float64 COMMENT 'Уплачено, Br',
    debt Float64 COMMENT 'Задолженность, Br',
    taxpayers UInt32 COMMENT 'Число налогоплательщиков',
    penalties Float64 COMMENT 'Штрафы и пени, Br'
)
ENGINE = MergeTree()
PARTITION BY toYear(period)
ORDER BY (region, tax_type, period)
SETTINGS index_granularity = 8192;

-- Оптимизация ClickHouse DWH (Materialized Views)
CREATE MATERIALIZED VIEW IF NOT EXISTS default.tax_region_summary_mv
ENGINE = SummingMergeTree()
PARTITION BY toYear(period)
ORDER BY (region, period)
AS SELECT
    period,
    region,
    sum(accrued) AS total_accrued,
    sum(paid) AS total_paid,
    sum(debt) AS total_debt,
    sum(penalties) AS total_penalties
FROM default.tax_data
GROUP BY period, region;


-- ===================== Phase 4: Долгосрочная память =====================
-- Профили пользователей (описание: кто пользователь, чем занимается)
CREATE TABLE IF NOT EXISTS default.user_profiles
(
    user_id    String COMMENT 'Идентификатор пользователя (username из JWT)',
    profile    String COMMENT 'Текстовое описание пользователя',
    role       String DEFAULT '' COMMENT 'Роль/должность',
    updated_at DateTime DEFAULT now() COMMENT 'Время последнего обновления'
)
ENGINE = ReplacingMergeTree(updated_at)
ORDER BY user_id;

-- Журнал истории чата + эмбеддинг запроса (RAG по прошлым запросам пользователя)
CREATE TABLE IF NOT EXISTS default.chat_history_logs
(
    id        String COMMENT 'UUID записи',
    user_id   String COMMENT 'Идентификатор пользователя',
    prompt    String COMMENT 'Запрос пользователя',
    response  String COMMENT 'Ответ системы',
    ts        DateTime DEFAULT now() COMMENT 'Временная метка',
    embedding Array(Float32) COMMENT 'Эмбеддинг запроса (all-MiniLM-L6-v2, 384d)'
)
ENGINE = MergeTree()
ORDER BY (user_id, ts);
