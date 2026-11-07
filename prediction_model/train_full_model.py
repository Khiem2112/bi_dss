import os
import time
import joblib
import numpy as np
import pandas as pd
import duckdb
from dotenv import load_dotenv

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import lightgbm as lgb
from sklearn.linear_model import LogisticRegression
from sklearn.isotonic import IsotonicRegression
from sklearn.calibration import calibration_curve
from sklearn.metrics import roc_auc_score, average_precision_score, brier_score_loss, roc_curve, precision_recall_curve
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import shap

for p in [".env", "../.env", "etl/.env", "../etl/.env"]:
    if os.path.exists(p):
        load_dotenv(p)
        break

TOKEN = os.getenv("MOTHERDUCK_TOKEN")
OUTPUT_DIR = "prediction_model/output"
MODELS_DIR = "prediction_model/models"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

print("Ket noi MotherDuck...")
con = duckdb.connect(f"md:my_db?motherduck_token={TOKEN}", read_only=True)

# Query tao bang dac trung chuan hoa pre-flight khong leakage
# Toan bo dac trung lich su (route, origin, dest) chi duoc tinh tren tap train (2015-2016)
base_feature_query = """
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
    m.flight_date,
    m.dataset_split,
    m.year,
    m.quarter,
    m.month,
    m.day_of_week,
    m.season,
    m.time_block,
    m.origin,
    m.destination,
    m.route_key,
    m.distance,
    m.distance_group,
    COALESCE(r.route_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS route_hist_delay_rate,
    COALESCE(o.origin_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS origin_hist_delay_rate,
    COALESCE(d.dest_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS dest_hist_delay_rate,
    COALESCE(r.route_flight_count, 0) AS route_hist_flight_count,
    m.delay_outcome
FROM mart_model_features m
LEFT JOIN route_stats r ON m.route_key = r.route_key
LEFT JOIN origin_stats o ON m.origin = o.origin
LEFT JOIN dest_stats d ON m.destination = d.destination
WHERE m.dataset_split = '{split}'
LIMIT {limit}
"""

print("Dang trich xuat du lieu tu MotherDuck...")
t0 = time.time()
train_df = con.execute(base_feature_query.format(split='train', limit=400000)).fetchdf()
val_df = con.execute(base_feature_query.format(split='validation', limit=150000)).fetchdf()
test_df = con.execute(base_feature_query.format(split='test', limit=150000)).fetchdf()
con.close()
print(f"Trich xuat hoan tat sau {time.time()-t0:.2f}s:")
print(f"Train: {len(train_df):,} | Val: {len(val_df):,} | Test: {len(test_df):,}")

# Danh sach dac trung
FEATURES = [
    "month",
    "day_of_week",
    "quarter",
    "time_block_code",
    "distance",
    "route_hist_delay_rate",
    "origin_hist_delay_rate",
    "dest_hist_delay_rate",
    "route_hist_flight_count"
]

time_block_map = {"Early Morning": 0, "Morning": 1, "Afternoon": 2, "Evening": 3}
for df in [train_df, val_df, test_df]:
    df["time_block_code"] = df["time_block"].map(time_block_map).fillna(1).astype(int)

X_train, y_train = train_df[FEATURES], train_df["delay_outcome"]
X_val, y_val = val_df[FEATURES], val_df["delay_outcome"]
X_test, y_test = test_df[FEATURES], test_df["delay_outcome"]

baseline_train_rate = y_train.mean()
print(f"Ty le tre co so (train mean): {baseline_train_rate:.4f}")

# Model 1: Baseline Constant
y_pred_base_val = np.full(len(y_val), baseline_train_rate)
y_pred_base_test = np.full(len(y_test), baseline_train_rate)

