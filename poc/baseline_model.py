"""
Phase 7 - POC Execution (muc 8.3)
Baseline model cho bai toan du bao Delay Outcome (ArrDelay >= 15 phut) cua Southwest (WN).

Du lieu: mart_model_features (da duoc ETL chuan bi san, chi gom cot pre-flight-safe,
chia theo thoi gian: train=2015-2016, validation=2017, test=2018).

So sanh 2 model theo dung tinh than Phase 7 handbook va SC6/SC7 cua tai lieu du an:
  - Baseline don gian: du doan hang so = ty le tre lich su tren tap train (khong dung feature nao).
  - Model thu nghiem: Logistic Regression voi cac predictor hang muc thap (khong dung
    origin/destination/route vi cardinality qua lon, khong phu hop cho mot baseline POC).

Tieu chi POC (theo Bang 3.5 / SC6 / SC7):
  - ROC-AUC cua model > baseline.
  - Brier score cua model khong cao hon baseline.
  - Co calibration plot kem so quan sat.

Khong dung lam ket luan cuoi cung cho Phase 8 full build - day chi la POC de xac nhan
huong tiep can kha thi truoc khi dau tu day du.
"""
import duckdb
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_auc_score, brier_score_loss
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline

DB_PATH = "../etl/dev_warehouse.duckdb"
OUTPUT_DIR = "output"

# Predictor hang muc thap, pre-flight-safe, tranh high-cardinality (origin/destination/route)
# de giu dung tinh chat "baseline model" cua POC (Phase 8 full build moi can target-encode route).
CATEGORICAL_FEATURES = ["season", "time_block", "distance_group"]
NUMERIC_FEATURES = ["quarter", "month", "day_of_week", "distance"]
TARGET = "delay_outcome"


def load_split(con, split_name):
    query = f"""
        SELECT {", ".join(CATEGORICAL_FEATURES + NUMERIC_FEATURES + [TARGET])}
        FROM mart_model_features
        WHERE dataset_split = '{split_name}'
    """
    return con.execute(query).fetchdf()


def build_pipeline():
    preprocessor = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL_FEATURES),
        ],
        remainder="passthrough",
    )
    return Pipeline(
        steps=[
            ("preprocess", preprocessor),
            ("model", LogisticRegression(max_iter=1000)),
        ]
    )


def evaluate(y_true, y_pred_proba, label):
    auc = roc_auc_score(y_true, y_pred_proba)
    brier = brier_score_loss(y_true, y_pred_proba)
    print(f"[{label}] ROC-AUC = {auc:.4f} | Brier = {brier:.4f} | n = {len(y_true):,}")
    return auc, brier


def main():
    con = duckdb.connect(DB_PATH, read_only=True)

    print("Dang doc du lieu tu mart_model_features...")
    train = load_split(con, "train")
    valid = load_split(con, "validation")
    test = load_split(con, "test")
    con.close()

    X_train, y_train = train[CATEGORICAL_FEATURES + NUMERIC_FEATURES], train[TARGET]
    X_valid, y_valid = valid[CATEGORICAL_FEATURES + NUMERIC_FEATURES], valid[TARGET]
    X_test, y_test = test[CATEGORICAL_FEATURES + NUMERIC_FEATURES], test[TARGET]

    print(f"Train: {len(train):,} dong | Validation: {len(valid):,} dong | Test: {len(test):,} dong")
    print()

    # --- Baseline: hang so = ty le tre lich su tren tap train ---
    baseline_rate = y_train.mean()
    print(f"Baseline (constant) = {baseline_rate:.4f} (ty le tre tren tap train)")

    baseline_pred_valid = np.full(len(y_valid), baseline_rate)
    baseline_pred_test = np.full(len(y_test), baseline_rate)

    # --- Model thu nghiem: Logistic Regression ---
    pipeline = build_pipeline()
    pipeline.fit(X_train, y_train)

    model_pred_valid = pipeline.predict_proba(X_valid)[:, 1]
    model_pred_test = pipeline.predict_proba(X_test)[:, 1]

    print("\n===== KET QUA TREN TAP VALIDATION (dung de chon nguong/calibration) =====")
    evaluate(y_valid, baseline_pred_valid, "Baseline - Validation")
    evaluate(y_valid, model_pred_valid, "LogisticRegression - Validation")

    print("\n===== KET QUA TREN TAP TEST (chi danh gia cuoi cung, khong dung de tinh chinh) =====")
    base_auc_test, base_brier_test = evaluate(y_test, baseline_pred_test, "Baseline - Test")
    model_auc_test, model_brier_test = evaluate(y_test, model_pred_test, "LogisticRegression - Test")

    print("\n===== SO SANH VOI TIEU CHI POC (SC6 / SC7) =====")
    auc_pass = model_auc_test > base_auc_test
    brier_pass = model_brier_test <= base_brier_test
    print(f"ROC-AUC model > baseline?  {'PASS' if auc_pass else 'FAIL'} "
          f"({model_auc_test:.4f} vs {base_auc_test:.4f})")
    print(f"Brier model <= baseline?  {'PASS' if brier_pass else 'FAIL'} "
          f"({model_brier_test:.4f} vs {base_brier_test:.4f})")

    # --- Calibration plot tren tap test ---
    frac_pos, mean_pred = calibration_curve(y_test, model_pred_test, n_bins=10, strategy="quantile")

    plt.figure(figsize=(6, 6))
    plt.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Perfect calibration")
    plt.plot(mean_pred, frac_pos, marker="o", label="LogisticRegression (test)")
    plt.axhline(baseline_rate, linestyle=":", color="orange", label=f"Baseline rate = {baseline_rate:.3f}")
    plt.xlabel("Predicted probability (mean per bin)")
    plt.ylabel("Observed delay rate (fraction positive)")
    plt.title("Calibration Plot - POC Baseline Model (WN, test=2018)")
    plt.legend()
    plt.tight_layout()
    out_path = f"{OUTPUT_DIR}/calibration_plot.png"
    plt.savefig(out_path, dpi=150)
    print(f"\nDa luu calibration plot: {out_path}")

    # --- Xuat bang ket qua CSV de dua vao POC Evaluation Report ---
    results = pd.DataFrame([
        {"model": "Baseline (constant)", "split": "validation",
         "roc_auc": roc_auc_score(y_valid, baseline_pred_valid),
         "brier": brier_score_loss(y_valid, baseline_pred_valid), "n": len(y_valid)},
        {"model": "LogisticRegression", "split": "validation",
         "roc_auc": roc_auc_score(y_valid, model_pred_valid),
         "brier": brier_score_loss(y_valid, model_pred_valid), "n": len(y_valid)},
        {"model": "Baseline (constant)", "split": "test",
         "roc_auc": base_auc_test, "brier": base_brier_test, "n": len(y_test)},
        {"model": "LogisticRegression", "split": "test",
         "roc_auc": model_auc_test, "brier": model_brier_test, "n": len(y_test)},
    ])
    results_path = f"{OUTPUT_DIR}/poc_model_results.csv"
    results.to_csv(results_path, index=False)
    print(f"Da luu bang ket qua: {results_path}")


if __name__ == "__main__":
    main()
