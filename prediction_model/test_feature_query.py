import os
import time
import duckdb
from dotenv import load_dotenv

for p in [".env", "../.env", "etl/.env", "../etl/.env"]:
    if os.path.exists(p):
        load_dotenv(p)
        break

token = os.getenv("MOTHERDUCK_TOKEN")
con = duckdb.connect(f"md:my_db?motherduck_token={token}", read_only=True)

test_query = """
WITH train_stats AS (
    SELECT AVG(delay_outcome) AS global_mean
    FROM mart_model_features
    WHERE dataset_split = 'train'
),
route_stats AS (
    SELECT
        route_key,
        COUNT(*) AS route_flight_count,
        (SUM(delay_outcome) + 50.0 * (SELECT global_mean FROM train_stats)) / (COUNT(*) + 50.0) AS route_hist_delay_rate
    FROM mart_model_features
    WHERE dataset_split = 'train'
    GROUP BY route_key
),
origin_stats AS (
    SELECT
        origin,
        (SUM(delay_outcome) + 100.0 * (SELECT global_mean FROM train_stats)) / (COUNT(*) + 100.0) AS origin_hist_delay_rate
    FROM mart_model_features
    WHERE dataset_split = 'train'
    GROUP BY origin
),
dest_stats AS (
    SELECT
        destination,
        (SUM(delay_outcome) + 100.0 * (SELECT global_mean FROM train_stats)) / (COUNT(*) + 100.0) AS dest_hist_delay_rate
    FROM mart_model_features
    WHERE dataset_split = 'train'
    GROUP BY destination
)
SELECT
    m.flight_key,
    m.dataset_split,
    m.month,
    m.day_of_week,
    m.time_block,
    m.distance,
    COALESCE(r.route_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS route_hist_delay_rate,
    COALESCE(o.origin_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS origin_hist_delay_rate,
    COALESCE(d.dest_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS dest_hist_delay_rate,
    COALESCE(r.route_flight_count, 0) AS route_hist_flight_count,
    m.delay_outcome
FROM mart_model_features m
LEFT JOIN route_stats r ON m.route_key = r.route_key
LEFT JOIN origin_stats o ON m.origin = o.origin
LEFT JOIN dest_stats d ON m.destination = d.destination
WHERE m.dataset_split = 'validation'
LIMIT 10
"""

t0 = time.time()
df = con.execute(test_query).fetchdf()
print(f"Lay thanh cong 10 dong sau {time.time()-t0:.2f}s:")
print(df)
con.close()