# Model 2: Logistic Regression (POC Baseline)
poc_cat_features = ["season", "time_block", "distance_group"]
poc_num_features = ["quarter", "month", "day_of_week", "distance"]
poc_preprocessor = ColumnTransformer(
    transformers=[("cat", OneHotEncoder(handle_unknown="ignore"), poc_cat_features)],
    remainder="passthrough"
)
poc_pipeline = Pipeline([
    ("prep", poc_preprocessor),
    ("clf", LogisticRegression(max_iter=1000))
])
print("Dang huan luyen Logistic Regression (POC)...")
poc_pipeline.fit(train_df[poc_cat_features + poc_num_features], y_train)
y_pred_lr_val = poc_pipeline.predict_proba(val_df[poc_cat_features + poc_num_features])[:, 1]
y_pred_lr_test = poc_pipeline.predict_proba(test_df[poc_cat_features + poc_num_features])[:, 1]

# Model 3: LightGBM Classifier voi Monotonic Constraints
# Rang buoc don dieu: time_block (+1), route_hist (+1), origin_hist (+1)
monotonic_constraints = [0, 0, 0, 1, 0, 1, 1, 0, 0]
lgb_model = lgb.LGBMClassifier(
    n_estimators=250,
    learning_rate=0.05,
    num_leaves=31,
    random_state=42,
    monotone_constraints=monotonic_constraints,
    verbose=-1
)
print("Dang huan luyen LightGBM voi Monotonic Constraints...")
lgb_model.fit(X_train, y_train)
y_pred_lgb_val = lgb_model.predict_proba(X_val)[:, 1]
y_pred_lgb_test = lgb_model.predict_proba(X_test)[:, 1]

# Model 4: Calibrated LightGBM (Isotonic Regression tren tap Validation)
print("Dang hieu chinh xac suat bang Isotonic Regression tren tap Validation...")
isotonic_calibrator = IsotonicRegression(out_of_bounds="clip")
isotonic_calibrator.fit(y_pred_lgb_val, y_val)
y_pred_cal_val = isotonic_calibrator.predict(y_pred_lgb_val)
y_pred_cal_test = isotonic_calibrator.predict(y_pred_lgb_test)

# Tinh toan Expected Calibration Error (ECE)
def calculate_ece(y_true, y_prob, n_bins=10):
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        in_bin = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i + 1])
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    return ece

# Danh gia metrics tren Test set
models_dict = {
    "Baseline (Constant)": y_pred_base_test,
    "Logistic Regression (POC)": y_pred_lr_test,
    "LightGBM (Tho)": y_pred_lgb_test,
    "LightGBM Calibrated (Chinh thuc)": y_pred_cal_test
}

results_list = []
for name, y_prob in models_dict.items():
    auc = roc_auc_score(y_test, y_prob) if name != "Baseline (Constant)" else 0.5000
    pr_auc = average_precision_score(y_test, y_prob)
    brier = brier_score_loss(y_test, y_prob)
    ece = calculate_ece(y_test.values, y_prob, n_bins=10)
    
    # Precision@K tren Test set
    top_50_idx = np.argsort(y_prob)[-50:]
    prec_at_50 = y_test.iloc[top_50_idx].mean()
    top_100_idx = np.argsort(y_prob)[-100:]
    prec_at_100 = y_test.iloc[top_100_idx].mean()
    top_500_idx = np.argsort(y_prob)[-500:]
    prec_at_500 = y_test.iloc[top_500_idx].mean()
    
    # Top Decile Lift
    top_10pct_n = int(0.10 * len(y_prob))
    top_10pct_idx = np.argsort(y_prob)[-top_10pct_n:]
    prec_top_10pct = y_test.iloc[top_10pct_idx].mean()
    lift_10pct = prec_top_10pct / baseline_train_rate
    
    results_list.append({
        "Model": name,
        "ROC-AUC": round(auc, 4),
        "PR-AUC": round(pr_auc, 4),
        "Brier Score": round(brier, 4),
        "ECE": round(ece, 4),
        "Precision@50": round(prec_at_50, 4),
        "Precision@100": round(prec_at_100, 4),
        "Precision@500": round(prec_at_500, 4),
        "Top-10% Lift": round(lift_10pct, 2)
    })

results_df = pd.DataFrame(results_list)
print("\n===== BANG KET QUA SO SANH CAC MO HINH TREN TAP TEST 2018 =====")
print(results_df.to_string(index=False))
results_df.to_csv(f"{OUTPUT_DIR}/model_comparison_results.csv", index=False)

