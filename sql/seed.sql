-- =====================================================================
-- SEED DATA — Jalankan SETELAH schema.sql
-- =====================================================================

-- Akun admin default
-- Username : admin
-- Password : admin123   (GANTI SETELAH LOGIN PERTAMA!)
insert into admin_users (username, password_hash, full_name, email)
values (
    'admin',
    '$2b$12$tAimiqEUAjPoUhEXLQtD4e3RwjeQaTIGZcsnzA2hgGAdh1UsWuEg2',
    'Administrator Sistem',
    'admin@pertaminapatraniaga.local'
)
on conflict (username) do nothing;
