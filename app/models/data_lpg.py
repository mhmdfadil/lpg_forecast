"""
Operasi data untuk tabel data_historis & data_aktual_2026.
"""
from datetime import datetime, timezone
from app.supabase_client import get_supabase

TABLE_MAP = {
    "historis": "data_historis",
    "aktual_2026": "data_aktual_2026",
}

# Wilayah yang dianggap top kontributor berdasarkan seed.sql
# (bisa diubah sesuai kebutuhan, atau dihitung dinamis dari data)
_TOP_KONTRIBUTOR_DEFAULT = {
    "KOTA MEDAN",
    "KABUPATEN DELI SERDANG",
    "KABUPATEN SERDANG BERDAGAI",
    "KOTA BINJAI",
    "KABUPATEN LANGKAT",
}


def _get_wilayah_map() -> dict:
    """
    Ambil semua wilayah dari tabel master, kembalikan dict
    {nama_wilayah_upper: id}.
    """
    sb = get_supabase()
    res = sb.table("wilayah").select("id,nama_wilayah").execute()
    return {r["nama_wilayah"].strip().upper(): r["id"] for r in (res.data or [])}


def _ensure_wilayah(nama_list: list) -> dict:
    """
    Pastikan setiap nama_wilayah dalam nama_list sudah ada di tabel wilayah.
    Jika belum, insert otomatis dengan is_top_kontributor sesuai daftar default.
    Kembalikan dict {nama_wilayah_upper: id} yang sudah lengkap.
    """
    sb = get_supabase()
    wilayah_map = _get_wilayah_map()

    nama_baru = [
        n for n in {n.strip().upper() for n in nama_list if n}
        if n not in wilayah_map
    ]

    if nama_baru:
        payload = [
            {
                "nama_wilayah": nama,
                "is_top_kontributor": nama in _TOP_KONTRIBUTOR_DEFAULT,
            }
            for nama in nama_baru
        ]
        sb.table("wilayah").upsert(payload, on_conflict="nama_wilayah").execute()
        # Refresh map setelah insert
        wilayah_map = _get_wilayah_map()

    return wilayah_map


def insert_batch(tipe: str, rows: list, batch_size: int = 500):
    """
    Insert data secara batch ke tabel yang sesuai.
    - Otomatis insert nama_wilayah baru ke tabel master wilayah jika belum ada.
    - Mengisi wilayah_id dari hasil lookup.
    - Setelah semua batch selesai, refresh tabel kontribusi_wilayah.
    rows: list[dict] dengan key: tanggal, nama_wilayah, total_berat, sumber_import
    """
    sb = get_supabase()
    table = TABLE_MAP[tipe]

    # Kumpulkan semua nama wilayah unik dari rows, pastikan sudah ada di master
    semua_nama = [r.get("nama_wilayah", "") for r in rows]
    wilayah_map = _ensure_wilayah(semua_nama)

    inserted = 0
    for i in range(0, len(rows), batch_size):
        chunk = rows[i : i + batch_size]
        enriched = []
        for row in chunk:
            nama = (row.get("nama_wilayah") or "").strip().upper()
            enriched.append({
                **row,
                "wilayah_id": wilayah_map.get(nama),
            })
        sb.table(table).upsert(
            enriched, on_conflict="tanggal,nama_wilayah,sumber_import"
        ).execute()
        inserted += len(enriched)

    # Refresh kontribusi_wilayah setelah insert selesai
    try:
        _refresh_kontribusi_wilayah(tipe)
    except Exception:
        pass  # Jangan gagalkan insert hanya karena refresh kontribusi error

    return inserted


