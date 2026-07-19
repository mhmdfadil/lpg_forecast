"""
Route untuk proses forecasting: form input parameter, jalankan pipeline
ARIMA/SARIMA, tampilkan hasil detail, riwayat run, download Excel.
"""
import traceback
from datetime import datetime, timedelta
import pandas as pd
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, send_file
)

from app.utils.decorators import login_required
from app.models.data_lpg import (
    fetch_aggregated_daily, get_distinct_wilayah, get_date_range,
)
from app.services.forecast_engine import (
    run_full_pipeline, determine_best_model, SEASONAL_PERIOD, TRAIN_RATIO,
)
from app.models.forecast_run import (
    create_run, update_run, get_run, list_runs, delete_run,
    save_acf_pacf, save_dataset_points, save_prediction_test,
    save_prediction_future, get_acf_pacf, get_dataset_points,
    get_prediction_test, get_prediction_future,
)
from app.services.excel_export import build_forecast_excel

forecast_bp = Blueprint("forecast", __name__, url_prefix="/forecast")


@forecast_bp.route("/")
@login_required
def index():
    try:
        runs = list_runs(50)
    except Exception as e:
        flash(f"Gagal memuat riwayat forecasting: {e}", "danger")
        runs = []
    return render_template("admin/forecast_index.html", runs=runs)


