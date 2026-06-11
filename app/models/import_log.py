"""
Operasi untuk tabel import_log.
"""
from app.supabase_client import get_supabase


def create_log(nama_file, tipe_dataset, jumlah_baris, tanggal_mulai, tanggal_akhir,
                status="sukses", pesan=None, diupload_oleh=None):
    sb = get_supabase()
    payload = {
        "nama_file": nama_file,
        "tipe_dataset": tipe_dataset,
        "jumlah_baris": jumlah_baris,
        "tanggal_mulai": tanggal_mulai,
        "tanggal_akhir": tanggal_akhir,
        "status": status,
        "pesan": pesan,
        "diupload_oleh": diupload_oleh,
    }
    sb.table("import_log").insert(payload).execute()


def list_logs(limit=20):
    sb = get_supabase()
    res = (
        sb.table("import_log")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []
