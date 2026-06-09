# SiForLPG — Sistem Informasi Forecasting Permintaan LPG

Sistem informasi berbasis web untuk meramalkan permintaan penyaluran LPG harian menggunakan model **ARIMA** dan **SARIMA**, dibangun untuk mendukung skripsi:

> **"Forecasting Permintaan LPG Menggunakan Algoritma ARIMA dan SARIMA Berdasarkan Data Historis Penyaluran"**
> Cut Rena Mutia (220170188) — Teknik Informatika, Universitas Malikussaleh
> Studi kasus: PT Pertamina Patra Niaga, Pangkalan Susu, Kab. Langkat, Sumatera Utara

---

## ✨ Fitur Utama

- **Autentikasi Admin** — login manual (username/password, bcrypt-hashed), bukan Supabase Auth.
- **Import Dataset Excel** — upload `datapenelitian1.xlsx` (atau format serupa), deteksi otomatis sheet `data_2023-2025_faktualhistoris` (training) dan `data_uji_2026_faktual` (pembanding).
- **Kelola Data** — lihat, filter (per kabupaten/kota & rentang tanggal), dan hapus dataset.
- **Proses Forecasting Lengkap** mengikuti alur penelitian:
  1. Agregasi data harian per scope wilayah
  2. Split data Train/Test
  3. Uji stasioneritas (ADF Test)
  4. Differencing otomatis bila diperlukan
  5. Analisis ACF & PACF (correlogram)
  6. Pemodelan **ARIMA** (auto-order via `pmdarima`)
  7. Pemodelan **SARIMA** (musiman mingguan, auto-order)
  8. Evaluasi **MAE, RMSE, MAPE** pada data test
  9. Peramalan ke depan sesuai rentang tanggal pilihan admin
  10. Perbandingan fleksibel dengan data aktual 2026 (jika tersedia & tumpang-tindih tanggal)
  11. Penentuan **model terbaik** otomatis berdasarkan skor evaluasi
- **Visualisasi Detail** — setiap tahap proses ditampilkan lengkap (grafik train/test, correlogram ACF/PACF, prediksi vs aktual, peramalan vs aktual 2026).
- **Export Excel Multi-Sheet** — laporan lengkap 11 sheet (ringkasan, data harian, uji stasioneritas, ACF/PACF, parameter model, prediksi, evaluasi, kesimpulan).
- **Tema Light / Dark / System** tersimpan di localStorage.
- **Desain Neumorphism** — palet Pinky · Sky Blue · Teeny Greeny.

---

## 🗂️ Struktur Proyek

```
lpg_forecast/
├── app/
│   ├── routes/            # Blueprint: auth, dashboard, data_management, forecasting, api
│   ├── services/           # Logic inti: excel_import, excel_export, forecast_engine (ARIMA/SARIMA)
│   ├── models/              # Operasi Supabase per tabel
│   ├── templates/          # Jinja2 templates (base, admin/*, auth/*, errors/*)
│   ├── static/css/style.css # Sistem desain neumorphism
│   ├── static/js/theme.js   # Theme switcher & utilitas
│   └── supabase_client.py
├── sql/
│   ├── schema.sql          # Jalankan PERTAMA di Supabase SQL Editor
│   └── seed.sql            # Jalankan KEDUA (akun admin default + master wilayah)
├── config.py
├── run.py                  # Entry point
├── requirements.txt
└── .env                    # Kredensial Supabase (sudah diisi sesuai yang Anda berikan)
```

---

## 🚀 Cara Menjalankan

### 1. Setup Database Supabase

1. Buka **Supabase Dashboard** → project Anda → **SQL Editor**.
2. Jalankan seluruh isi `sql/schema.sql` (membuat semua tabel, index, RLS policy).
3. Jalankan seluruh isi `sql/seed.sql` (membuat akun admin default + master data wilayah).

> **Akun admin default:**
> - Username: `admin`
> - Password: `admin123`
>
> ⚠️ **Segera ubah password setelah login pertama** melalui menu *Profil & Password*.

### 2. Setup Environment Python

