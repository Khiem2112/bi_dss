import os
import time
import duckdb
from dotenv import load_dotenv

for p in [".env", "../.env", "etl/.env", "../etl/.env"]:
    if os.path.exists(p):
        load_dotenv(p)
        break

token = os.getenv("MOTHERDUCK_TOKEN")
print("Dang ket noi MotherDuck...")
t0 = time.time()
con = duckdb.connect(f"md:my_db?motherduck_token={token}", read_only=True)
print(f"Ket noi thanh cong sau {time.time()-t0:.2f}s")

t0 = time.time()
print("Kiem tra so luong ban ghi theo split trong mart_model_features...")
res = con.execute("""
    SELECT dataset_split, count(*) as n, round(avg(delay_outcome), 4) as delay_rate
    FROM mart_model_features
    GROUP BY dataset_split
    ORDER BY dataset_split
""").fetchall()
for row in res:
    print(f"Split: {row[0]} | So ban ghi: {row[1]:,} | Ty le tre: {row[2]:.4f}")
print(f"Thuc hien xong sau {time.time()-t0:.2f}s")

con.close()

