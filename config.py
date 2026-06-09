"""
Konfigurasi aplikasi Flask.
Membaca variabel lingkungan dari .env (lihat .env.example).
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SUPABASE_URL = os.environ.get("SUPABASE_URL")
    SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

    FLASK_ENV = os.environ.get("FLASK_ENV", "production")
    DEBUG = os.environ.get("FLASK_DEBUG", "False") == "True"

    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB upload limit
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),"lpg_forecast","uploads")
    ALLOWED_EXTENSIONS = {"xlsx", "xls"}

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 jam

    # Default kolom yang diharapkan pada file dataset
    EXPECTED_COLUMNS = ["Act. Gds Mvmnt Date", "Kabupaten/Kota", "Total Berat"]

    # Nama sheet default sesuai proposal skripsi
    SHEET_HISTORIS_DEFAULT = "data_2023-2025_faktualhistoris"
    SHEET_AKTUAL_DEFAULT = "data_uji_2026_faktual"
