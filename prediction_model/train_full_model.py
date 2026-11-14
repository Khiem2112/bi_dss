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
from sklearn.metrics import (
    roc_auc_score,
    average_precision_score,
    brier_score_loss,
    roc_curve,
    precision_recall_curve,
)
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
import shap

for p in [".env", "../.env", "etl/.env", "../etl/.env"]:
    if os.path.exists(p):
        load_dotenv(p)
        break

TOKEN = os.getenv("MOTHERDUCK_TOKEN")
SAVE_WEIGHTS = os.getenv("SAVE_WEIGHTS", "false").lower() in ("true", "1", "yes")
OUTPUT_DIR = "prediction_model/output"
MODELS_DIR = "prediction_model/models"
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(MODELS_DIR, exist_ok=True)

TIME_BLOCK_MAP = {"Early Morning": 0, "Morning": 1, "Afternoon": 2, "Evening": 3}

FEATURES = [
    "month",
    "day_of_week",
    "quarter",
    "time_block_code",
    "distance",
    "route_hist_delay_rate",
    "origin_hist_delay_rate",
    "dest_hist_delay_rate",
    "route_hist_flight_count",
]

CATEGORICAL_FEATURES = ["month", "day_of_week", "quarter", "time_block_code"]

# Ty le tre lich su Empirical Bayes tinh tu tap Train (2015-2016) lam moc tham chieu dong bang cho Validation (2017) va Test (2018).
# Rieng tap Train (2015-2016) se duoc ghi de bang compute_temporal_expanding_target_encoding de tranh ro ri du lieu tuong lai.
BASE_FEATURE_QUERY = """
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
    CAST(m.distance AS FLOAT) AS distance,
    m.distance_group,
    CAST(COALESCE(r.route_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS FLOAT) AS route_hist_delay_rate,
    CAST(COALESCE(o.origin_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS FLOAT) AS origin_hist_delay_rate,
    CAST(COALESCE(d.dest_hist_delay_rate, (SELECT global_mean FROM train_stats)) AS FLOAT) AS dest_hist_delay_rate,
    CAST(COALESCE(r.route_flight_count, 0) AS INTEGER) AS route_hist_flight_count,
    CAST(m.delay_outcome AS INTEGER) AS delay_outcome
FROM mart_model_features m
LEFT JOIN route_stats r ON m.route_key = r.route_key
LEFT JOIN origin_stats o ON m.origin = o.origin
LEFT JOIN dest_stats d ON m.destination = d.destination
WHERE m.dataset_split IN ('train', 'validation', 'test')
"""


def compute_temporal_expanding_target_encoding(train_df, m_route=50.0, m_airport=100.0, global_prior=None):
    """
    Tinh toan ty le tre lich su Empirical Bayes theo cua so thoi gian mo rong (Expanding Window) tren tap Train.
    Voi moi ngay bay d, chi tong hop du lieu tu cac chuyen bay dien ra hoan toan truoc ngay d (flight_date < d),
    triet tieu hoan toan look-ahead bias (khong dung tuong lai du bao qua khu) va in-sample leakage (khong dung nhan cua chinh chuyen bay do).
    """
    y = train_df["delay_outcome"].to_numpy(dtype=np.float64)
    global_mean = float(global_prior) if global_prior is not None else float(np.mean(y))

    temporal_df = pd.DataFrame(index=train_df.index)

    for col, m, out_col in [
        ("route_key", m_route, "route_hist_delay_rate"),
        ("origin", m_airport, "origin_hist_delay_rate"),
        ("destination", m_airport, "dest_hist_delay_rate"),
    ]:
        daily = (
            train_df.groupby(["flight_date", col])["delay_outcome"]
            .agg(day_cnt="count", day_sum="sum")
            .reset_index()
            .sort_values("flight_date")
        )

        daily["cum_cnt"] = daily.groupby(col)["day_cnt"].cumsum()
        daily["cum_sum"] = daily.groupby(col)["day_sum"].cumsum()
        daily["prior_cnt"] = daily["cum_cnt"] - daily["day_cnt"]
        daily["prior_sum"] = daily["cum_sum"] - daily["day_sum"]

        daily_indexed = daily.set_index(["flight_date", col])
        key = pd.MultiIndex.from_arrays([train_df["flight_date"], train_df[col]])

        prior_cnt = daily_indexed["prior_cnt"].reindex(key).fillna(0).to_numpy(dtype=np.float64)
        prior_sum = daily_indexed["prior_sum"].reindex(key).fillna(0).to_numpy(dtype=np.float64)

        rate = ((prior_sum + m * global_mean) / (prior_cnt + m)).astype(np.float32)
        temporal_df[out_col] = rate

        if col == "route_key":
            temporal_df["route_hist_flight_count"] = prior_cnt.astype(np.int32)

    return temporal_df


