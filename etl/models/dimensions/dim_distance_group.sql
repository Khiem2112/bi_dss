-- Bang chieu nhom cu ly theo tieu chuan BTS 250 dam
{{ config(materialized='table') }}

SELECT * FROM (
    VALUES
        ('G01', 0, 249, '0–249 dặm'),
        ('G02', 250, 499, '250–499 dặm'),
        ('G03', 500, 749, '500–749 dặm'),
        ('G04', 750, 999, '750–999 dặm'),
        ('G05', 1000, 1249, '1.000–1.249 dặm'),
        ('G06', 1250, 1499, '1.250–1.499 dặm'),
        ('G07', 1500, 1749, '1.500–1.749 dặm'),
        ('G08', 1750, 1999, '1.750–1.999 dặm'),
        ('G09', 2000, 2249, '2.000–2.249 dặm'),
        ('G10', 2250, 2499, '2.250–2.499 dặm'),
        ('G11', 2500, 99999, 'Từ 2.500 dặm')
) AS t(distance_group, min_distance, max_distance, label_vi)
