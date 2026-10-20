# Dashboard Produktivitas Pertanian Antarnegara

Dashboard Streamlit yang membaca hasil ekspor notebook (tanpa koneksi database).

## Struktur folder (yang di-upload ke GitHub)

```
repo/
├─ app.py
├─ requirements.txt
├─ .streamlit/
│   └─ config.toml        <- tema terang
└─ data/                  <- isi folder dashboard_data/ dari notebook
    ├─ data_bersih_pertanian.csv
    ├─ hasil_klasifikasi.csv
    ├─ ringkasan_assessing.csv
    ├─ kolom_assessing.csv
    ├─ describe_assessing.csv
    ├─ log_cleaning.csv
    ├─ perbandingan_model.csv
    ├─ importance_fitur.csv
    ├─ pola_kosong.csv
    ├─ dim_country_bersih.csv
    ├─ laporan_klasifikasi.csv
    └─ meta_analisis.json
```

## Langkah

1. Jalankan notebook `analisis_pertanian.ipynb` sampai sel **Ekspor** (bagian 7). Folder `dashboard_data/` akan terbentuk.
2. Salin seluruh isi `dashboard_data/` ke folder `data/` di samping `app.py`.
3. Coba lokal:
   ```
   pip install -r requirements.txt
   streamlit run app.py
   ```
4. Upload folder ke repositori GitHub (pastikan folder `.streamlit/` dan `data/` ikut).
5. Di Streamlit Community Cloud, buat app baru dari repositori itu, pilih branch dan isi *main file path* dengan `app.py`.

## Memperbarui data

MySQL berubah -> jalankan DAG Airflow -> jalankan ulang notebook -> salin `dashboard_data/` ke `data/` -> push ke GitHub.
Dashboard publik akan memakai data baru setelah repositori diperbarui.

## Keamanan

Versi ini **tidak memakai password atau koneksi database**, jadi tidak ada rahasia yang perlu disimpan.
Jangan pernah meng-commit password MySQL ke GitHub.

## Tampilan gelap / warna tidak sesuai

Dashboard sudah dipaksa tampil terang lewat CSS. Agar seluruh komponen (termasuk tabel interaktif) ikut terang, jalankan dari **folder yang berisi `.streamlit/`**:

```
cd folder_dashboard
streamlit run app.py
```

Streamlit membaca `.streamlit/config.toml` dari folder tempat perintah dijalankan, bukan dari folder `app.py`.
Alternatif tanpa file konfigurasi:

```
streamlit run app.py --theme.base light --theme.primaryColor "#2A9D8F"
```
