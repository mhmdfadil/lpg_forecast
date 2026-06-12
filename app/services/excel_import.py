"""
Service untuk membaca & memvalidasi file Excel dataset penyaluran LPG,
lalu menyiapkannya untuk disimpan ke Supabase (data_historis / data_aktual_2026).

Format yang didukung mengikuti struktur datapenelitian1.xlsx:
    Sheet "data_2023-2025_faktualhistoris" -> tabel data_historis
    Sheet "data_uji_2026_faktual"          -> tabel data_aktual_2026

Kolom wajib: 'Act. Gds Mvmnt Date', 'Kabupaten/Kota', 'Total Berat'
Tanggal dapat berupa serial Excel (angka) ataupun format tanggal biasa.
"""
import pandas as pd
import numpy as np

REQUIRED_COLUMNS = ["Act. Gds Mvmnt Date", "Kabupaten/Kota", "Total Berat"]


class ImportValidationError(Exception):
    pass


def list_sheets(file_path: str):
    xl = pd.ExcelFile(file_path)
    return xl.sheet_names


def read_sheet(file_path: str, sheet_name: str) -> pd.DataFrame:
    df = pd.read_excel(file_path, sheet_name=sheet_name)
    return df


def validate_columns(df: pd.DataFrame):
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ImportValidationError(
            f"Kolom berikut tidak ditemukan pada sheet: {', '.join(missing)}. "
            f"Kolom yang ditemukan: {', '.join(map(str, df.columns))}"
        )


def normalize_dataframe(df: pd.DataFrame, sumber_import: str) -> pd.DataFrame:
    """
    Membersihkan & menormalisasi dataframe mentah menjadi siap-insert:
    kolom -> tanggal (date ISO), nama_wilayah (str upper trim), total_berat (float)
    """
    df = df.copy()
    validate_columns(df)

    # --- Tanggal: bisa berupa datetime, atau serial number Excel ---
    date_col = df["Act. Gds Mvmnt Date"]
    if pd.api.types.is_numeric_dtype(date_col):
        tanggal = pd.to_datetime(date_col, unit="D", origin="1899-12-30")
    else:
        tanggal = pd.to_datetime(date_col, errors="coerce")

    df["tanggal"] = tanggal.dt.strftime("%Y-%m-%d")
    df["nama_wilayah"] = df["Kabupaten/Kota"].astype(str).str.strip().str.upper()
    df["total_berat"] = pd.to_numeric(df["Total Berat"], errors="coerce")

    before = len(df)
    df = df.dropna(subset=["tanggal", "nama_wilayah", "total_berat"])
    df = df[df["nama_wilayah"] != "NAN"]
    dropped = before - len(df)

    df["sumber_import"] = sumber_import

    result = df[["tanggal", "nama_wilayah", "total_berat", "sumber_import"]].copy()
    result.attrs["dropped_rows"] = dropped
    return result


def aggregate_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Karena tabel Supabase punya UNIQUE (tanggal, nama_wilayah, sumber_import),
    baris dengan kombinasi sama (mis. data 2026 yang punya banyak baris kecil
    per hari per kab/kota) dijumlahkan terlebih dahulu agar tidak bentrok
    saat upsert dan agar nilainya representasi total harian yang benar.
    """
    agg = (
        df.groupby(["tanggal", "nama_wilayah", "sumber_import"], as_index=False)["total_berat"]
        .sum()
    )
    return agg


def dataframe_to_records(df: pd.DataFrame) -> list:
    records = df.to_dict(orient="records")
    # pastikan tipe data JSON-serializable (numpy -> python native)
    clean = []
    for r in records:
        clean.append(
            {
                "tanggal": r["tanggal"],
                "nama_wilayah": r["nama_wilayah"],
                "total_berat": float(r["total_berat"]),
                "sumber_import": r["sumber_import"],
            }
        )
    return clean


def process_upload(file_path: str, sheet_name: str, sumber_import: str):
    """
    Pipeline lengkap: baca sheet -> validasi -> normalisasi -> agregasi dedup
    -> kembalikan (records siap-insert, ringkasan).
    """
    df_raw = read_sheet(file_path, sheet_name)
    df_norm = normalize_dataframe(df_raw, sumber_import)
    dropped = df_norm.attrs.get("dropped_rows", 0)
    df_agg = aggregate_duplicates(df_norm)
    records = dataframe_to_records(df_agg)

    ringkasan = {
        "baris_mentah": len(df_raw),
        "baris_valid": len(df_norm),
        "baris_dibuang": dropped,
        "baris_setelah_agregasi": len(df_agg),
        "tanggal_mulai": df_agg["tanggal"].min() if not df_agg.empty else None,
        "tanggal_akhir": df_agg["tanggal"].max() if not df_agg.empty else None,
        "jumlah_wilayah": df_agg["nama_wilayah"].nunique() if not df_agg.empty else 0,
    }
    return records, ringkasan
