"""
Route untuk kelola data: upload dataset Excel, lihat data historis & aktual,
hapus data, lihat log import, kontribusi wilayah.
"""
import os
import uuid
from datetime import datetime
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash,
    session, jsonify, current_app
)
from werkzeug.utils import secure_filename

from app.utils.decorators import login_required
from app.services.excel_import import (
    list_sheets, process_upload, ImportValidationError,
)
from app.models.data_lpg import (
    insert_batch, count_rows, get_date_range, get_distinct_wilayah,
    fetch_aggregated_daily, delete_all, get_kontribusi_wilayah,
)
from app.models.import_log import create_log, list_logs

data_bp = Blueprint("data", __name__, url_prefix="/data")


def _allowed_file(filename):
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_EXTENSIONS"]


@data_bp.route("/")
@login_required
def index():
    try:
        jumlah_historis = count_rows("historis")
        jumlah_aktual = count_rows("aktual_2026")
        rentang_historis = get_date_range("historis")
        rentang_aktual = get_date_range("aktual_2026")
        logs = list_logs(10)
    except Exception as e:
        flash(f"Gagal memuat ringkasan data: {e}", "danger")
        jumlah_historis = jumlah_aktual = 0
        rentang_historis = rentang_aktual = (None, None)
        logs = []

    return render_template(
        "admin/data_index.html",
        jumlah_historis=jumlah_historis,
        jumlah_aktual=jumlah_aktual,
        rentang_historis=rentang_historis,
        rentang_aktual=rentang_aktual,
        logs=logs,
    )


@data_bp.route("/upload", methods=["GET", "POST"])
@login_required
def upload():
    if request.method == "GET":
        return render_template("admin/data_upload.html")

    file = request.files.get("dataset_file")
    tipe_dataset = request.form.get("tipe_dataset")  # 'historis' atau 'aktual_2026'
    sheet_name = request.form.get("sheet_name")

    if not file or file.filename == "":
        flash("Silakan pilih file Excel terlebih dahulu.", "danger")
        return redirect(url_for("data.upload"))

    if not _allowed_file(file.filename):
        flash("Format file tidak didukung. Gunakan .xlsx atau .xls.", "danger")
        return redirect(url_for("data.upload"))

    if tipe_dataset not in ("historis", "aktual_2026"):
        flash("Tipe dataset tidak valid.", "danger")
        return redirect(url_for("data.upload"))

    filename = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex[:8]}_{filename}"
    save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
    file.save(save_path)

    try:
        if not sheet_name:
            sheets = list_sheets(save_path)
            sheet_name = sheets[0] if sheets else None
            if not sheet_name:
                raise ImportValidationError("File Excel tidak memiliki sheet apa pun.")

        sumber_import = f"{filename} | {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        records, ringkasan = process_upload(save_path, sheet_name, sumber_import)

        if not records:
            raise ImportValidationError(
                "Tidak ada baris valid yang dapat diimpor. Periksa format kolom & isi file."
            )

        insert_batch(tipe_dataset, records)

        create_log(
            nama_file=filename,
            tipe_dataset=tipe_dataset,
            jumlah_baris=ringkasan["baris_setelah_agregasi"],
            tanggal_mulai=ringkasan["tanggal_mulai"],
            tanggal_akhir=ringkasan["tanggal_akhir"],
            status="sukses",
            pesan=(
                f"Sheet: {sheet_name}. Baris mentah: {ringkasan['baris_mentah']}, "
                f"valid: {ringkasan['baris_valid']}, dibuang: {ringkasan['baris_dibuang']}, "
                f"setelah agregasi: {ringkasan['baris_setelah_agregasi']}, "
                f"wilayah: {ringkasan['jumlah_wilayah']}."
            ),
            diupload_oleh=session.get("admin_id"),
        )

        flash(
            f"Import berhasil! {ringkasan['baris_setelah_agregasi']} baris data "
            f"({ringkasan['tanggal_mulai']} s.d. {ringkasan['tanggal_akhir']}) "
            f"untuk {ringkasan['jumlah_wilayah']} wilayah berhasil disimpan.",
            "success",
        )

    except ImportValidationError as e:
        create_log(
            nama_file=filename, tipe_dataset=tipe_dataset, jumlah_baris=0,
            tanggal_mulai=None, tanggal_akhir=None, status="gagal",
            pesan=str(e), diupload_oleh=session.get("admin_id"),
        )
        flash(f"Validasi gagal: {e}", "danger")
    except Exception as e:
        create_log(
            nama_file=filename, tipe_dataset=tipe_dataset, jumlah_baris=0,
            tanggal_mulai=None, tanggal_akhir=None, status="gagal",
            pesan=str(e), diupload_oleh=session.get("admin_id"),
        )
        flash(f"Terjadi kesalahan saat memproses file: {e}", "danger")
    finally:
        try:
            os.remove(save_path)
        except OSError:
            pass

    return redirect(url_for("data.index"))


