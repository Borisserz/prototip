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
