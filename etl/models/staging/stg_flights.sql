-- Staging model: doc du lieu tho tu CSV, ep kieu va dan xuat cac cot nghiep vu
{{ config(materialized='view') }}

WITH raw_flights AS (
    SELECT
        ROW_NUMBER() OVER () AS source_record_id,
        *
    FROM read_csv_auto(
        ['../data/2015.csv', '../data/2016.csv', '../data/2017.csv', '../data/2018.csv'],
        ignore_errors=true,
        union_by_name=true,
        filename=true
    )
)

SELECT
    source_record_id,
    filename AS source_file,
    CAST(FL_DATE AS DATE) AS flight_date,
    TRIM(OP_CARRIER) AS carrier,
    CAST(OP_CARRIER_FL_NUM AS VARCHAR) AS flight_number,
    TRIM(ORIGIN) AS origin,
    TRIM(DEST) AS destination,
    CAST(CRS_DEP_TIME AS INTEGER) AS crs_dep_time,
    CAST(DEP_TIME AS REAL) AS dep_time,
    CAST(DEP_DELAY AS REAL) AS dep_delay,
    CAST(ARR_DELAY AS REAL) AS arr_delay,
    CAST(COALESCE(CANCELLED, 0) AS INTEGER) AS cancelled,
    CAST(COALESCE(DIVERTED, 0) AS INTEGER) AS diverted,
    CAST(DISTANCE AS REAL) AS distance,
    
    strftime(CAST(FL_DATE AS DATE), '%Y-%m') AS year_month,
    isodow(CAST(FL_DATE AS DATE)) AS day_of_week,
    
    {{ time_block_expr('CRS_DEP_TIME') }} AS time_block,

    {{ season_expr('EXTRACT(MONTH FROM CAST(FL_DATE AS DATE))') }} AS season,

    {{ distance_group_expr('DISTANCE') }} AS distance_group,
    
    CASE
        WHEN COALESCE(CANCELLED, 0) = 0
         AND COALESCE(DIVERTED, 0) = 0
         AND ARR_DELAY IS NOT NULL
        THEN 1
        ELSE 0
    END AS is_eligible,
    
    CASE
        WHEN COALESCE(CANCELLED, 0) = 0
         AND COALESCE(DIVERTED, 0) = 0
         AND ARR_DELAY IS NOT NULL
         AND ARR_DELAY >= 15
        THEN 1
        ELSE 0
    END AS is_delayed,

    -- DelayOutcome dung ngu nghia NULL rieng, khac is_delayed (0/1 dung de SUM cho KPI):
    -- NULL khi khong xac dinh duoc ket qua den (thieu ARR_DELAY), tranh bi hieu nham la dung gio.
    CASE
        WHEN ARR_DELAY IS NULL THEN NULL
        WHEN ARR_DELAY >= 15 THEN 1
        ELSE 0
    END AS delay_outcome,

    CAST(COALESCE(CARRIER_DELAY, 0) AS REAL) AS carrier_delay,
    CAST(COALESCE(WEATHER_DELAY, 0) AS REAL) AS weather_delay,
    CAST(COALESCE(NAS_DELAY, 0) AS REAL) AS nas_delay,
    CAST(COALESCE(SECURITY_DELAY, 0) AS REAL) AS security_delay,
    CAST(COALESCE(LATE_AIRCRAFT_DELAY, 0) AS REAL) AS late_aircraft_delay

FROM raw_flights