@data_bp.route("/sheets", methods=["POST"])
@login_required
def preview_sheets():
    """AJAX endpoint: upload sementara file, kembalikan daftar nama sheet."""
    file = request.files.get("dataset_file")
    if not file or file.filename == "":
        return jsonify({"error": "File tidak ditemukan"}), 400
    if not _allowed_file(file.filename):
        return jsonify({"error": "Format file tidak didukung"}), 400

    filename = secure_filename(file.filename)
    tmp_name = f"preview_{uuid.uuid4().hex[:8]}_{filename}"
    tmp_path = os.path.join(current_app.config["UPLOAD_FOLDER"], tmp_name)
    file.save(tmp_path)
    try:
        sheets = list_sheets(tmp_path)
        return jsonify({"sheets": sheets})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


@data_bp.route("/historis")
@login_required
def view_historis():
    return _view_dataset("historis")


@data_bp.route("/aktual-2026")
@login_required
def view_aktual():
    return _view_dataset("aktual_2026")


def _view_dataset(tipe):
    wilayah_filter = request.args.get("wilayah", "TOTAL")
    tanggal_mulai = request.args.get("mulai") or None
    tanggal_akhir = request.args.get("akhir") or None

    try:
        wilayah_list = get_distinct_wilayah(tipe)
        rows = fetch_aggregated_daily(tipe, wilayah_filter, tanggal_mulai, tanggal_akhir)
    except Exception as e:
        flash(f"Gagal memuat data: {e}", "danger")
        wilayah_list, rows = [], []

    import pandas as pd
    if rows:
        df = pd.DataFrame(rows)
        df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)
        daily = df.groupby("tanggal")["total_berat"].sum().reset_index().sort_values("tanggal")
        chart_labels = daily["tanggal"].tolist()
        chart_values = daily["total_berat"].round(2).tolist()
        table_rows = sorted(rows, key=lambda r: (r["tanggal"], r["nama_wilayah"]))[:500]
    else:
        chart_labels, chart_values, table_rows = [], [], []

    return render_template(
        "admin/data_view.html",
        tipe=tipe,
        wilayah_list=wilayah_list,
        wilayah_filter=wilayah_filter,
        tanggal_mulai=tanggal_mulai,
        tanggal_akhir=tanggal_akhir,
        chart_labels=chart_labels,
        chart_values=chart_values,
        table_rows=table_rows,
        total_rows=len(rows),
    )


@data_bp.route("/kontribusi")
@login_required
def kontribusi():
    tipe = request.args.get("tipe", "historis")
    try:
        data = get_kontribusi_wilayah(tipe)
    except Exception as e:
        flash(f"Gagal menghitung kontribusi wilayah: {e}", "danger")
        data = []
    return render_template("admin/data_kontribusi.html", tipe=tipe, data=data)


@data_bp.route("/hapus/<tipe>", methods=["POST"])
@login_required
def hapus(tipe):
    if tipe not in ("historis", "aktual_2026"):
        flash("Tipe dataset tidak valid.", "danger")
        return redirect(url_for("data.index"))
    try:
        delete_all(tipe)
        flash("Seluruh data pada dataset ini berhasil dihapus.", "success")
    except Exception as e:
        flash(f"Gagal menghapus data: {e}", "danger")
    return redirect(url_for("data.index"))