def calculate_ece(y_true, y_prob, n_bins=10):
    """Calculate Expected Calibration Error across equal-width probability bins."""
    bin_boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        if i == n_bins - 1:
            in_bin = (y_prob >= bin_boundaries[i]) & (y_prob <= bin_boundaries[i + 1])
        else:
            in_bin = (y_prob >= bin_boundaries[i]) & (y_prob < bin_boundaries[i + 1])
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    return float(ece)


def main():
    print("Ket noi MotherDuck...")
    t0 = time.time()
    raw_np = None
    for attempt in range(3):
        try:
            con = duckdb.connect(f"md:my_db?motherduck_token={TOKEN}", read_only=True)
            print("Dang trich xuat toan bo tap du lieu WN tu MotherDuck...")
            raw_np = con.execute(BASE_FEATURE_QUERY).fetchnumpy()
            con.close()
            break
        except duckdb.Error as exc:
            print(f"MotherDuck query that bai (lan {attempt + 1}/3): {exc}")
            if attempt == 2:
                raise
            time.sleep(3)

    full_df = pd.DataFrame({
        "flight_key": raw_np["flight_key"].astype(str),
        "flight_date": pd.to_datetime(raw_np["flight_date"]),
        "dataset_split": raw_np["dataset_split"].astype(str),
        "year": raw_np["year"].astype(np.int32),
        "quarter": raw_np["quarter"].astype(np.int32),
        "month": raw_np["month"].astype(np.int32),
        "day_of_week": raw_np["day_of_week"].astype(np.int32),
        "season": raw_np["season"].astype(str),
        "time_block": raw_np["time_block"].astype(str),
        "origin": raw_np["origin"].astype(str),
        "destination": raw_np["destination"].astype(str),
        "route_key": raw_np["route_key"].astype(str),
        "distance": raw_np["distance"].astype(np.float32),
        "distance_group": raw_np["distance_group"].astype(str),
        "route_hist_delay_rate": raw_np["route_hist_delay_rate"].astype(np.float32),
        "origin_hist_delay_rate": raw_np["origin_hist_delay_rate"].astype(np.float32),
        "dest_hist_delay_rate": raw_np["dest_hist_delay_rate"].astype(np.float32),
        "route_hist_flight_count": raw_np["route_hist_flight_count"].astype(np.int32),
        "delay_outcome": raw_np["delay_outcome"].astype(np.int32),
    })
    full_df["time_block_code"] = full_df["time_block"].map(TIME_BLOCK_MAP).fillna(1).astype(np.int32)

    train_df = (
        full_df[full_df["dataset_split"] == "train"]
        .sort_values(["flight_date", "flight_key"], kind="mergesort", ignore_index=True)
    )
    val_df = (
        full_df[full_df["dataset_split"] == "validation"]
        .sort_values(["flight_date", "flight_key"], kind="mergesort", ignore_index=True)
    )
    test_df = (
        full_df[full_df["dataset_split"] == "test"]
        .sort_values(["flight_date", "flight_key"], kind="mergesort", ignore_index=True)
    )
    del raw_np, full_df

    print(f"Trich xuat hoan tat sau {time.time() - t0:.2f}s:")
    print(f"Train: {len(train_df):,} | Val: {len(val_df):,} | Test: {len(test_df):,}")

    y_train = train_df["delay_outcome"].to_numpy()
    y_val = val_df["delay_outcome"].to_numpy()
    y_test = test_df["delay_outcome"].to_numpy()

    baseline_train_rate = float(y_train.mean())
    print(f"Ty le tre co so (train mean): {baseline_train_rate:.4f}")

    # Tinh toan dac trung lich su cho tap Train bang cua so thoi gian mo rong (Expanding Window)
    # Bao dam chi su dung du lieu dien ra truoc ngay bay (flight_date < current_flight_date),
    # loai bo hoan toan look-ahead bias va in-sample leakage.
    print("Dang tinh toan ty le tre lich su mo rong theo thoi gian (Temporal Expanding Lag) cho tap Train...")
    train_temporal_te = compute_temporal_expanding_target_encoding(
        train_df, m_route=50.0, m_airport=100.0, global_prior=baseline_train_rate
    )
    for te_col in ["route_hist_delay_rate", "origin_hist_delay_rate", "dest_hist_delay_rate", "route_hist_flight_count"]:
        train_df[te_col] = train_temporal_te[te_col]

    X_train = train_df[FEATURES].copy()
    X_val = val_df[FEATURES].copy()
    X_test = test_df[FEATURES].copy()

    # Baseline Constant
    y_pred_base_test = np.full(len(y_test), baseline_train_rate)

    # Baseline Logistic Regression (POC specification)
    poc_cat_features = ["season", "time_block", "distance_group"]
    poc_num_features = ["quarter", "month", "day_of_week", "distance"]
    poc_preprocessor = ColumnTransformer(
        transformers=[("cat", OneHotEncoder(handle_unknown="ignore"), poc_cat_features)],
        remainder="passthrough",
    )
    poc_pipeline = Pipeline([
        ("prep", poc_preprocessor),
        ("clf", LogisticRegression(max_iter=1000)),
    ])
    print("Dang huan luyen Logistic Regression (POC)...")
    poc_pipeline.fit(train_df[poc_cat_features + poc_num_features], y_train)
    y_pred_lr_val = poc_pipeline.predict_proba(val_df[poc_cat_features + poc_num_features])[:, 1]
    y_pred_lr_test = poc_pipeline.predict_proba(test_df[poc_cat_features + poc_num_features])[:, 1]

    # Tuned LightGBM Classifier on original 9 features with categorical schedule splitting and strong regularization
    lgb_model = lgb.LGBMClassifier(
        metric="auc",
        n_estimators=4000,
        learning_rate=0.015,
        max_depth=6,
        num_leaves=31,
        min_child_samples=4000,
        reg_alpha=30.0,
        reg_lambda=300.0,
        path_smooth=100.0,
        cat_smooth=1000.0,
        cat_l2=200.0,
        min_data_per_group=1000,
        colsample_bytree=0.7,
        subsample=0.8,
        subsample_freq=1,
        max_bin=511,
        deterministic=True,
        random_state=42,
        n_jobs=-1,
        verbose=-1,
    )
    print("Dang huan luyen LightGBM (da tinh chỉnh tham so voi early stopping tren Validation 2017)...")
    lgb_model.fit(
        X_train,
        y_train,
        categorical_feature=CATEGORICAL_FEATURES,
        eval_X=X_val,
        eval_y=y_val,
        callbacks=[lgb.early_stopping(stopping_rounds=100, verbose=False)],
    )
    print(f"LightGBM dung tai iteration: {lgb_model.best_iteration_}")

    y_pred_lgb_val = lgb_model.predict_proba(X_val)[:, 1]
    y_pred_lgb_test = lgb_model.predict_proba(X_test)[:, 1]

    # Isotonic Regression probability calibration on Validation 2017
    print("Dang hieu chinh xac suat bang Isotonic Regression tren tap Validation 2017...")
    isotonic_calibrator = IsotonicRegression(out_of_bounds="clip")
    isotonic_calibrator.fit(y_pred_lgb_val, y_val)
    y_pred_cal_val = isotonic_calibrator.predict(y_pred_lgb_val)
    y_pred_cal_test = isotonic_calibrator.predict(y_pred_lgb_test)

    print(
        f"Validation 2017 -> POC LR AUC: {roc_auc_score(y_val, y_pred_lr_val):.4f} | "
        f"LGBM Raw AUC: {roc_auc_score(y_val, y_pred_lgb_val):.4f} | "
        f"LGBM Cal AUC: {roc_auc_score(y_val, y_pred_cal_val):.4f} (ECE={calculate_ece(y_val, y_pred_cal_val):.4f})"
    )

    models_dict = {
        "Baseline (Constant)": y_pred_base_test,
        "Logistic Regression (POC)": y_pred_lr_test,
        "LightGBM (Tho)": y_pred_lgb_test,
        "LightGBM Calibrated (Chinh thuc)": y_pred_cal_test,
    }

    results_list = []
    for name, y_prob in models_dict.items():
        auc = roc_auc_score(y_test, y_prob) if name != "Baseline (Constant)" else 0.5000
        pr_auc = average_precision_score(y_test, y_prob)
        brier = brier_score_loss(y_test, y_prob)
        ece = calculate_ece(y_test, y_prob, n_bins=10)

        order_idx = np.argsort(y_prob)
        prec_at_50 = float(y_test[order_idx[-50:]].mean())
        prec_at_100 = float(y_test[order_idx[-100:]].mean())
        prec_at_500 = float(y_test[order_idx[-500:]].mean())

        top_10pct_n = int(0.10 * len(y_prob))
        prec_top_10pct = float(y_test[order_idx[-top_10pct_n:]].mean())
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
            "Top-10% Lift": round(lift_10pct, 2),
        })

    results_df = pd.DataFrame(results_list)
    print("\n===== BANG KET QUA SO SANH CAC MO HINH TREN TAP TEST 2018 =====")
    print(results_df.to_string(index=False))
    results_df.to_csv(f"{OUTPUT_DIR}/model_comparison_results.csv", index=False)

    model_bundle = {
        "lgb_model": lgb_model,
        "calibrator": isotonic_calibrator,
        "features": FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "train_mean": baseline_train_rate,
        "best_iteration": int(lgb_model.best_iteration_),
    }
    if SAVE_WEIGHTS:
        joblib.dump(model_bundle, f"{MODELS_DIR}/full_lgbm_calibrated.joblib")
        print(f"\nDa luu model vao {MODELS_DIR}/full_lgbm_calibrated.joblib")
    else:
        print("\nBo qua luu file weight model (SAVE_WEIGHTS=False).")

    # Calibration curve comparison plot
    plt.figure(figsize=(7, 6))
    plt.plot([0, 1], [0, 1], linestyle="--", color="gray", label="Hieu chuan hoan hao (Perfect)")
    for name, y_prob in [
        ("Logistic Regression", y_pred_lr_test),
        ("LightGBM Tho", y_pred_lgb_test),
        ("LightGBM Calibrated", y_pred_cal_test),
    ]:
        prob_true, prob_pred = calibration_curve(y_test, y_prob, n_bins=10, strategy="quantile")
        plt.plot(prob_pred, prob_true, marker="o", label=name)
    plt.axhline(baseline_train_rate, linestyle=":", color="red", label=f"Baseline ({baseline_train_rate:.3f})")
    plt.xlabel("Xac suat du bao trung binh moi bin (Predicted Probability)")
    plt.ylabel("Ty le tre thuc te quan sat (Observed Delay Rate)")
    plt.title("So Sanh Hieu Chuan Xac Suat Tren Tap Test 2018")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/calibration_comparison.png", dpi=150)
    plt.close()

    # ROC and PR curve comparison plot
    plt.figure(figsize=(12, 5))
    plt.subplot(1, 2, 1)
    for name, y_prob in [("Logistic (POC)", y_pred_lr_test), ("LightGBM Calibrated", y_pred_cal_test)]:
        fpr, tpr, _ = roc_curve(y_test, y_prob)
        auc_val = roc_auc_score(y_test, y_prob)
        plt.plot(fpr, tpr, label=f"{name} (AUC = {auc_val:.4f})")
    plt.plot([0, 1], [0, 1], "k--", label="Ngau nhien (0.5000)")
    plt.xlabel("Ty le duong tinh gia (FPR)")
    plt.ylabel("Ty le duong tinh that (TPR)")
    plt.title("Duong Cong ROC (Test 2018)")
    plt.legend()

    plt.subplot(1, 2, 2)
    for name, y_prob in [("Logistic (POC)", y_pred_lr_test), ("LightGBM Calibrated", y_pred_cal_test)]:
        prec, rec, _ = precision_recall_curve(y_test, y_prob)
        pr_auc_val = average_precision_score(y_test, y_prob)
        plt.plot(rec, prec, label=f"{name} (PR-AUC = {pr_auc_val:.4f})")
    plt.axhline(y_test.mean(), color="red", linestyle=":", label=f"No-skill baseline ({y_test.mean():.4f})")
    plt.xlabel("Do phu (Recall)")
    plt.ylabel("Do chinh xac (Precision)")
    plt.title("Duong Cong Precision-Recall (Test 2018)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/roc_pr_curves.png", dpi=150)
    plt.close()

    # Stratified-by-time representative 5,000-flight sample across Test 2018 for TreeSHAP and FactPrediction
    sample_pos = np.sort(
        test_df.sample(n=min(5000, len(test_df)), random_state=42).index.to_numpy()
    )

    # TreeSHAP decomposition over the 5,000 test flights scored for FactPrediction
    print("Dang tinh toan TreeSHAP values...")
    explainer = shap.TreeExplainer(lgb_model)
    sample_test = X_test.iloc[sample_pos]
    shap_values = explainer.shap_values(sample_test)
    if isinstance(shap_values, list):
        shap_vals = shap_values[1]
    else:
        shap_vals = shap_values

    feat_idx = {f: i for i, f in enumerate(FEATURES)}
    sched_idx = [feat_idx["month"], feat_idx["day_of_week"], feat_idx["quarter"], feat_idx["time_block_code"]]
    route_idx = [feat_idx["route_hist_delay_rate"], feat_idx["distance"], feat_idx["route_hist_flight_count"]]
    cong_idx = [feat_idx["origin_hist_delay_rate"], feat_idx["dest_hist_delay_rate"]]

    contrib_schedule = np.sum(shap_vals[:, sched_idx], axis=1)
    contrib_route = np.sum(shap_vals[:, route_idx], axis=1)
    contrib_congestion = np.sum(shap_vals[:, cong_idx], axis=1)

    mean_abs_shap = np.abs(shap_vals).mean(axis=0)
    feat_series = pd.Series(mean_abs_shap, index=FEATURES).sort_values(ascending=True)

    plt.figure(figsize=(8, 5))
    feat_series.plot(kind="barh", color="#1f77b4")
    plt.xlabel("Gia tri SHAP tuyet doi trung binh (|SHAP value|)")
    plt.title("Do Quan Trong Dac Trung Giai Thich Bang TreeSHAP")
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/shap_tornado.png", dpi=150)
    plt.close()

    # Export FactPrediction sample compatible with the DSS serving contract
    scored_sample = test_df.iloc[sample_pos].copy()
    cal_probs_sample = y_pred_cal_test[sample_pos]

    scored_sample["PredictedDelayProbability"] = np.round(cal_probs_sample, 4)
    scored_sample["RiskBand"] = np.where(
        cal_probs_sample >= 0.40,
        "Cao",
        np.where(cal_probs_sample >= 0.20, "Trung bình", "Thấp"),
    )

    scored_sample["FeatureContributionSchedule"] = np.round(contrib_schedule, 4)
    scored_sample["FeatureContributionRouteHist"] = np.round(contrib_route, 4)
    scored_sample["FeatureContributionCongestion"] = np.round(contrib_congestion, 4)

    scored_sample["PriorityReviewStatus"] = np.where(
        scored_sample["route_hist_flight_count"] < 30,
        "Chưa đủ bằng chứng",
        np.where(
            (scored_sample["PredictedDelayProbability"] >= 0.40)
            & (scored_sample["route_hist_delay_rate"] >= baseline_train_rate),
            "Ưu tiên xem xét",
            "Tiếp tục theo dõi",
        ),
    )

    scored_sample["PredictionID"] = np.arange(1000001, 1000001 + len(scored_sample))
    scored_sample["DateKey"] = scored_sample["flight_date"].dt.strftime("%Y%m%d").astype(int)
    scored_sample["ModelVersion"] = "LGBM-CAL-v1.0"
    scored_sample["ScoringTimestamp"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

    out_cols = [
        "PredictionID",
        "flight_key",
        "DateKey",
        "route_key",
        "origin",
        "destination",
        "time_block",
        "distance",
        "PredictedDelayProbability",
        "RiskBand",
        "FeatureContributionSchedule",
        "FeatureContributionRouteHist",
        "FeatureContributionCongestion",
        "PriorityReviewStatus",
        "ModelVersion",
        "ScoringTimestamp",
    ]

    scored_sample[out_cols].to_csv(f"{OUTPUT_DIR}/fact_prediction_output.csv", index=False)
    print(f"Da xuat bang FactPrediction mau ({len(scored_sample):,} ban ghi) vao {OUTPUT_DIR}/fact_prediction_output.csv")

    plt.figure(figsize=(10, 4))
    plt.subplot(1, 2, 1)
    risk_order = ["Cao", "Trung bình", "Thấp"]
    risk_counts = scored_sample["RiskBand"].value_counts().reindex(risk_order, fill_value=0)
    risk_counts.plot(kind="bar", color=["#d62728", "#ff7f0e", "#2ca02c"])
    plt.ylabel("So luong chuyen bay")
    plt.title("Phan Bo Chuyen Bay Theo RiskBand")
    plt.xticks(rotation=0)

    plt.subplot(1, 2, 2)
    status_order = ["Ưu tiên xem xét", "Tiếp tục theo dõi", "Chưa đủ bằng chứng"]
    status_counts = scored_sample["PriorityReviewStatus"].value_counts().reindex(status_order, fill_value=0)
    status_counts.plot(kind="bar", color=["#1f77b4", "#aec7e8", "#c7c7c7"])
    plt.ylabel("So luong chuyen bay")
    plt.title("Phan Bo PriorityReviewStatus")
    plt.xticks(rotation=15)
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/risk_ranking_lift.png", dpi=150)
    plt.close()

    print("\nHoan tat toan bo qua trinh huan luyen, hieu chuan va xuat ket qua!")


if __name__ == "__main__":
    main()
