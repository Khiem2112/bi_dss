-- FactFlight: fact o grain 1 dong = 1 lan xuat hien theo lich cua chuyen bay
-- tren mot chang co huong, vao mot ngay va thoi diem khoi hanh du kien cu the.
-- Noi voi dimension bang surrogate key; thieu khoa -> dung Unknown Member (-1).
{{ config(materialized='table') }}

WITH base AS (
    SELECT
        s.*,
        COUNT(*) OVER (
            PARTITION BY s.flight_date, s.carrier, s.flight_number,
                         s.origin, s.destination, s.crs_dep_time
        ) AS business_key_group_size
    FROM {{ ref('stg_flights') }} s
)

SELECT
    base.source_record_id AS flight_key,
    base.source_record_id,
    base.source_file,
    base.flight_date,
    base.carrier,
    base.flight_number,
    base.origin,
    base.destination,
    base.crs_dep_time,

    CAST(strftime(base.flight_date, '%Y%m%d') AS INTEGER) AS date_key,
    COALESCE(dc.carrier_key, -1) AS carrier_key,
    COALESCE(do_.airport_key, -1) AS origin_airport_key,
    COALESCE(dd.airport_key, -1) AS destination_airport_key,
    COALESCE(dr.route_key, -1) AS route_key,
    COALESCE(dst.scheduled_time_key, -1) AS scheduled_time_key,
    COALESCE(dg.distance_group_key, -1) AS distance_group_key,

    base.year_month,
    base.day_of_week,
    base.time_block,
    base.season,
    base.distance_group,
    base.distance,
    base.arr_delay,
    base.dep_delay,
    base.cancelled,
    base.diverted,
    base.is_eligible,
    base.is_delayed,
    base.delay_outcome,
    base.carrier_delay,
    base.weather_delay,
    base.nas_delay,
    base.security_delay,
    base.late_aircraft_delay,

    base.business_key_group_size > 1 AS business_key_duplicate_flag

FROM base
LEFT JOIN {{ ref('dim_carrier') }} dc ON base.carrier = dc.carrier_code
LEFT JOIN {{ ref('dim_airport') }} do_ ON base.origin = do_.airport_code
LEFT JOIN {{ ref('dim_airport') }} dd ON base.destination = dd.airport_code
LEFT JOIN {{ ref('dim_route') }} dr ON base.origin = dr.origin AND base.destination = dr.destination
LEFT JOIN {{ ref('dim_scheduled_time') }} dst ON base.crs_dep_time = dst.scheduled_time_key
LEFT JOIN {{ ref('dim_distance_group') }} dg ON base.distance_group = dg.distance_group
