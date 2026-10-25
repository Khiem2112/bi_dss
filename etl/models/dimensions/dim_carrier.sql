-- Bang chieu hang hang khong noi dia My (DimCarrier)
{{ config(materialized='table') }}

WITH carriers AS (
    SELECT DISTINCT carrier AS carrier_code
    FROM {{ ref('stg_flights') }}
    WHERE carrier IS NOT NULL AND carrier != ''
)

SELECT
    ROW_NUMBER() OVER (ORDER BY carrier_code) AS carrier_key,
    carrier_code,
    CASE carrier_code
        WHEN '9E' THEN 'Endeavor Air'
        WHEN 'AA' THEN 'American Airlines Inc.'
        WHEN 'AS' THEN 'Alaska Airlines Inc.'
        WHEN 'B6' THEN 'JetBlue Airways'
        WHEN 'DL' THEN 'Delta Air Lines Inc.'
        WHEN 'EV' THEN 'ExpressJet Airlines LLC'
        WHEN 'F9' THEN 'Frontier Airlines Inc.'
        WHEN 'G4' THEN 'Allegiant Air'
        WHEN 'HA' THEN 'Hawaiian Airlines Inc.'
        WHEN 'MQ' THEN 'Envoy Air'
        WHEN 'NK' THEN 'Spirit Air Lines'
        WHEN 'OH' THEN 'PSA Airlines Inc.'
        WHEN 'OO' THEN 'SkyWest Airlines Inc.'
        WHEN 'UA' THEN 'United Air Lines Inc.'
        WHEN 'US' THEN 'US Airways Inc.'
        WHEN 'VX' THEN 'Virgin America'
        WHEN 'WN' THEN 'Southwest Airlines Co.'
        WHEN 'YV' THEN 'Mesa Airlines Inc.'
        WHEN 'YX' THEN 'Republic Airline'
        ELSE carrier_code
    END AS carrier_name,
    CASE
        WHEN carrier_code = 'WN' THEN 'Hãng phân tích chính'
        WHEN carrier_code IN ('DL', 'AA') THEN 'Hãng tham chiếu'
        ELSE 'Hãng đối thủ khác'
    END AS carrier_role_vi
FROM carriers
ORDER BY carrier_code
