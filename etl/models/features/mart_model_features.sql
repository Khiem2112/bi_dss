-- Feature mart cho DSS: tap dac trung + nhan de huan luyen/kiem thu mo hinh du bao tre chuyen.
-- Chi gom WN (case study chinh, theo mục 1.6 Project Scope), chi gom cot pre-flight-safe
-- (khong dua ARR_DELAY, delay cause, dep_time, is_delayed... vao de tranh data leakage - SC2).
-- Chia tap theo thoi gian (khong random split) de mo phong dung dieu kien du bao thuc te:
--   train      = 2015-2016 (hoc mua vu, du lieu lon nhat)
--   validation = 2017      (chon nguong calibration / baseline du bao - SC7)
--   test       = 2018      (danh gia cuoi cung, khong dung de tinh chinh bat ky thong so nao)
{{ config(materialized='table') }}

SELECT
    flight_key,
    flight_date,
    carrier,

    EXTRACT(YEAR FROM flight_date)::INTEGER AS year,
    EXTRACT(QUARTER FROM flight_date)::INTEGER AS quarter,
    EXTRACT(MONTH FROM flight_date)::INTEGER AS month,
    day_of_week,
    season,
    time_block,

    origin,
    destination,
    route_key,
    distance,
    distance_group,

    is_eligible,
    delay_outcome,

    CASE
        WHEN EXTRACT(YEAR FROM flight_date) IN (2015, 2016) THEN 'train'
        WHEN EXTRACT(YEAR FROM flight_date) = 2017 THEN 'validation'
        WHEN EXTRACT(YEAR FROM flight_date) = 2018 THEN 'test'
    END AS dataset_split

FROM {{ ref('fact_flight') }}
WHERE carrier = 'WN'
  AND is_eligible = 1
