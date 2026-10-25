-- Bang chieu thoi gian: 1.461 ngay tu 2015-01-01 den 2018-12-31
{{ config(materialized='table') }}

WITH date_spine AS (
    SELECT CAST('2015-01-01' AS DATE) + INTERVAL (n) DAY AS flight_date
    FROM generate_series(0, 1460) AS t(n)
)

SELECT
    flight_date,
    EXTRACT(YEAR FROM flight_date)::INTEGER AS year,
    EXTRACT(MONTH FROM flight_date)::INTEGER AS month,
    strftime(flight_date, '%Y-%m') AS year_month,
    EXTRACT(DAY FROM flight_date)::INTEGER AS day_of_month,
    isodow(flight_date) AS day_of_week,
    CASE isodow(flight_date)
        WHEN 1 THEN 'Thứ Hai'
        WHEN 2 THEN 'Thứ Ba'
        WHEN 3 THEN 'Thứ Tư'
        WHEN 4 THEN 'Thứ Năm'
        WHEN 5 THEN 'Thứ Sáu'
        WHEN 6 THEN 'Thứ Bảy'
        WHEN 7 THEN 'Chủ Nhật'
    END AS day_of_week_vi,
    CASE
        WHEN EXTRACT(MONTH FROM flight_date) IN (1, 2, 3) THEN 'Winter'
        WHEN EXTRACT(MONTH FROM flight_date) IN (4, 5, 6) THEN 'Spring'
        WHEN EXTRACT(MONTH FROM flight_date) IN (7, 8, 9) THEN 'Summer'
        ELSE 'Autumn'
    END AS season,
    CASE
        WHEN EXTRACT(MONTH FROM flight_date) IN (1, 2, 3) THEN 'Mùa đông'
        WHEN EXTRACT(MONTH FROM flight_date) IN (4, 5, 6) THEN 'Mùa xuân'
        WHEN EXTRACT(MONTH FROM flight_date) IN (7, 8, 9) THEN 'Mùa hè'
        ELSE 'Mùa thu'
    END AS season_vi
FROM date_spine
