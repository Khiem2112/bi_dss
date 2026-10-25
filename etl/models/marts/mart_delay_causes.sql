-- Bang mart thong ke nguyen nhan tre cua Southwest Airlines (WN) 2015-2018
{{ config(materialized='table') }}

WITH wn_delays AS (
    SELECT
        year_month,
        origin,
        destination,
        carrier_delay,
        weather_delay,
        nas_delay,
        security_delay,
        late_aircraft_delay
    FROM {{ ref('stg_flights') }}
    WHERE carrier = 'WN' AND is_delayed = 1
),

unpivoted AS (
    SELECT year_month, origin, destination, 'Carrier' AS cause, carrier_delay AS delay_minutes
    FROM wn_delays WHERE carrier_delay > 0
    UNION ALL
    SELECT year_month, origin, destination, 'Weather' AS cause, weather_delay AS delay_minutes
    FROM wn_delays WHERE weather_delay > 0
    UNION ALL
    SELECT year_month, origin, destination, 'NAS' AS cause, nas_delay AS delay_minutes
    FROM wn_delays WHERE nas_delay > 0
    UNION ALL
    SELECT year_month, origin, destination, 'Security' AS cause, security_delay AS delay_minutes
    FROM wn_delays WHERE security_delay > 0
    UNION ALL
    SELECT year_month, origin, destination, 'LateAircraft' AS cause, late_aircraft_delay AS delay_minutes
    FROM wn_delays WHERE late_aircraft_delay > 0
)

SELECT
    year_month,
    origin,
    destination,
    cause,
    COUNT(*)::INTEGER AS affected_flights,
    ROUND(SUM(delay_minutes), 2)::REAL AS delay_minutes
FROM unpivoted
GROUP BY year_month, origin, destination, cause
