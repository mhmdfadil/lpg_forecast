"""
Operasi untuk tabel forecast_run dan tabel-tabel detailnya:
forecast_acf_pacf, forecast_dataset_point, forecast_prediction_test,
forecast_prediction_future.
"""
import math
from app.supabase_client import get_supabase


def _clean_num(v):
    """Konversi angka NaN/Inf ke None agar aman disimpan ke Postgres (JSON)."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def create_run(payload: dict) -> str:
    sb = get_supabase()
    res = sb.table("forecast_run").insert(payload).execute()
    return res.data[0]["id"]


def update_run(run_id: str, payload: dict):
    sb = get_supabase()
    sb.table("forecast_run").update(payload).eq("id", run_id).execute()


def get_run(run_id: str):
    sb = get_supabase()
    res = sb.table("forecast_run").select("*").eq("id", run_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


def list_runs(limit: int = 50):
    sb = get_supabase()
    res = (
        sb.table("forecast_run")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def delete_run(run_id: str):
    sb = get_supabase()
    sb.table("forecast_run").delete().eq("id", run_id).execute()


def save_acf_pacf(run_id: str, tahap: str, items: list):
    sb = get_supabase()
    rows = [
        {
            "run_id": run_id,
            "tahap": tahap,
            "lag": item["lag"],
            "acf_value": _clean_num(item["acf"]),
            "pacf_value": _clean_num(item["pacf"]),
        }
        for item in items
    ]
    if rows:
        sb.table("forecast_acf_pacf").insert(rows).execute()


def save_dataset_points(run_id: str, train_series, test_series):
    sb = get_supabase()
    rows = []
    for ts, val in train_series.items():
        rows.append({
            "run_id": run_id, "tanggal": ts.strftime("%Y-%m-%d"),
            "nilai_aktual": _clean_num(val), "kelompok": "train",
        })
    for ts, val in test_series.items():
        rows.append({
            "run_id": run_id, "tanggal": ts.strftime("%Y-%m-%d"),
            "nilai_aktual": _clean_num(val), "kelompok": "test",
        })
    for i in range(0, len(rows), 500):
        sb.table("forecast_dataset_point").insert(rows[i:i + 500]).execute()


def save_prediction_test(run_id: str, model: str, test_series, pred_mean, pred_ci):
    sb = get_supabase()
    rows = []
    for ts in test_series.index:
        rows.append({
            "run_id": run_id,
            "model": model,
            "tanggal": ts.strftime("%Y-%m-%d"),
            "nilai_aktual": _clean_num(test_series.get(ts)),
            "nilai_prediksi": _clean_num(pred_mean.get(ts)),
            "residual": _clean_num(
                (test_series.get(ts) - pred_mean.get(ts))
                if test_series.get(ts) is not None and pred_mean.get(ts) is not None
                else None
            ),
            "batas_bawah": _clean_num(pred_ci.iloc[:, 0].get(ts)) if pred_ci is not None else None,
            "batas_atas": _clean_num(pred_ci.iloc[:, 1].get(ts)) if pred_ci is not None else None,
        })
    for i in range(0, len(rows), 500):
        sb.table("forecast_prediction_test").insert(rows[i:i + 500]).execute()


def save_prediction_future(run_id: str, model: str, future_mean, future_ci, actual_2026_map: dict = None):
    sb = get_supabase()
    actual_2026_map = actual_2026_map or {}
    rows = []
    for ts in future_mean.index:
        tanggal_str = ts.strftime("%Y-%m-%d")
        rows.append({
            "run_id": run_id,
            "model": model,
            "tanggal": tanggal_str,
            "nilai_prediksi": _clean_num(future_mean.get(ts)),
            "batas_bawah": _clean_num(future_ci.iloc[:, 0].get(ts)) if future_ci is not None else None,
            "batas_atas": _clean_num(future_ci.iloc[:, 1].get(ts)) if future_ci is not None else None,
            "nilai_aktual_2026": _clean_num(actual_2026_map.get(tanggal_str)),
        })
    for i in range(0, len(rows), 500):
        sb.table("forecast_prediction_future").insert(rows[i:i + 500]).execute()


def get_acf_pacf(run_id: str, tahap: str = None):
    sb = get_supabase()
    q = sb.table("forecast_acf_pacf").select("*").eq("run_id", run_id)
    if tahap:
        q = q.eq("tahap", tahap)
    res = q.order("lag", desc=False).execute()
    return res.data or []


def get_dataset_points(run_id: str):
    sb = get_supabase()
    res = (
        sb.table("forecast_dataset_point")
        .select("*")
        .eq("run_id", run_id)
        .order("tanggal", desc=False)
        .execute()
    )
    return res.data or []


def get_prediction_test(run_id: str, model: str = None):
    sb = get_supabase()
    q = sb.table("forecast_prediction_test").select("*").eq("run_id", run_id)
    if model:
        q = q.eq("model", model)
    res = q.order("tanggal", desc=False).execute()
    return res.data or []


def get_prediction_future(run_id: str, model: str = None):
    sb = get_supabase()
    q = sb.table("forecast_prediction_future").select("*").eq("run_id", run_id)
    if model:
        q = q.eq("model", model)
    res = q.order("tanggal", desc=False).execute()
    return res.data or []
