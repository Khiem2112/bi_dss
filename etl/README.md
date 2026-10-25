# Pipeline ETL MotherDuck va dbt cho BI & DSS Dashboard

Pipeline nay xu ly tap du lieu chuyen bay noi dia My giai doan 2015-2018 (~3,01 GB, ~28 trieu dong) tu file goc `data/flights_2015_2018.csv`, bien doi thanh cac bang Dimension, Data Mart va bang chi tiet lam sach, dong bo truc tiep len MotherDuck (DuckDB Cloud).

---

## Cau truc thu muc

```
etl/
├── .env                        # Chuyen connection string va token MotherDuck
├── dbt_project.yml             # Cau hinh dbt project
├── profiles.yml                # Cau hinh profile ket noi MotherDuck va Local DuckDB
├── plan.md                     # Ke hoach tong the va quy tac nghiep vu
├── verify_motherduck.py        # Script doi soat toan ven du lieu truc tiep tren MotherDuck
├── models/
│   ├── staging/
│   │   └── stg_flights.sql     # View doc CSV, ep kieu va dan xuat cac cot
│   ├── dimensions/
│   │   ├── dim_date.sql           # 1.461 ngay (2015-2018)
│   │   ├── dim_carrier.sql        # 19 hang hang khong noi dia My
│   │   ├── dim_airport.sql        # 367 san bay noi dia My
│   │   ├── dim_route.sql          # 6.815 tuyen bay co huong
│   │   ├── dim_scheduled_time.sql # 1.424 gio khoi hanh du kien (DimScheduledTime)
│   │   └── dim_distance_group.sql # 11 nhom cu ly tieu chuan BTS 250 dam
│   ├── marts/
│   │   ├── mart_base.sql          # 939.559 dong tong hop WN 2015-2018 voi 4 additive measures
│   │   ├── mart_delay_causes.sql  # 188.986 dong thong ke 5 nhom nguyen nhan tre
│   │   └── flights_cleaned.sql    # 24.324.804 dong chuyen bay lam sach tat ca cac hang
│   └── schema.yml                 # Rang buoc toan ven va kiem tra gia tri
└── tests/
    ├── assert_delayed_lte_eligible.sql # Kiem tra delayed_flights <= eligible_flights
    └── assert_wn_audit_metrics.sql     # Kiem tra khop cac moc so lieu doi soat chuan
```

---

## Cac bang tren MotherDuck (`my_db`)

| Bang | Phan loai | So dong | Mo ta |
|---|---|---:|---|
| `mart_base` | Data Mart | 939.559 | Grain min nhat (thang, thu, gio, origin, dest, distance_group, season) phuc vu tat ca bieu do WN |
| `mart_delay_causes` | Data Mart | 188.986 | Tong hop 5 nhom nguyen nhan tre cua Southwest Airlines |
| `flights_cleaned` | Fact Table | 24.324.804 | Toan bo chuyen bay 2015-2018 lam sach, phuc vu xem chi tiet va so sanh hang bay doi thu |
| `dim_date` | Dimension | 1.461 | Chi tiet ngay, thang, nam, thu, mua |
| `dim_carrier` | Dimension | 19 | Danh muc 19 hang bay noi dia My kem vai tro phan tich |
| `dim_airport` | Dimension | 367 | Danh muc san bay xuat phat va dich den |
| `dim_route` | Dimension | 6.815 | Danh muc tuyen bay co huong |
| `dim_scheduled_time` | Dimension | 1.424 | Danh muc gio khoi hanh du kien, gio, phut va 4 khung gio ke hoach |
| `dim_distance_group` | Dimension | 11 | 11 nhom cu ly chuan BTS 250 dam (G01 den G11) |

---

## Chi so doi soat thuc te (Khop 100% moc chuan)

| Chi so | Moc chuan | Ket qua tren MotherDuck | Trang thai |
|---|---:|---:|---|
| So ban ghi WN trong flights_cleaned | 5.243.295 | 5.243.295 | Khop tuyet doi |
| Tong chuyen du dieu kien (eligible) | 5.163.515 | 5.163.515 | Khop tuyet doi |
| Tong chuyen tre (delayed >= 15 phut) | 990.810 | 990.810 | Khop tuyet doi |
| Ty le tre toan mang | 19,189% | 19,189% | Khop tuyet doi |
| Tong phut tre den | 23.056.706 | 23.056.706 | Khop tuyet doi |
| So dong vi pham delayed > eligible | 0 | 0 | Khop tuyet doi |

---

## Huong dan chay

### Chay doi soat du lieu

```powershell
python verify_motherduck.py
```

### Chay toan bo bai kiem tra dbt

```powershell
$env:MOTHERDUCK_TOKEN=(Get-Content .env | Where-Object { $_ -match '^MOTHERDUCK_TOKEN=' } | ForEach-Object { $_ -replace '^MOTHERDUCK_TOKEN=', '' })
python -m dbt.cli.main test --profiles-dir .
```

### Chay lai pipeline dbt

```powershell
$env:MOTHERDUCK_TOKEN=(Get-Content .env | Where-Object { $_ -match '^MOTHERDUCK_TOKEN=' } | ForEach-Object { $_ -replace '^MOTHERDUCK_TOKEN=', '' })
python -m dbt.cli.main run --profiles-dir .
```
