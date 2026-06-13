"""
Engine inti forecasting: ARIMA & SARIMA.

Mengikuti alur penelitian pada proposal skripsi (Bab III):
    1. Agregasi data harian (sesuai scope wilayah)
    2. Split train/test
    3. Uji stasioneritas (ADF Test)
    4. Differencing jika diperlukan
    5. Analisis ACF & PACF
    6. Pemodelan ARIMA (auto_arima utk pencarian order terbaik, non-seasonal)
    7. Pemodelan SARIMA (auto_arima dengan seasonal=True)
    8. Evaluasi & perbandingan (MAE, RMSE, MAPE) pada data test
    9. Peramalan ke depan (future) sesuai rentang tanggal pilihan admin
    10. Jika ada data aktual 2026 yang overlap dengan tanggal future -> dihitung juga
        MAE/RMSE pembanding aktual & evaluasi tambahan
"""
import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import adfuller, acf, pacf
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.statespace.sarimax import SARIMAX
import pmdarima as pm
from sklearn.metrics import mean_absolute_error, mean_squared_error


SEASONAL_PERIOD = 7  # pola musiman mingguan untuk data harian penyaluran LPG


def build_daily_series(rows: list) -> pd.Series:
    """
    rows: list of dict {tanggal, nama_wilayah, total_berat}
    Mengagregasi total_berat per tanggal (sum seluruh wilayah pada scope yg
    sudah difilter sebelumnya), lalu mengisi tanggal yang hilang (jika ada)
    dengan reindex harian agar deret waktu kontinu.
    """
    if not rows:
        raise ValueError("Tidak ada data untuk diproses.")

    df = pd.DataFrame(rows)
    df["tanggal"] = pd.to_datetime(df["tanggal"])
    df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)

    daily = df.groupby("tanggal")["total_berat"].sum().sort_index()

    full_idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_idx)
    daily = daily.interpolate(method="linear").bfill().ffill()
    daily.index.name = "tanggal"
    return daily


def train_test_split_series(series: pd.Series, train_ratio: float = 0.8):
    n = len(series)
    split_idx = max(1, int(n * train_ratio))
    train = series.iloc[:split_idx]
    test = series.iloc[split_idx:]
    return train, test


def adf_test(series: pd.Series) -> dict:
    result = adfuller(series.dropna(), autolag="AIC")
    return {
        "adf_statistic": float(result[0]),
        "p_value": float(result[1]),
        "n_lags": int(result[2]),
        "n_obs": int(result[3]),
        "critical_values": {k: float(v) for k, v in result[4].items()},
        "is_stationary": bool(result[1] < 0.05),
    }


def determine_differencing(series: pd.Series, max_d: int = 2):
    """
    Menentukan order differencing (d) berdasarkan ADF test berulang.
    Mengembalikan (d, series_differenced, adf_before, adf_after)
    """
    adf_before = adf_test(series)
    if adf_before["is_stationary"]:
        return 0, series, adf_before, adf_before

    current = series.copy()
    d = 0
    adf_after = adf_before
    while d < max_d:
        current = current.diff().dropna()
        d += 1
        adf_after = adf_test(current)
        if adf_after["is_stationary"]:
            break
    return d, current, adf_before, adf_after


