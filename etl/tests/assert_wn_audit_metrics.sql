-- Kiem tra doi soat bat buoc cac moc so lieu chuan cua WN 2015-2018
WITH audit AS (
    SELECT
        SUM(eligible_flights) AS total_eligible,
        SUM(delayed_flights) AS total_delayed,
        ROUND(SUM(delayed_flights) * 100.0 / SUM(eligible_flights), 3) AS delay_rate_pct,
        ROUND(SUM(arrival_delay_sum), 0) AS total_delay_min
    FROM {{ ref('mart_base') }}
)
SELECT *
FROM audit
WHERE total_eligible != 5163515
   OR total_delayed != 990810
   OR delay_rate_pct != 19.189
   OR total_delay_min != 23056706