# Luu model artifact
model_bundle = {
    "lgb_model": lgb_model,
    "calibrator": isotonic_calibrator,
    "features": FEATURES,
    "train_mean": baseline_train_rate
}
joblib.dump(model_bundle, f"{MODELS_DIR}/full_lgbm_calibrated.joblib")
print(f"\nDa luu model vao {MODELS_DIR}/full_lgbm_calibrated.joblib")

# Bieu do 1: Calibration Comparison
plt.figure(figsize=(7, 6))
plt.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Hieu chuan hoan hao (Perfect)")
for name, y_prob in [
    ("Logistic Regression", y_pred_lr_test),
    ("LightGBM Tho", y_pred_lgb_test),
    ("LightGBM Calibrated", y_pred_cal_test)
]:
    prob_true, prob_pred = calibration_curve(y_test, y_prob, n_bins=10, strategy="quantile")
    plt.plot(prob_pred, prob_true, marker="o", label=f"{name}")
plt.axhline(baseline_train_rate, linestyle=":", color="red", label=f"Baseline ({baseline_train_rate:.3f})")
plt.xlabel("Xac suat du bao trung binh moi bin (Predicted Probability)")
plt.ylabel("Ty le tre thuc te quan sat (Observed Delay Rate)")
plt.title("So Sanh Hieu Chuan Xac Suat Tren Tap Test 2018")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/calibration_comparison.png", dpi=150)
plt.close()

# Bieu do 2: ROC and PR Curves
plt.figure(figsize=(12, 5))
plt.subplot(1, 2, 1)
for name, y_prob in [("Logistic (POC)", y_pred_lr_test), ("LightGBM Calibrated", y_pred_cal_test)]:
    fpr, tpr, _ = roc_curve(y_test, y_prob)
    auc_val = roc_auc_score(y_test, y_prob)
    plt.plot(fpr, tpr, label=f"{name} (AUC = {auc_val:.3f})")
plt.plot([0, 1], [0, 1], "k--", label="Ngau nhien (0.50)")
plt.xlabel("Ty le duong tinh gia (FPR)")
plt.ylabel("Ty le duong tinh that (TPR)")
plt.title("Duong Cong ROC (Test 2018)")
plt.legend()

plt.subplot(1, 2, 2)
for name, y_prob in [("Logistic (POC)", y_pred_lr_test), ("LightGBM Calibrated", y_pred_cal_test)]:
    prec, rec, _ = precision_recall_curve(y_test, y_prob)
    pr_auc_val = average_precision_score(y_test, y_prob)
    plt.plot(rec, prec, label=f"{name} (PR-AUC = {pr_auc_val:.3f})")
plt.axhline(y_test.mean(), color="red", linestyle=":", label=f"No-skill baseline ({y_test.mean():.3f})")
plt.xlabel("Do phu (Recall)")
plt.ylabel("Do chinh xac (Precision)")
plt.title("Duong Cong Precision-Recall (Test 2018)")
plt.legend()
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/roc_pr_curves.png", dpi=150)
plt.close()

# Tinh toan SHAP Values giai thich mo hinh
print("Dang tinh toan TreeSHAP values...")
explainer = shap.TreeExplainer(lgb_model)
sample_test = X_test.iloc[:5000]
shap_values = explainer.shap_values(sample_test)
if isinstance(shap_values, list):
    shap_vals = shap_values[1]
else:
    shap_vals = shap_values

# Tong hop SHAP theo 3 nhom giai thich cho DSS
# Schedule: month, day_of_week, quarter, time_block_code
# RouteHist: route_hist_delay_rate, distance, route_hist_flight_count
# Congestion: origin_hist_delay_rate, dest_hist_delay_rate
feat_idx = {f: i for i, f in enumerate(FEATURES)}
sched_idx = [feat_idx["month"], feat_idx["day_of_week"], feat_idx["quarter"], feat_idx["time_block_code"]]
route_idx = [feat_idx["route_hist_delay_rate"], feat_idx["distance"], feat_idx["route_hist_flight_count"]]
cong_idx = [feat_idx["origin_hist_delay_rate"], feat_idx["dest_hist_delay_rate"]]