@forecast_bp.route("/baru", methods=["GET", "POST"])
@login_required
def new_run():
    try:
        wilayah_list = get_distinct_wilayah("historis")
        rentang_historis = get_date_range("historis")
    except Exception as e:
        flash(f"Gagal memuat data wilayah: {e}", "danger")
        wilayah_list, rentang_historis = [], (None, None)

    if request.method == "GET":
        return render_template(
            "admin/forecast_new.html",
            wilayah_list=wilayah_list,
            rentang_historis=rentang_historis,
            today=datetime.now().strftime("%Y-%m-%d"),
        )

    # ---- POST: jalankan pipeline ----
    nama_run = request.form.get("nama_run", "").strip() or f"Forecast {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    wilayah_scope = request.form.get("wilayah_scope", "TOTAL")
    # Proporsi train/test bersifat MUTLAK 80% : 20% (TRAIN_RATIO), tidak
    # menerima input dari form agar tidak bisa diubah pengguna.
    train_ratio = TRAIN_RATIO
    tanggal_mulai_prediksi = request.form.get("tanggal_mulai_prediksi")
    tanggal_akhir_prediksi = request.form.get("tanggal_akhir_prediksi")
    bandingkan_aktual = request.form.get("bandingkan_aktual") == "on"

    if not tanggal_mulai_prediksi or not tanggal_akhir_prediksi:
        flash("Rentang tanggal prediksi wajib diisi.", "danger")
        return redirect(url_for("forecast.new_run"))

    start_pred = pd.to_datetime(tanggal_mulai_prediksi)
    end_pred = pd.to_datetime(tanggal_akhir_prediksi)
    if end_pred < start_pred:
        flash("Tanggal akhir prediksi tidak boleh sebelum tanggal mulai.", "danger")
        return redirect(url_for("forecast.new_run"))

    horizon_dates = pd.date_range(start_pred, end_pred, freq="D")
    if len(horizon_dates) > 366:
        flash("Rentang prediksi terlalu panjang (maksimal 366 hari).", "danger")
        return redirect(url_for("forecast.new_run"))

    try:
        rows = fetch_aggregated_daily("historis", wilayah_scope)
        if not rows:
            flash("Tidak ada data historis untuk scope yang dipilih. Silakan upload data terlebih dahulu.", "danger")
            return redirect(url_for("forecast.new_run"))

        results = run_full_pipeline(rows, horizon_dates)
    except Exception as e:
        flash(f"Gagal menjalankan proses forecasting: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for("forecast.new_run"))

    series = results["series"]
    train, test = results["train"], results["test"]
    arima, sarima = results["arima"], results["sarima"]

    best_model, skor_arima, skor_sarima = determine_best_model(
        arima["eval_test"], sarima["eval_test"]
    )

    # ---- Pembanding data aktual 2026 (opsional & fleksibel) ----
    actual_2026_map = {}
    arima_eval_aktual = {"mae": None, "rmse": None, "mape": None}
    sarima_eval_aktual = {"mae": None, "rmse": None, "mape": None}

    if bandingkan_aktual:
        try:
            aktual_rows = fetch_aggregated_daily(
                "aktual_2026", wilayah_scope,
                tanggal_mulai_prediksi, tanggal_akhir_prediksi,
            )
            if aktual_rows:
                df_akt = pd.DataFrame(aktual_rows)
                df_akt["tanggal"] = pd.to_datetime(df_akt["tanggal"])
                df_akt["total_berat"] = pd.to_numeric(df_akt["total_berat"], errors="coerce").fillna(0)
                daily_akt = df_akt.groupby("tanggal")["total_berat"].sum()
                actual_2026_map = {ts.strftime("%Y-%m-%d"): float(v) for ts, v in daily_akt.items()}

                from app.services.forecast_engine import evaluate_predictions

                common_dates = [d for d in horizon_dates if d in daily_akt.index]
                if common_dates:
                    actual_vals = daily_akt.loc[common_dates].values
                    arima_pred_vals = arima["future_prediction"].loc[common_dates].values
                    sarima_pred_vals = sarima["future_prediction"].loc[common_dates].values
                    arima_eval_aktual = evaluate_predictions(actual_vals, arima_pred_vals)
                    sarima_eval_aktual = evaluate_predictions(actual_vals, sarima_pred_vals)
            else:
                flash("Tidak ditemukan data aktual 2026 pada rentang tanggal prediksi yang dipilih.", "warning")
        except Exception as e:
            flash(f"Gagal membandingkan dengan data aktual: {e}", "warning")

    # ---- Simpan ke Supabase ----
    try:
        run_payload = {
            "nama_run": nama_run,
            "wilayah_scope": wilayah_scope,
            "tanggal_mulai_data": series.index.min().strftime("%Y-%m-%d"),
            "tanggal_akhir_data": series.index.max().strftime("%Y-%m-%d"),
            "horizon_hari": len(horizon_dates),
            "tanggal_mulai_prediksi": tanggal_mulai_prediksi,
            "tanggal_akhir_prediksi": tanggal_akhir_prediksi,
            "train_test_split": train_ratio,
            "bandingkan_aktual": bool(actual_2026_map),

            "adf_statistic_awal": results["adf_before"]["adf_statistic"],
            "adf_pvalue_awal": results["adf_before"]["p_value"],
            "adf_stasioner_awal": results["adf_before"]["is_stationary"],
            "differencing_order": results["differencing_order"],
            "adf_statistic_diff": results["adf_after"]["adf_statistic"],
            "adf_pvalue_diff": results["adf_after"]["p_value"],
            "adf_stasioner_diff": results["adf_after"]["is_stationary"],
            "acf_ci95_sebelum": results["acf_ci95_before"],
            "acf_ci95_sesudah": results["acf_ci95_after"] if results["differencing_order"] > 0 else None,

            "arima_p": arima["order"][0], "arima_d": arima["order"][1], "arima_q": arima["order"][2],
            "arima_aic": arima["aic"], "arima_bic": arima["bic"],
            "arima_mae_test": arima["eval_test"]["mae"],
            "arima_rmse_test": arima["eval_test"]["rmse"],
            "arima_mape_test": arima["eval_test"]["mape"],
            "arima_mae_aktual": arima_eval_aktual["mae"],
            "arima_rmse_aktual": arima_eval_aktual["rmse"],
            "arima_mape_aktual": arima_eval_aktual["mape"],

            "sarima_p": sarima["order"][0], "sarima_d": sarima["order"][1], "sarima_q": sarima["order"][2],
            "sarima_pp": sarima["seasonal_order"][0], "sarima_dd": sarima["seasonal_order"][1],
            "sarima_qq": sarima["seasonal_order"][2], "sarima_s": sarima["seasonal_order"][3],
            "sarima_aic": sarima["aic"], "sarima_bic": sarima["bic"],
            "sarima_mae_test": sarima["eval_test"]["mae"],
            "sarima_rmse_test": sarima["eval_test"]["rmse"],
            "sarima_mape_test": sarima["eval_test"]["mape"],
            "sarima_mae_aktual": sarima_eval_aktual["mae"],
            "sarima_rmse_aktual": sarima_eval_aktual["rmse"],
            "sarima_mape_aktual": sarima_eval_aktual["mape"],

            "model_terbaik": best_model,
            "skor_arima": skor_arima,
            "skor_sarima": skor_sarima,
            "status": "selesai",
            "dijalankan_oleh": session.get("admin_id"),
        }
        run_id = create_run(run_payload)

        save_acf_pacf(run_id, "sebelum_diff", results["acf_pacf_before"])
        if results["differencing_order"] > 0:
            save_acf_pacf(run_id, "sesudah_diff", results["acf_pacf_after"])

        save_dataset_points(run_id, train, test)
        save_prediction_test(run_id, "ARIMA", test, arima["test_prediction"], arima["test_ci"])
        save_prediction_test(run_id, "SARIMA", test, sarima["test_prediction"], sarima["test_ci"])
        save_prediction_future(run_id, "ARIMA", arima["future_prediction"], arima["future_ci"], actual_2026_map)
        save_prediction_future(run_id, "SARIMA", sarima["future_prediction"], sarima["future_ci"], actual_2026_map)

        flash("Proses forecasting ARIMA & SARIMA berhasil diselesaikan!", "success")
        return redirect(url_for("forecast.detail", run_id=run_id))

    except Exception as e:
        flash(f"Forecasting selesai dihitung namun gagal disimpan ke database: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for("forecast.new_run"))


@forecast_bp.route("/<run_id>")
@login_required
def detail(run_id):
    run = get_run(run_id)
    if not run:
        flash("Data forecasting tidak ditemukan.", "danger")
        return redirect(url_for("forecast.index"))

    dataset_points = get_dataset_points(run_id)
    acf_before = get_acf_pacf(run_id, "sebelum_diff")
    acf_after = get_acf_pacf(run_id, "sesudah_diff") if run.get("differencing_order", 0) > 0 else []

    pred_test_arima = get_prediction_test(run_id, "ARIMA")
    pred_test_sarima = get_prediction_test(run_id, "SARIMA")
    pred_future_arima = get_prediction_future(run_id, "ARIMA")
    pred_future_sarima = get_prediction_future(run_id, "SARIMA")

    return render_template(
        "admin/forecast_detail.html",
        run=run,
        dataset_points=dataset_points,
        acf_before=acf_before,
        acf_after=acf_after,
        pred_test_arima=pred_test_arima,
        pred_test_sarima=pred_test_sarima,
        pred_future_arima=pred_future_arima,
        pred_future_sarima=pred_future_sarima,
        seasonal_period=SEASONAL_PERIOD,
    )


@forecast_bp.route("/<run_id>/hapus", methods=["POST"])
@login_required
def hapus_run(run_id):
    try:
        delete_run(run_id)
        flash("Riwayat forecasting berhasil dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus riwayat: {e}", "danger")
    return redirect(url_for("forecast.index"))


@forecast_bp.route("/<run_id>/export")
@login_required
def export_excel(run_id):
    run = get_run(run_id)
    if not run:
        flash("Data forecasting tidak ditemukan.", "danger")
        return redirect(url_for("forecast.index"))

    try:
        dataset_points = get_dataset_points(run_id)
        acf_before = get_acf_pacf(run_id, "sebelum_diff")
        acf_after = get_acf_pacf(run_id, "sesudah_diff")
        pred_test_arima = get_prediction_test(run_id, "ARIMA")
        pred_test_sarima = get_prediction_test(run_id, "SARIMA")
        pred_future_arima = get_prediction_future(run_id, "ARIMA")
        pred_future_sarima = get_prediction_future(run_id, "SARIMA")

        excel_bytes = build_forecast_excel(
            run=run,
            dataset_points=dataset_points,
            acf_before=acf_before,
            acf_after=acf_after,
            pred_test_arima=pred_test_arima,
            pred_test_sarima=pred_test_sarima,
            pred_future_arima=pred_future_arima,
            pred_future_sarima=pred_future_sarima,
        )

        filename = f"Forecast_LPG_{run.get('wilayah_scope','TOTAL')}_{run['id'][:8]}.xlsx".replace(" ", "_")

        from app.models.export_log import create_export_log
        try:
            create_export_log(run_id, filename, session.get("admin_id"))
        except Exception:
            pass

        return send_file(
            excel_bytes,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        flash(f"Gagal membuat file Excel: {e}", "danger")
        traceback.print_exc()
        return redirect(url_for("forecast.detail", run_id=run_id))