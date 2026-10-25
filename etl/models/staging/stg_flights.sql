-- Staging model: doc du lieu tho tu CSV, ep kieu va dan xuat cac cot nghiep vu
{{ config(materialized='view') }}

WITH raw_flights AS (
    SELECT *
    FROM read_csv_auto('../data/flights_2015_2018.csv', ignore_errors=true)
)

SELECT
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
    
    CASE
        WHEN CRS_DEP_TIME < 600 THEN 'Early Morning'
        WHEN CRS_DEP_TIME < 1200 THEN 'Morning'
        WHEN CRS_DEP_TIME < 1800 THEN 'Afternoon'
        ELSE 'Evening'
    END AS time_block,
    
    CASE
        WHEN EXTRACT(MONTH FROM CAST(FL_DATE AS DATE)) IN (1, 2, 3) THEN 'Winter'
        WHEN EXTRACT(MONTH FROM CAST(FL_DATE AS DATE)) IN (4, 5, 6) THEN 'Spring'
        WHEN EXTRACT(MONTH FROM CAST(FL_DATE AS DATE)) IN (7, 8, 9) THEN 'Summer'
        ELSE 'Autumn'
    END AS season,
    
    CASE
        WHEN DISTANCE < 250 THEN 'G01'
        WHEN DISTANCE < 500 THEN 'G02'
        WHEN DISTANCE < 750 THEN 'G03'
        WHEN DISTANCE < 1000 THEN 'G04'
        WHEN DISTANCE < 1250 THEN 'G05'
        WHEN DISTANCE < 1500 THEN 'G06'
        WHEN DISTANCE < 1750 THEN 'G07'
        WHEN DISTANCE < 2000 THEN 'G08'
        WHEN DISTANCE < 2250 THEN 'G09'
        WHEN DISTANCE < 2500 THEN 'G10'
        ELSE 'G11'
    END AS distance_group,
    
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
    
    CAST(COALESCE(CARRIER_DELAY, 0) AS REAL) AS carrier_delay,
    CAST(COALESCE(WEATHER_DELAY, 0) AS REAL) AS weather_delay,
    CAST(COALESCE(NAS_DELAY, 0) AS REAL) AS nas_delay,
    CAST(COALESCE(SECURITY_DELAY, 0) AS REAL) AS security_delay,
    CAST(COALESCE(LATE_AIRCRAFT_DELAY, 0) AS REAL) AS late_aircraft_delay

FROM raw_flights