def _refresh_kontribusi_wilayah(tipe: str):
    """
    Hitung ulang kontribusi per wilayah untuk tipe dataset yang diberikan,
    lalu simpan/perbarui ke tabel kontribusi_wilayah.
    Dipanggil otomatis setiap kali insert_batch berhasil.
    """
    import pandas as pd

    rows = fetch_aggregated_daily(tipe)
    if not rows:
        return

    df = pd.DataFrame(rows)
    df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)

    tanggal_vals = pd.to_datetime(df["tanggal"], errors="coerce")
    periode_mulai = tanggal_vals.min().strftime("%Y-%m-%d") if not tanggal_vals.isna().all() else None
    periode_akhir = tanggal_vals.max().strftime("%Y-%m-%d") if not tanggal_vals.isna().all() else None

    agg = df.groupby("nama_wilayah")["total_berat"].sum()
    total = agg.sum()
    now = datetime.now(timezone.utc).isoformat()

    sb = get_supabase()
    payload = [
        {
            "nama_wilayah": nama,
            "total_penyaluran": round(float(nilai), 2),
            "persentase": round(float(nilai) / total * 100, 3) if total else 0,
            "periode_mulai": periode_mulai,
            "periode_akhir": periode_akhir,
            "dihitung_pada": now,
        }
        for nama, nilai in agg.items()
    ]

    if payload:
        sb.table("kontribusi_wilayah").insert(payload).execute()


def count_rows(tipe: str) -> int:
    sb = get_supabase()
    table = TABLE_MAP[tipe]
    res = sb.table(table).select("id", count="exact").limit(1).execute()
    return res.count or 0


def get_date_range(tipe: str):
    sb = get_supabase()
    table = TABLE_MAP[tipe]
    res_min = sb.table(table).select("tanggal").order("tanggal", desc=False).limit(1).execute()
    res_max = sb.table(table).select("tanggal").order("tanggal", desc=True).limit(1).execute()
    tmin = res_min.data[0]["tanggal"] if res_min.data else None
    tmax = res_max.data[0]["tanggal"] if res_max.data else None
    return tmin, tmax


def get_distinct_wilayah(tipe: str):
    sb = get_supabase()
    table = TABLE_MAP[tipe]
    all_rows = []
    page_size = 1000
    start = 0
    while True:
        res = (
            sb.table(table)
            .select("nama_wilayah")
            .range(start, start + page_size - 1)
            .execute()
        )
        data = res.data or []
        all_rows.extend(data)
        if len(data) < page_size:
            break
        start += page_size
    return sorted({r["nama_wilayah"] for r in all_rows})


def fetch_aggregated_daily(
    tipe: str,
    wilayah: str = None,
    tanggal_mulai: str = None,
    tanggal_akhir: str = None,
):
    """
    Mengambil seluruh baris (tanggal, nama_wilayah, total_berat) dari tabel,
    dengan filter opsional, untuk diagregasi di layer service (pandas).
    Menggunakan pagination agar aman untuk dataset besar (>1000 baris).
    """
    sb = get_supabase()
    table = TABLE_MAP[tipe]
    query = sb.table(table).select("tanggal,nama_wilayah,total_berat")

    if wilayah and wilayah != "TOTAL":
        query = query.eq("nama_wilayah", wilayah)
    if tanggal_mulai:
        query = query.gte("tanggal", tanggal_mulai)
    if tanggal_akhir:
        query = query.lte("tanggal", tanggal_akhir)

    all_rows = []
    page_size = 1000
    start = 0
    while True:
        res = query.range(start, start + page_size - 1).execute()
        data = res.data or []
        all_rows.extend(data)
        if len(data) < page_size:
            break
        start += page_size
    return all_rows


def delete_all(tipe: str):
    sb = get_supabase()
    table = TABLE_MAP[tipe]
    sb.table(table).delete().neq("id", 0).execute()


def get_kontribusi_wilayah(tipe: str = "historis"):
    """
    Hitung kontribusi total per wilayah dari data aktual (real-time dari tabel data).
    Dipakai untuk tampilan dashboard & halaman kontribusi.
    """
    rows = fetch_aggregated_daily(tipe)
    if not rows:
        return []
    import pandas as pd

    df = pd.DataFrame(rows)
    df["total_berat"] = pd.to_numeric(df["total_berat"], errors="coerce").fillna(0)
    agg = df.groupby("nama_wilayah")["total_berat"].sum().sort_values(ascending=False)
    total = agg.sum()
    result = []
    for nama, nilai in agg.items():
        result.append(
            {
                "nama_wilayah": nama,
                "total": float(nilai),
                "persentase": round(float(nilai) / total * 100, 2) if total else 0,
            }
        )
    return result