contrib_schedule = np.sum(shap_vals[:, sched_idx], axis=1)
contrib_route = np.sum(shap_vals[:, route_idx], axis=1)
contrib_congestion = np.sum(shap_vals[:, cong_idx], axis=1)

# Bieu do 3: Feature Importance Tornado
mean_abs_shap = np.abs(shap_vals).mean(axis=0)
feat_series = pd.Series(mean_abs_shap, index=FEATURES).sort_values(ascending=True)

plt.figure(figsize=(8, 5))
feat_series.plot(kind="barh", color="#1f77b4")
plt.xlabel("Gia tri SHAP tuyet doi trung binh (|SHAP value|)")
plt.title("Do Quan Trong Dac Trung Giai Thich Bang TreeSHAP")
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/shap_tornado.png", dpi=150)
plt.close()

# Xuat bang FactPrediction cho DSS Dashboard
scored_sample = test_df.iloc[:5000].copy()
cal_probs_sample = y_pred_cal_test[:5000]

scored_sample["PredictedDelayProbability"] = np.round(cal_probs_sample, 4)
scored_sample["RiskBand"] = np.where(
    cal_probs_sample >= 0.40, "Cao",
    np.where(cal_probs_sample >= 0.20, "Trung bình", "Thấp")
)

scored_sample["FeatureContributionSchedule"] = np.round(contrib_schedule, 4)
scored_sample["FeatureContributionRouteHist"] = np.round(contrib_route, 4)
scored_sample["FeatureContributionCongestion"] = np.round(contrib_congestion, 4)

# Quy tac danh gia PriorityReviewStatus
scored_sample["PriorityReviewStatus"] = np.where(
    scored_sample["route_hist_flight_count"] < 30, "Chưa đủ bằng chứng",
    np.where(
        (scored_sample["PredictedDelayProbability"] >= 0.40) & 
        (scored_sample["route_hist_delay_rate"] >= baseline_train_rate),
        "Ưu tiên xem xét",
        "Tiếp tục theo dõi"
    )
)

# Chuan hoa cot phu hop FactPrediction Star Schema
scored_sample["PredictionID"] = np.arange(1000001, 1000001 + len(scored_sample))
scored_sample["DateKey"] = pd.to_datetime(scored_sample["flight_date"]).dt.strftime("%Y%m%d").astype(int)
scored_sample["ModelVersion"] = "LGBM-CAL-v1.0"
scored_sample["ScoringTimestamp"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

out_cols = [
    "PredictionID", "flight_key", "DateKey", "route_key", "origin", "destination",
    "time_block", "distance", "PredictedDelayProbability", "RiskBand",
    "FeatureContributionSchedule", "FeatureContributionRouteHist", "FeatureContributionCongestion",
    "PriorityReviewStatus", "ModelVersion", "ScoringTimestamp"
]

scored_sample[out_cols].to_csv(f"{OUTPUT_DIR}/fact_prediction_output.csv", index=False)
print(f"Da xuat bang FactPrediction mau ({len(scored_sample):,} ban ghi) vao {OUTPUT_DIR}/fact_prediction_output.csv")

# Bieu do 4: Risk Ranking Distribution & Lift
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
risk_counts = scored_sample["RiskBand"].value_counts()
colors = ["#d62728", "#ff7f0e", "#2ca02c"]
risk_counts.plot(kind="bar", color=colors)
plt.ylabel("So luong chuyen bay")
plt.title("Phan Bo Chuyen Bay Theo RiskBand")
plt.xticks(rotation=0)

plt.subplot(1, 2, 2)
status_counts = scored_sample["PriorityReviewStatus"].value_counts()
status_counts.plot(kind="bar", color=["#1f77b4", "#aec7e8", "#c7c7c7"])
plt.ylabel("So luong chuyen bay")
plt.title("Phan Bo PriorityReviewStatus")
plt.xticks(rotation=15)
plt.tight_layout()
plt.savefig(f"{OUTPUT_DIR}/risk_ranking_lift.png", dpi=150)
plt.close()

print("\nHoan tat toan bo qua trinh huan luyen, hieu chuan va xuat ket qua!")
