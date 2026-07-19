-- =====================================================================
-- SKEMA DATABASE — SISTEM FORECASTING PERMINTAAN LPG (ARIMA & SARIMA)
-- PT Pertamina Patra Niaga — Pangkalan Susu, Kab. Langkat, Sumut
-- Skripsi: Cut Rena Mutia (220170188) — Teknik Informatika, Unimal
-- Target  : Supabase (PostgreSQL)
-- =====================================================================
-- Cara pakai:
--   1. Buka Supabase Dashboard > SQL Editor
--   2. Tempel seluruh isi file ini, klik RUN
--   3. (Opsional) jalankan seed.sql untuk membuat akun admin default
-- =====================================================================

-- Ekstensi yang dibutuhkan
create extension if not exists "uuid-ossp";
create extension if not exists pgcrypto;

-- =====================================================================
-- 1. TABEL ADMIN (Auth manual — bukan Supabase Auth)
-- =====================================================================
create table if not exists admin_users (
    id              uuid primary key default uuid_generate_v4(),
    username        varchar(50) unique not null,
    password_hash   text not null,
    full_name       varchar(150),
    email           varchar(150),
    is_active       boolean not null default true,
    last_login_at   timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

comment on table admin_users is 'Akun admin tunggal untuk mengelola sistem (bukan Supabase Auth)';

-- =====================================================================
-- 2. MASTER WILAYAH (Kabupaten/Kota)
-- =====================================================================
create table if not exists wilayah (
    id              serial primary key,
    nama_wilayah    varchar(100) unique not null,
    kode_wilayah    varchar(20),
    is_top_kontributor boolean default false,
    created_at      timestamptz not null default now()
);

comment on table wilayah is 'Master data kabupaten/kota wilayah penyaluran LPG';

-- =====================================================================
-- 3. DATA HISTORIS PENYALURAN (Dataset training: 2023-2025)
--    Sumber: sheet "data_2023-2025_faktualhistoris"
-- =====================================================================
create table if not exists data_historis (
    id              bigserial primary key,
    tanggal         date not null,
    wilayah_id      integer references wilayah(id) on delete set null,
    nama_wilayah    varchar(100) not null,   -- disimpan juga sebagai teks agar tahan terhadap perubahan master
    total_berat     numeric(18,2) not null default 0,
    sumber_import   varchar(150),             -- nama file/batch import
    created_at      timestamptz not null default now(),
    unique (tanggal, nama_wilayah, sumber_import)
);

create index if not exists idx_data_historis_tanggal on data_historis (tanggal);
create index if not exists idx_data_historis_wilayah on data_historis (nama_wilayah);

comment on table data_historis is 'Data historis penyaluran LPG harian per kabupaten/kota (dataset training ARIMA/SARIMA)';

-- =====================================================================
-- 4. DATA AKTUAL 2026 (Data uji/pembanding forecast)
--    Sumber: sheet "data_uji_2026_faktual"
-- =====================================================================
create table if not exists data_aktual_2026 (
    id              bigserial primary key,
    tanggal         date not null,
    wilayah_id      integer references wilayah(id) on delete set null,
    nama_wilayah    varchar(100) not null,
    total_berat     numeric(18,2) not null default 0,
    sumber_import   varchar(150),
    created_at      timestamptz not null default now(),
    unique (tanggal, nama_wilayah, sumber_import)
);

create index if not exists idx_data_aktual_tanggal on data_aktual_2026 (tanggal);
create index if not exists idx_data_aktual_wilayah on data_aktual_2026 (nama_wilayah);

comment on table data_aktual_2026 is 'Data aktual penyaluran LPG (mis. 2026) untuk dibandingkan dengan hasil forecasting';

-- =====================================================================
-- 5. LOG IMPORT DATASET
-- =====================================================================
create table if not exists import_log (
    id              bigserial primary key,
    nama_file       varchar(255) not null,
    tipe_dataset    varchar(30) not null check (tipe_dataset in ('historis', 'aktual_2026')),
    jumlah_baris    integer not null default 0,
    tanggal_mulai   date,
    tanggal_akhir   date,
    status          varchar(20) not null default 'sukses' check (status in ('sukses', 'gagal', 'sebagian')),
    pesan           text,
    diupload_oleh   uuid references admin_users(id) on delete set null,
    created_at      timestamptz not null default now()
);

comment on table import_log is 'Riwayat import file dataset (Excel) oleh admin';

-- =====================================================================
-- 6. RUN FORECASTING (header proses peramalan)
-- =====================================================================
create table if not exists forecast_run (
    id                  uuid primary key default uuid_generate_v4(),
    nama_run            varchar(150),
    wilayah_scope       varchar(100) not null default 'TOTAL',  -- 'TOTAL' (agregat) atau nama kabupaten/kota spesifik
    tanggal_mulai_data  date not null,
    tanggal_akhir_data  date not null,
    horizon_hari        integer not null,           -- jumlah hari yang diramalkan
    tanggal_mulai_prediksi date not null,
    tanggal_akhir_prediksi date not null,
    train_test_split    numeric(4,3) default 0.8,   -- MUTLAK 0.8 (80% train / 20% test), tidak dapat diubah dari form
    bandingkan_aktual   boolean default false,       -- apakah dibandingkan dengan data_aktual_2026

    -- Hasil uji stasioneritas (ADF) sebelum differencing
    adf_statistic_awal     numeric,
    adf_pvalue_awal        numeric,
    adf_stasioner_awal     boolean,
    -- Setelah differencing (jika perlu)
    differencing_order     integer default 0,
    adf_statistic_diff     numeric,
    adf_pvalue_diff        numeric,
    adf_stasioner_diff     boolean,

    -- Batas signifikansi 95% ACF/PACF (±1.96/√n), dipakai sbg garis confidence
    -- interval pada grafik correlogram di halaman detail run
    acf_ci95_sebelum       numeric,
    acf_ci95_sesudah       numeric,

    -- Parameter model ARIMA (p,d,q)
    arima_p             integer,
    arima_d             integer,
    arima_q             integer,
    arima_aic           numeric,
    arima_bic           numeric,
    arima_mae_test      numeric,
    arima_rmse_test     numeric,
    arima_mape_test     numeric,
    arima_mae_aktual    numeric,
    arima_rmse_aktual   numeric,
    arima_mape_aktual   numeric,

    -- Parameter model SARIMA (p,d,q)(P,D,Q)s
    sarima_p            integer,
    sarima_d            integer,
    sarima_q            integer,
    sarima_pp           integer,  -- P (seasonal AR order)
    sarima_dd           integer,  -- D (seasonal differencing order)
    sarima_qq           integer,  -- Q (seasonal MA order)
    sarima_s            integer,  -- s (seasonal period, mis. 7 untuk musiman mingguan)
    sarima_aic          numeric,
    sarima_bic          numeric,
    sarima_mae_test     numeric,
    sarima_rmse_test    numeric,
    sarima_mape_test    numeric,
    sarima_mae_aktual   numeric,
    sarima_rmse_aktual  numeric,
    sarima_mape_aktual  numeric,

    model_terbaik       varchar(10),  -- 'ARIMA' atau 'SARIMA'
    skor_arima          integer default 0,
    skor_sarima         integer default 0,
    catatan             text,

    status              varchar(20) not null default 'selesai' check (status in ('berjalan','selesai','gagal')),
    pesan_error         text,
    dijalankan_oleh     uuid references admin_users(id) on delete set null,
    created_at          timestamptz not null default now()
);

comment on table forecast_run is 'Header setiap kali proses forecasting ARIMA/SARIMA dijalankan beserta ringkasan hasil evaluasi';

-- =====================================================================
-- 7. ACF / PACF VALUES per run (lag 0..30, sebelum & sesudah differencing)
-- =====================================================================
create table if not exists forecast_acf_pacf (
    id              bigserial primary key,
    run_id          uuid not null references forecast_run(id) on delete cascade,
    tahap           varchar(20) not null check (tahap in ('sebelum_diff','sesudah_diff')),
    lag             integer not null,
    acf_value       numeric,
    pacf_value      numeric
);

create index if not exists idx_acf_pacf_run on forecast_acf_pacf (run_id);

comment on table forecast_acf_pacf is 'Nilai ACF & PACF per lag, dipakai untuk grafik korelogram di halaman detail run';

-- =====================================================================
-- 8. DATA TRAIN/TEST yang dipakai dalam run (snapshot agregat harian)
-- =====================================================================
create table if not exists forecast_dataset_point (
    id              bigserial primary key,
    run_id          uuid not null references forecast_run(id) on delete cascade,
    tanggal         date not null,
    nilai_aktual    numeric not null,
    kelompok        varchar(10) not null check (kelompok in ('train','test'))
);

create index if not exists idx_dataset_point_run on forecast_dataset_point (run_id);

comment on table forecast_dataset_point is 'Snapshot data harian (agregat sesuai scope wilayah) yang dipakai sebagai train/test pada satu run forecasting';

-- =====================================================================
-- 9. PREDIKSI PER MODEL (hasil prediksi test-set ARIMA & SARIMA, utk evaluasi)
-- =====================================================================
create table if not exists forecast_prediction_test (
    id              bigserial primary key,
    run_id          uuid not null references forecast_run(id) on delete cascade,
    model           varchar(10) not null check (model in ('ARIMA','SARIMA')),
    tanggal         date not null,
    nilai_aktual    numeric,
    nilai_prediksi  numeric,
    residual        numeric,
    batas_bawah     numeric,   -- confidence interval lower
    batas_atas      numeric    -- confidence interval upper
);

create index if not exists idx_pred_test_run on forecast_prediction_test (run_id, model);

comment on table forecast_prediction_test is 'Prediksi model pada periode data test (utk menghitung MAE/RMSE & plot Prediksi vs Aktual)';

-- =====================================================================
-- 10. PERAMALAN MASA DEPAN (future forecast, tanggal pilihan user)
-- =====================================================================
create table if not exists forecast_prediction_future (
    id              bigserial primary key,
    run_id          uuid not null references forecast_run(id) on delete cascade,
    model           varchar(10) not null check (model in ('ARIMA','SARIMA')),
    tanggal         date not null,
    nilai_prediksi  numeric not null,
    batas_bawah     numeric,
    batas_atas      numeric,
    nilai_aktual_2026 numeric   -- diisi jika tanggal cocok dengan data_aktual_2026 (untuk perbandingan fleksibel)
);

create index if not exists idx_pred_future_run on forecast_prediction_future (run_id, model);

comment on table forecast_prediction_future is 'Hasil peramalan ke depan sesuai rentang tanggal yang dipilih admin, termasuk pembanding aktual 2026 bila tersedia';

-- =====================================================================
-- 11. KONTRIBUSI PER KABUPATEN/KOTA (ringkasan per run, opsional/global)
-- =====================================================================
create table if not exists kontribusi_wilayah (
    id              bigserial primary key,
    nama_wilayah    varchar(100) not null,
    total_penyaluran numeric(18,2) not null default 0,
    persentase      numeric(6,3),
    periode_mulai   date,
    periode_akhir   date,
    dihitung_pada   timestamptz not null default now()
);

comment on table kontribusi_wilayah is 'Ringkasan kontribusi penyaluran LPG per kabupaten/kota untuk grafik & analisis pendukung';

-- =====================================================================
-- 12. EXPORT LOG (riwayat download Excel)
-- =====================================================================
create table if not exists export_log (
    id              bigserial primary key,
    run_id          uuid references forecast_run(id) on delete set null,
    nama_file       varchar(255) not null,
    diunduh_oleh    uuid references admin_users(id) on delete set null,
    created_at      timestamptz not null default now()
);

-- =====================================================================
-- TRIGGER: auto-update updated_at pada admin_users
-- =====================================================================
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_admin_users_updated on admin_users;
create trigger trg_admin_users_updated
    before update on admin_users
    for each row execute function set_updated_at();

-- =====================================================================
-- ROW LEVEL SECURITY
-- Catatan: Proyek ini memakai SUPABASE ANON KEY di backend Flask
-- (bukan service role key). Karena seluruh validasi & otorisasi admin
-- sudah ditangani di sisi Flask (session login), policy berikut dibuat
-- permisif (mengizinkan operasi CRUD via anon key) supaya backend bisa
-- berfungsi penuh. Untuk produksi sesungguhnya, sebaiknya gunakan
-- service role key di server + RLS yang lebih ketat.
-- =====================================================================
alter table admin_users enable row level security;
alter table wilayah enable row level security;
alter table data_historis enable row level security;
alter table data_aktual_2026 enable row level security;
alter table import_log enable row level security;
alter table forecast_run enable row level security;
alter table forecast_acf_pacf enable row level security;
alter table forecast_dataset_point enable row level security;
alter table forecast_prediction_test enable row level security;
alter table forecast_prediction_future enable row level security;
alter table kontribusi_wilayah enable row level security;
alter table export_log enable row level security;

drop policy if exists "allow_all_admin_users" on admin_users;
create policy "allow_all_admin_users" on admin_users for all using (true) with check (true);

drop policy if exists "allow_all_wilayah" on wilayah;
create policy "allow_all_wilayah" on wilayah for all using (true) with check (true);

drop policy if exists "allow_all_data_historis" on data_historis;
create policy "allow_all_data_historis" on data_historis for all using (true) with check (true);

drop policy if exists "allow_all_data_aktual_2026" on data_aktual_2026;
create policy "allow_all_data_aktual_2026" on data_aktual_2026 for all using (true) with check (true);

drop policy if exists "allow_all_import_log" on import_log;
create policy "allow_all_import_log" on import_log for all using (true) with check (true);

drop policy if exists "allow_all_forecast_run" on forecast_run;
create policy "allow_all_forecast_run" on forecast_run for all using (true) with check (true);

drop policy if exists "allow_all_forecast_acf_pacf" on forecast_acf_pacf;
create policy "allow_all_forecast_acf_pacf" on forecast_acf_pacf for all using (true) with check (true);

drop policy if exists "allow_all_forecast_dataset_point" on forecast_dataset_point;
create policy "allow_all_forecast_dataset_point" on forecast_dataset_point for all using (true) with check (true);

drop policy if exists "allow_all_forecast_prediction_test" on forecast_prediction_test;
create policy "allow_all_forecast_prediction_test" on forecast_prediction_test for all using (true) with check (true);

drop policy if exists "allow_all_forecast_prediction_future" on forecast_prediction_future;
create policy "allow_all_forecast_prediction_future" on forecast_prediction_future for all using (true) with check (true);

drop policy if exists "allow_all_kontribusi_wilayah" on kontribusi_wilayah;
create policy "allow_all_kontribusi_wilayah" on kontribusi_wilayah for all using (true) with check (true);

drop policy if exists "allow_all_export_log" on export_log;
create policy "allow_all_export_log" on export_log for all using (true) with check (true);

-- =====================================================================
-- MIGRASI: jalankan blok ini di Supabase (SQL Editor) jika database
-- SUDAH ADA sebelumnya (sudah pernah menjalankan schema di atas), agar
-- kolom baru batas signifikansi 95% ACF/PACF ikut tersedia tanpa perlu
-- membuat ulang tabel dari awal.
-- =====================================================================
alter table forecast_run add column if not exists acf_ci95_sebelum numeric;
alter table forecast_run add column if not exists acf_ci95_sesudah numeric;

-- =====================================================================
-- SELESAI
-- =====================================================================