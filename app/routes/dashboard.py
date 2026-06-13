"""
Route dashboard utama: ringkasan statistik, grafik tren, run terbaru.
"""
from flask import Blueprint, render_template, redirect, url_for, flash
from app.utils.decorators import login_required
from app.models.data_lpg import count_rows, get_date_range, get_kontribusi_wilayah, fetch_aggregated_daily
from app.models.forecast_run import list_runs

dashboard_bp = Blueprint("dashboard", __name__, url_prefix="")


@dashboard_bp.route("/")
def root():
    return redirect(url_for("dashboard.index"))


@dashboard_bp.route("/dashboard")
@login_required
def index():
    try:
        jumlah_historis = count_rows("historis")
        jumlah_aktual = count_rows("aktual_2026")
        rentang_historis = get_date_range("historis")
        kontribusi = get_kontribusi_wilayah("historis")[:5]
        runs = list_runs(5)

        rows = fetch_aggregated_daily("historis")
        chart_labels, chart_values = [], []
        if rows:
            import pandas as pd
            df = pd.DataFrame(rows)
            df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)
            daily = df.groupby("tanggal")["total_berat"].sum().reset_index().sort_values("tanggal")
            chart_labels = daily["tanggal"].tolist()
            chart_values = daily["total_berat"].round(2).tolist()
    except Exception as e:
        flash(f"Gagal memuat data dashboard: {e}", "danger")
        jumlah_historis = jumlah_aktual = 0
        rentang_historis = (None, None)
        kontribusi, runs = [], []
        chart_labels, chart_values = [], []

    return render_template(
        "admin/dashboard.html",
        jumlah_historis=jumlah_historis,
        jumlah_aktual=jumlah_aktual,
        rentang_historis=rentang_historis,
        kontribusi=kontribusi,
        runs=runs,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )
