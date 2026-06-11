"""
Operasi untuk tabel export_log.
"""
from app.supabase_client import get_supabase


def create_export_log(run_id, nama_file, diunduh_oleh=None):
    sb = get_supabase()
    sb.table("export_log").insert({
        "run_id": run_id,
        "nama_file": nama_file,
        "diunduh_oleh": diunduh_oleh,
    }).execute()
