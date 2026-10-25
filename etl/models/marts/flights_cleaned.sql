-- Bang chi tiet tung chuyen bay lam sach cho tat ca cac hang bay (2015-2018)
{{ config(materialized='table') }}

SELECT
    flight_date,
    carrier,
    flight_number,
    origin,
    destination,
    crs_dep_time,
    dep_time,
    dep_delay,
    arr_delay,
    cancelled,
    diverted,
    distance,
    distance_group,
    time_block,
    season,
    day_of_week,
    year_month,
    is_eligible,
    is_delayed,
    carrier_delay,
    weather_delay,
    nas_delay,
    security_delay,
    late_aircraft_delay
FROM {{ ref('stg_flights') }}
