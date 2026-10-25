-- Kiem tra rang buoc logic: so chuyen tre khong duoc vuot qua so chuyen du dieu kien
SELECT *
FROM {{ ref('mart_base') }}
WHERE delayed_flights > eligible_flights