```bash
cd lpg_forecast (optional, berada di path)
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

> **Catatan kompatibilitas:** `pmdarima` membutuhkan `numpy<2`. File `requirements.txt` sudah mem-pin versi yang kompatibel (`numpy<2`, `scipy<1.13`, `scikit-learn<1.5`). Jangan upgrade paket-paket ini secara terpisah tanpa menguji ulang `pmdarima`.

### 3. Konfigurasi `.env`

File `.env` sudah berisi kredensial Supabase yang Anda berikan:

```
SUPABASE_URL=https://avqulodebrgmpgswhtbd.supabase.co
SUPABASE_KEY=<anon-key>
SECRET_KEY=your-super-secret-flask-key-change-this-in-production
FLASK_ENV=development
FLASK_DEBUG=True
```

Ganti `SECRET_KEY` dengan string acak sebelum deploy ke produksi.

### 4. Jalankan Aplikasi

```bash
python run.py
```

Buka **http://localhost:5000** di browser. Anda akan diarahkan ke halaman login.

---

## 📊 Format Dataset Excel

File Excel harus memiliki kolom berikut (nama harus persis sama):

| Kolom                  | Tipe     | Keterangan                          |
|-------------------------|----------|--------------------------------------|
| `Act. Gds Mvmnt Date`   | Tanggal  | Tanggal penyaluran                   |
| `Kabupaten/Kota`        | Teks     | Nama wilayah                         |
| `Total Berat`           | Angka    | Jumlah penyaluran (Kg) per baris     |

- **Sheet Historis** (training): sebaiknya dinamai `data_2023-2025_faktualhistoris`.
- **Sheet Aktual 2026** (pembanding): sebaiknya dinamai `data_uji_2026_faktual`.
- Baris dengan kombinasi tanggal + wilayah yang sama akan **otomatis dijumlahkan** (agregasi) saat import, sehingga aman untuk data granular (banyak baris kecil per hari).

> **Catatan penting:** Berdasarkan pemeriksaan `datapenelitian1.xlsx` yang diberikan, sheet `data_2023-2025_faktualhistoris` saat ini hanya berisi **18 baris sampel** (Jan 2023/2024/2025), bukan dataset harian lengkap 3 tahun seperti yang dideskripsikan proposal. Untuk hasil forecasting yang valid secara akademis, pastikan dataset training yang diunggah benar-benar mencakup rentang harian penuh (idealnya ratusan–ribuan baris).

---

## 🧮 Tentang Engine Forecasting

- **Auto-order ARIMA & SARIMA** menggunakan `pmdarima.auto_arima` (stepwise search berbasis AIC), sesuai praktik umum penelitian time series.
- **Musiman SARIMA** diasumsikan periode **7 hari** (pola mingguan), umum untuk data distribusi/penjualan harian.
- **Model terbaik** ditentukan dari skor perbandingan MAE, RMSE, MAPE pada data test (mode "voting": model dengan nilai metrik lebih kecil pada masing-masing metrik mendapat 1 poin).
- Untuk forecasting masa depan (`future`), model di-**refit** menggunakan seluruh data (train+test) dengan order yang sudah ditemukan, lalu diramalkan sesuai horizon tanggal yang dipilih admin.

---

## 🔒 Keamanan & Catatan Produksi

- Proyek ini menggunakan **Supabase anon key** (bukan service role key) dengan **RLS policy permisif** (`USING (true)`) agar backend Flask dapat operasi CRUD penuh. Ini cocok untuk skripsi/demo, namun **tidak direkomendasikan untuk produksi nyata** dengan data sensitif publik.
- Untuk produksi sesungguhnya: gunakan **service role key** di server (jangan expose ke client), perketat RLS, dan pertimbangkan rate-limiting pada endpoint upload.
- Session admin disimpan via Flask session (cookie `HttpOnly`, `SameSite=Lax`), masa berlaku 8 jam.

---

## 🛠️ Troubleshooting

| Masalah | Solusi |
|---|---|
| `ValueError: numpy.dtype size changed...` saat import `pmdarima` | Pastikan environment menggunakan `numpy<2` (lihat `requirements.txt`). Install ulang di virtualenv bersih. |
| Upload Excel gagal "Kolom tidak ditemukan" | Pastikan nama kolom persis: `Act. Gds Mvmnt Date`, `Kabupaten/Kota`, `Total Berat`. |
| Forecasting gagal "Tidak ada data historis" | Upload dataset historis terlebih dahulu melalui menu *Import Excel*. |
| Error koneksi Supabase | Periksa `SUPABASE_URL` & `SUPABASE_KEY` di `.env`, serta pastikan schema sudah dijalankan. |

---

## 📄 Lisensi

Proyek ini dibuat untuk keperluan akademis (skripsi). Bebas digunakan & dimodifikasi sesuai kebutuhan.
