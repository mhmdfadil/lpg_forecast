"""
API ringan untuk kebutuhan AJAX dari sisi klien (mis. grafik dinamis).
"""
from flask import Blueprint, jsonify, request
from app.utils.decorators import login_required
from app.models.data_lpg import fetch_aggregated_daily, get_distinct_wilayah

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/wilayah/<tipe>")
@login_required
def wilayah(tipe):
    if tipe not in ("historis", "aktual_2026"):
        return jsonify({"error": "tipe tidak valid"}), 400
    try:
        data = get_distinct_wilayah(tipe)
        return jsonify({"wilayah": data})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/series/<tipe>")
@login_required
def series(tipe):
    if tipe not in ("historis", "aktual_2026"):
        return jsonify({"error": "tipe tidak valid"}), 400
    wilayah_filter = request.args.get("wilayah", "TOTAL")
    mulai = request.args.get("mulai") or None
    akhir = request.args.get("akhir") or None
    try:
        rows = fetch_aggregated_daily(tipe, wilayah_filter, mulai, akhir)
        import pandas as pd
        if not rows:
            return jsonify({"labels": [], "values": []})
        df = pd.DataFrame(rows)
        df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)
        daily = df.groupby("tanggal")["total_berat"].sum().reset_index().sort_values("tanggal")
        return jsonify({
            "labels": daily["tanggal"].tolist(),
            "values": daily["total_berat"].round(2).tolist(),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
