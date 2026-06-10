"""
Wrapper tunggal untuk klien Supabase, supaya seluruh aplikasi
memakai satu instance koneksi yang sama.
"""
from supabase import create_client, Client
from config import Config

_supabase_client: Client = None


def get_supabase() -> Client:
    """Mengembalikan instance Supabase client (singleton)."""
    global _supabase_client
    if _supabase_client is None:
        if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
            raise RuntimeError(
                "SUPABASE_URL / SUPABASE_KEY belum diatur. Periksa file .env Anda."
            )
        _supabase_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    return _supabase_client