def compute_acf_pacf(series: pd.Series, nlags: int = 30):
    series_clean = series.dropna()
    nlags = min(nlags, max(1, len(series_clean) // 2 - 1))
    acf_vals = acf(series_clean, nlags=nlags, fft=True)
    pacf_vals = pacf(series_clean, nlags=nlags, method="ywm")
    return [
        {"lag": i, "acf": float(acf_vals[i]), "pacf": float(pacf_vals[i])}
        for i in range(len(acf_vals))
    ]


def evaluate_predictions(actual: np.ndarray, predicted: np.ndarray) -> dict:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mae = mean_absolute_error(actual, predicted)
    rmse = np.sqrt(mean_squared_error(actual, predicted))
    # MAPE - hindari pembagian oleh nol
    nonzero_mask = actual != 0
    if nonzero_mask.sum() > 0:
        mape = float(
            np.mean(np.abs((actual[nonzero_mask] - predicted[nonzero_mask]) / actual[nonzero_mask])) * 100
        )
    else:
        mape = None
    return {"mae": float(mae), "rmse": float(rmse), "mape": mape}


def fit_arima_auto(train: pd.Series):
    """Mencari order ARIMA (p,d,q) terbaik (non-seasonal) memakai auto_arima."""
    model = pm.auto_arima(
        train,
        start_p=0, start_q=0, max_p=5, max_q=5, max_d=2,
        seasonal=False,
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore",
        trace=False,
    )
    order = model.order  # (p, d, q)
    fitted = ARIMA(train, order=order).fit()
    return order, fitted


def fit_sarima_auto(train: pd.Series, m: int = SEASONAL_PERIOD):
    """Mencari order SARIMA (p,d,q)(P,D,Q)s terbaik memakai auto_arima seasonal."""
    model = pm.auto_arima(
        train,
        start_p=0, start_q=0, max_p=3, max_q=3, max_d=2,
        start_P=0, start_Q=0, max_P=2, max_Q=2, max_D=1,
        seasonal=True, m=m,
        stepwise=True,
        suppress_warnings=True,
        error_action="ignore",
        trace=False,
    )
    order = model.order
    seasonal_order = model.seasonal_order
    fitted = SARIMAX(
        train, order=order, seasonal_order=seasonal_order,
        enforce_stationarity=False, enforce_invertibility=False,
    ).fit(disp=False)
    return order, seasonal_order, fitted


def predict_test_arima(fitted, train: pd.Series, test: pd.Series):
    forecast_res = fitted.get_forecast(steps=len(test))
    mean = forecast_res.predicted_mean
    ci = forecast_res.conf_int(alpha=0.05)
    mean.index = test.index
    ci.index = test.index
    return mean, ci


def predict_test_sarima(fitted, train: pd.Series, test: pd.Series):
    forecast_res = fitted.get_forecast(steps=len(test))
    mean = forecast_res.predicted_mean
    ci = forecast_res.conf_int(alpha=0.05)
    mean.index = test.index
    ci.index = test.index
    return mean, ci


def refit_full_and_forecast_future(series: pd.Series, order, seasonal_order, horizon: int, future_index, model_kind: str):
    """
    Melatih ulang model dengan SELURUH data (train+test) menggunakan order
    terbaik yang sudah ditemukan, lalu meramalkan 'horizon' langkah ke depan
    pada tanggal-tanggal future_index yang dipilih admin.
    """
    if model_kind == "ARIMA":
        fitted_full = ARIMA(series, order=order).fit()
    else:
        fitted_full = SARIMAX(
            series, order=order, seasonal_order=seasonal_order,
            enforce_stationarity=False, enforce_invertibility=False,
        ).fit(disp=False)

    forecast_res = fitted_full.get_forecast(steps=horizon)
    mean = forecast_res.predicted_mean
    ci = forecast_res.conf_int(alpha=0.05)
    mean.index = future_index
    ci.index = future_index
    return mean, ci, fitted_full


def run_full_pipeline(rows: list, train_ratio: float, horizon_dates: pd.DatetimeIndex):
    """
    Menjalankan seluruh pipeline forecasting dan mengembalikan dict besar
    berisi semua hasil intermediate (untuk ditampilkan detail di UI & disimpan
    ke Supabase).
    """
    series = build_daily_series(rows)
    train, test = train_test_split_series(series, train_ratio)

    # --- Stasioneritas & differencing (berdasarkan train set) ---
    d_order, series_diff, adf_before, adf_after = determine_differencing(train)

    # --- ACF / PACF sebelum & sesudah differencing ---
    acf_pacf_before = compute_acf_pacf(train)
    acf_pacf_after = compute_acf_pacf(series_diff) if d_order > 0 else acf_pacf_before

    results = {
        "series": series,
        "train": train,
        "test": test,
        "differencing_order": d_order,
        "adf_before": adf_before,
        "adf_after": adf_after,
        "acf_pacf_before": acf_pacf_before,
        "acf_pacf_after": acf_pacf_after,
    }

    # ============== ARIMA ==============
    arima_order, arima_fitted = fit_arima_auto(train)
    arima_test_mean, arima_test_ci = predict_test_arima(arima_fitted, train, test)
    arima_eval_test = evaluate_predictions(test.values, arima_test_mean.values)

    results["arima"] = {
        "order": arima_order,
        "aic": float(arima_fitted.aic),
        "bic": float(arima_fitted.bic),
        "test_prediction": arima_test_mean,
        "test_ci": arima_test_ci,
        "eval_test": arima_eval_test,
    }

    # ============== SARIMA ==============
    sarima_order, sarima_seasonal_order, sarima_fitted = fit_sarima_auto(train, m=SEASONAL_PERIOD)
    sarima_test_mean, sarima_test_ci = predict_test_sarima(sarima_fitted, train, test)
    sarima_eval_test = evaluate_predictions(test.values, sarima_test_mean.values)

    results["sarima"] = {
        "order": sarima_order,
        "seasonal_order": sarima_seasonal_order,
        "aic": float(sarima_fitted.aic),
        "bic": float(sarima_fitted.bic),
        "test_prediction": sarima_test_mean,
        "test_ci": sarima_test_ci,
        "eval_test": sarima_eval_test,
    }

    # ============== Future forecasting (refit dgn seluruh data) ==============
    horizon = len(horizon_dates)

    arima_future_mean, arima_future_ci, _ = refit_full_and_forecast_future(
        series, arima_order, None, horizon, horizon_dates, "ARIMA"
    )
    sarima_future_mean, sarima_future_ci, _ = refit_full_and_forecast_future(
        series, sarima_order, sarima_seasonal_order, horizon, horizon_dates, "SARIMA"
    )

    results["arima"]["future_prediction"] = arima_future_mean
    results["arima"]["future_ci"] = arima_future_ci
    results["sarima"]["future_prediction"] = sarima_future_mean
    results["sarima"]["future_ci"] = sarima_future_ci

    return results


def determine_best_model(arima_eval: dict, sarima_eval: dict):
    """
    Skor sederhana: bandingkan MAE & RMSE (dan MAPE bila tersedia) pada
    test-set; model dengan nilai lebih kecil pada masing-masing metrik
    mendapat 1 poin. Model dengan skor tertinggi -> 'model terbaik'.
    """
    skor_arima = 0
    skor_sarima = 0
    metrics = ["mae", "rmse", "mape"]
    for m in metrics:
        a = arima_eval.get(m)
        s = sarima_eval.get(m)
        if a is None or s is None:
            continue
        if a < s:
            skor_arima += 1
        elif s < a:
            skor_sarima += 1

    if skor_arima > skor_sarima:
        best = "ARIMA"
    elif skor_sarima > skor_arima:
        best = "SARIMA"
    else:
        best = "ARIMA" if arima_eval.get("rmse", float("inf")) <= sarima_eval.get("rmse", float("inf")) else "SARIMA"

    return best, skor_arima, skor_sarima
