# 🌾 Produktivitas Pertanian Antarnegara

Sistem data end-to-end untuk menjawab satu pertanyaan: **faktor apa yang berkaitan dengan hasil serealia per hektare antarnegara pada 2000–2024?**

```
World Bank API ─┐
                ├─► Apache Airflow ─► MySQL ─► Notebook analisis ─► Dashboard Streamlit
NASA POWER API ─┘   (extract·validate·load)   (1 dimensi + 3 fakta)   (assessing → cleaning → EDA → model)
```

## Daftar isi

- [Ringkasan](#ringkasan)
- [Pertanyaan penelitian](#pertanyaan-penelitian)
- [Sumber data](#sumber-data)
- [Struktur database](#struktur-database)
- [Pipeline Airflow](#pipeline-airflow)
- [Notebook analisis](#notebook-analisis)
- [Dashboard Streamlit](#dashboard-streamlit)
- [Struktur folder](#struktur-folder)
- [Cara menjalankan](#cara-menjalankan)
- [Pemecahan masalah](#pemecahan-masalah)
- [Keputusan desain](#keputusan-desain)
- [Keterbatasan](#keterbatasan)
- [Sumber dan atribusi](#sumber-dan-atribusi)

## Ringkasan

| | |
|---|---|
| **Topik** | Keterkaitan pupuk, ekonomi, dan iklim terhadap produktivitas serealia |
| **Cakupan** | 42 negara (ASEAN, produsen pertanian besar, dan pembanding), tahun 2000–2024 |
| **Data utama** | Pertanian (`fact_agriculture`), target: hasil serealia (kg/ha) |
| **Data pendukung** | Ekonomi (`fact_economic`) dan iklim (`fact_climate`) |
| **Teknologi** | Apache Airflow (Astro CLI), MySQL 8, Python (pandas, scikit-learn, scipy), Plotly, Streamlit |

Prinsip yang dipegang: **DAG hanya mengambil dan menyimpan data mentah**. Pemeriksaan dan pembersihan data dilakukan di notebook sehingga prosesnya terlihat (assessing → cleaning → assessing ulang).

## Pertanyaan penelitian

| # | Jenis | Pertanyaan | Metode |
|---|---|---|---|
| Q1 | Sederhana | Negara dan kawasan mana yang hasil serealianya tertinggi? | Peringkat rata-rata per negara dan median per kawasan |
| Q2 | Analisis | Apakah pemakaian pupuk berkaitan dengan hasil serealia? | Scatter plot, korelasi Spearman dan Pearson (pupuk skala log) |
| Q3 | Analisis lanjutan | Apakah ekonomi dan iklim berkaitan dengan hasil serealia, dan di mana posisi Indonesia? | Heatmap korelasi, uji Kruskal-Wallis antar kelompok pendapatan, tren Indonesia vs ASEAN |
| Q4 | Model AI | Dapatkah karakteristik negara mengklasifikasikan hasil serealia menjadi Rendah / Sedang / Tinggi? | Klasifikasi dengan empat model dan validasi silang per negara |

> Data bersifat observasional, sehingga seluruh temuan adalah **keterkaitan (asosiasi)**, bukan bukti sebab-akibat.

## Sumber data

Keduanya gratis dan **tanpa API key**.

| Sumber | Data | Dipakai untuk |
|---|---|---|
| [World Bank Indicators API](https://datahelpdesk.worldbank.org/knowledgebase/articles/889392-about-the-indicators-api-documentation) | Indikator pertanian, ekonomi, kependudukan, dan metadata negara | `dim_country`, `fact_agriculture`, `fact_economic` |
| [NASA POWER](https://power.larc.nasa.gov/docs/services/api/) (bulanan, komunitas AG) | Suhu dan curah hujan di koordinat ibu kota | `fact_climate` |

### Indikator World Bank

| Kode | Kolom MySQL | Arti | Tabel |
|---|---|---|---|
| `AG.YLD.CREL.KG` | `cereal_yield_kg_ha` | Hasil serealia (kg/ha) — **target** | `fact_agriculture` |
| `AG.CON.FERT.ZS` | `fertilizer_kg_ha` | Pupuk (kg/ha lahan arable) | `fact_agriculture` |
| `AG.LND.ARBL.ZS` | `arable_land_pct` | Lahan arable (% luas lahan) | `fact_agriculture` |
| `NV.AGR.TOTL.ZS` | `agri_value_added_pct` | Nilai tambah pertanian (% PDB) | `fact_agriculture` |
| `SL.AGR.EMPL.ZS` | `agri_employment_pct` | Tenaga kerja pertanian (%) | `fact_agriculture` |
| `NY.GDP.PCAP.CD` | `gdp_per_capita_usd` | GDP per kapita (US$) | `fact_economic` |
| `SP.POP.TOTL` | `population` | Populasi | `fact_economic` |

### Iklim (NASA POWER)

Parameter `T2M` (suhu) dan `PRECTOTCORR` (curah hujan terkoreksi) dari endpoint bulanan. Nilai tahunan diambil dari kunci `MM=13`; curah hujan dikonversi dari mm/hari menjadi mm/tahun. Kolom `months_with_data` mencatat berapa dari 12 bulan yang datanya valid (nilai −999 dianggap hilang).

## Struktur database

Satu tabel dimensi dirujuk tiga tabel fakta lewat *foreign key* `country_id`.

| Tabel | Jenis | Isi | Kunci |
|---|---|---|---|
| `dim_country` | Dimensi | Nama, kawasan, kelompok pendapatan, ibu kota, koordinat | `UNIQUE (country_code)` |
| `fact_agriculture` | Fakta | Hasil serealia, pupuk, lahan arable, nilai tambah dan tenaga kerja pertanian | FK `country_id`, `UNIQUE (country_id, year)` |
| `fact_economic` | Fakta | GDP per kapita, populasi | FK `country_id`, `UNIQUE (country_id, year)` |
| `fact_climate` | Fakta | Suhu rata-rata, total curah hujan, jumlah bulan data valid | FK `country_id`, `UNIQUE (country_id, year)` |

Satu baris tabel fakta mewakili **satu negara pada satu tahun**. Ketiganya digabung kembali lewat negara + tahun saat analisis. Dengan 42 negara × 25 tahun, batas atas tiap tabel fakta adalah 1.050 baris (sebelum cleaning).

## Pipeline Airflow

DAG: `pertanian_worldbank_pipeline` (`schedule="@once"`, `retries=2`)

```
create_tables_mysql
        │
extract_countries
        │
   ┌────┴─────────────┐
extract_worldbank   extract_climate
   └────┬─────────────┘
     validate
        │
  load_dim_country
        │
   ┌────┼──────────────┐
load_fact_agriculture  load_fact_economic  load_fact_climate
   └────┼──────────────┘
   verify_load
```

| Task | Fungsi |
|---|---|
| `create_tables_mysql` | Membuat 4 tabel (tabel induk lebih dulu) |
| `extract_countries` | Metadata negara dari World Bank, hanya negara dalam `SCOPE` |
| `extract_worldbank` | Indikator pertanian dan ekonomi 2000–2024 |
| `extract_climate` | Suhu dan curah hujan per negara dari NASA POWER |
| `validate` | **Hanya memeriksa** (tidak kosong, tidak ada duplikat kunci, mencatat % kosong per kolom) |
| `load_*` | Memuat ke MySQL dengan *upsert* |
| `verify_load` | Memastikan tabel terisi, tidak ada baris yatim (FK konsisten), dan menghitung baris gabungan yang siap dianalisis |

Sifat penting:

- **Nilai kosong (NULL) sengaja dibiarkan.** Cleaning dilakukan di notebook.
- **Upsert** (`INSERT ... ON DUPLICATE KEY UPDATE`), bukan `TRUNCATE`, sehingga aman dijalankan berulang dan tidak membuat baris ganda. `TRUNCATE` juga tidak bisa dipakai pada tabel yang dirujuk foreign key.
- **Retry** untuk error jaringan, HTTP 429, dan 5xx (jeda bertahap). Error permanen (misalnya parameter salah) langsung gagal.
- **Cache iklim per negara** (`power_cache/`, berlaku 7 hari): bila task gagal di tengah jalan, menjalankan ulang melanjutkan dari negara yang belum selesai.
- Indikator **non-esensial** yang gagal dilewati (kolom jadi NULL); indikator esensial (`cereal_yield_kg_ha`, `gdp_per_capita_usd`) menghentikan DAG.
- Konfigurasi ada di bagian atas file DAG: `SCOPE`, `START_YEAR`, `END_YEAR`, `MYSQL_CONN_ID`, `DATA_DIR` (bisa diubah lewat variabel lingkungan `PIPELINE_DATA_DIR`).

## Notebook analisis

Notebook membaca empat tabel dari MySQL, lalu bekerja berurutan:

1. **Data gathering**: memuat `dim_country`, `fact_agriculture`, `fact_economic`, `fact_climate`.
2. **Assessing (sebelum cleaning)**: `info`, `describe`, nilai kosong, duplikat, dan nilai tidak valid per tabel.
3. **Cleaning** (lihat aturan di bawah).
4. **Assessing ulang**: pemeriksaan yang sama pada data bersih, dibandingkan dengan kondisi sebelumnya.
5. **EDA dan analisis** untuk Q1–Q3.
6. **Pemodelan** untuk Q4.
7. **Ekspor** hasil ke folder `dashboard_data/` untuk dashboard.

### Aturan cleaning

| Masalah | Keputusan | Alasan |
|---|---|---|
| Kolom teknis (`*_id`, `loaded_at`) | Dibuang | Tidak dipakai dalam analisis |
| Duplikat pada (negara, tahun) | Dihapus, simpan yang terakhir | Satu negara-tahun hanya boleh satu baris |
| Nilai di luar aturan validitas | Diubah menjadi kosong (NaN) | Baris masih punya indikator lain yang valid |
| Baris yang seluruh indikatornya kosong | Dihapus | Tidak membawa informasi |
| Celah pendek (≤ 2 tahun) pada indikator yang berubah lambat | Interpolasi linear dalam satu negara | Lahan arable, tenaga kerja, dan nilai tambah berubah bertahap |
| Kosong pada hasil serealia dan pupuk | **Tidak diisi** | Variabel inti; mengisinya berarti mengarang data |
| Outlier hasil serealia | Ditandai (aturan IQR), **tidak dihapus** | Hasil sangat tinggi bisa nyata |

Aturan validitas: hasil serealia dan pupuk tidak negatif · persentase 0–100 · GDP per kapita dan populasi positif · suhu −60 s.d. 60 °C · curah hujan tidak negatif · jumlah bulan data valid 0–12.

### Model (Q4)

- **Target**: tingkat hasil serealia (Rendah / Sedang / Tinggi) dari tertil. Ambang dihitung **hanya dari data latih**.
- **Fitur**: pupuk, lahan arable, nilai tambah dan tenaga kerja pertanian, log GDP per kapita, log populasi, suhu, curah hujan, tahun, kawasan, kelompok pendapatan. Hasil serealia **tidak** menjadi fitur.
- **Pembagian latih/uji per negara**: satu negara hanya masuk salah satu sisi, mencegah kebocoran data.
- **Imputasi di dalam pipeline** (median untuk numerik, nilai terbanyak untuk kategori), dipelajari hanya dari data latih.
- **Empat model**: Baseline, Decision Tree, Random Forest, Gradient Boosting. Penentu pemilihan: F1-macro.
- **Evaluasi**: akurasi, presisi, recall, F1 (macro), laporan per kelas, confusion matrix, *permutation importance*, dan validasi silang 5-lipat per negara.

Fokus penilaian ada pada proses dan interpretasi, bukan mengejar akurasi.

## Dashboard Streamlit

`app.py` membaca file hasil ekspor notebook dari folder `data/` dan **tidak membutuhkan koneksi database**, sehingga aman dipublikasikan.

| Tab | Isi |
|---|---|
| Beranda | Latar belakang, empat pertanyaan, alur sistem, diagram struktur database |
| Penjelasan | Judul, tujuan, alur penelitian, tabel dimensi vs fakta, target dan fitur |
| Assessing | Pemeriksaan data mentah per tabel |
| Cleaning | Aturan dan hasil pembersihan |
| Assessing ulang | Perbandingan sebelum vs sesudah |
| EDA (Q1–Q3) | Visualisasi jawaban tiga pertanyaan pertama |
| Model (Q4) | Metrik, perbandingan model, confusion matrix, fitur penting, cek per negara |
| Data & Kesimpulan | Tabel data terfilter (unduh CSV), keterbatasan, sumber |

**Filter** di sidebar: rentang tahun, kelompok pendapatan, kawasan, negara, dan kategori hasil serealia. Filter berlaku untuk kartu angka, EDA, dan tabel data; bagian Assessing, Cleaning, dan Model menampilkan hasil lengkap dari notebook.

### File yang dibutuhkan di folder `data/`

| File | Dipakai untuk |
|---|---|
| `data_bersih_pertanian.csv` | Data gabungan bersih (utama) |
| `hasil_klasifikasi.csv` | Aktual vs prediksi per negara-tahun |
| `meta_analisis.json` | Ambang kategori, jumlah data latih/uji, ringkasan cleaning |
| `ringkasan_assessing.csv`, `kolom_assessing.csv`, `describe_assessing.csv` | Tab Assessing dan Assessing ulang |
| `log_cleaning.csv` | Tab Cleaning |
| `perbandingan_model.csv`, `importance_fitur.csv`, `laporan_klasifikasi.csv` | Tab Model |

Semua file ini dihasilkan otomatis oleh bagian **Ekspor** di notebook ke folder `dashboard_data/`.

## Struktur folder

> Usulan susunan. Sesuaikan dengan struktur repositori kamu.

```
.
├── dags/
│   └── pertanian_worldbank_pipeline.py     # DAG Airflow
├── include/data/                           # CSV perantara DAG + cache iklim (dibuat otomatis)
├── notebook/
│   └── <nama-notebook>.ipynb               # assessing → cleaning → EDA → model → ekspor
├── dashboard_data/                         # hasil ekspor notebook
├── dashboard/
│   ├── app.py
│   ├── requirements.txt
│   └── data/                               # salinan isi dashboard_data/
└── README.md
```

## Cara menjalankan

### Prasyarat

- Docker Desktop
- [Astro CLI](https://www.astronomer.io/docs/astro/cli/install-cli)
- Python 3.10+ untuk notebook dan dashboard

### 1. Jalankan MySQL

```powershell
docker run --name mysql-praktikum -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=airflow_db -p 3306:3306 -d mysql:8.0
```

Bila container sudah pernah dibuat, cukup `docker start mysql-praktikum`. Kredensial di atas hanya untuk belajar di komputer lokal.

### 2. Siapkan Airflow (Astro)

Salin `pertanian_worldbank_pipeline.py` ke folder `dags/` proyek Astro, lalu pastikan `requirements.txt` proyek Astro memuat:

```
apache-airflow-providers-mysql
pandas
mysql-connector-python
requests
```

```powershell
astro dev start
```

Buka alamat Airflow UI yang ditampilkan di terminal (di Windows bisa berupa port acak, mis. `localhost:12851`; login bawaan `admin` / `admin`).

### 3. Buat koneksi MySQL di Airflow

**Admin → Connections → +**

| Field | Nilai |
|---|---|
| Connection Id | `mysql-local` |
| Connection Type | MySQL |
| Host | `host.docker.internal` |
| Schema | `airflow_db` |
| Login | `root` |
| Password | `root` |
| Port | `3306` |

Ketik langsung, jangan salin-tempel, agar tidak ada spasi atau karakter tab tersembunyi di depan nilai.

### 4. Jalankan DAG

Aktifkan toggle DAG `pertanian_worldbank_pipeline`. Karena `schedule="@once"`, DAG berjalan sekali begitu di-unpause (atau tekan **Trigger**). Tahap `extract_climate` paling lama karena memanggil NASA POWER per negara dengan jeda antar-request.

Periksa hasilnya:

```sql
SELECT COUNT(*) FROM dim_country;
SELECT COUNT(*) FROM fact_agriculture;
SELECT COUNT(*) FROM fact_economic;
SELECT COUNT(*) FROM fact_climate;
```

### 5. Jalankan notebook

```powershell
pip install pandas numpy scipy scikit-learn matplotlib seaborn plotly mysql-connector-python nbformat jupyter
```

Buka notebook, pilih **Run All** dengan MySQL menyala. Bagian **Ekspor** di akhir akan membuat folder `dashboard_data/`.

### 6. Jalankan dashboard

Salin isi `dashboard_data/` ke `dashboard/data/`, lalu:

```powershell
cd dashboard
pip install streamlit pandas numpy plotly scipy
streamlit run app.py
```

Dashboard terbuka di `http://localhost:8501`.

### Publikasi (opsional)

Dashboard tidak butuh database, jadi bisa dipublikasikan di Streamlit Community Cloud: unggah repositori ke GitHub (termasuk `dashboard/data/` dan `dashboard/requirements.txt`), lalu atur *Main file path* ke `dashboard/app.py`.

## Pemecahan masalah

| Gejala | Penyebab dan solusi |
|---|---|
| `Unknown database '\tairflow_db'` | Ada karakter tab tersembunyi di depan nilai Schema pada koneksi. Hapus isinya dan ketik ulang. |
| Task gagal `HTTP 429` atau timeout | Batas akses API. Jalankan ulang task; cache iklim melanjutkan dari negara yang belum selesai. |
| `3 negara berturut-turut gagal` di `extract_climate` | NASA POWER sedang bermasalah atau terbatasi. Baca pesan error di log, tunggu, lalu jalankan ulang. |
| Notebook: `Can't connect to MySQL server on 'localhost:3306'` | Container MySQL belum menyala: `docker start mysql-praktikum`, tunggu sampai muncul `ready for connections`. |
| Grafik Plotly tidak tampil di notebook | `pip install nbformat` pada lingkungan Python yang sama dengan kernel notebook. |
| Dashboard: *File data tidak ditemukan* | Jalankan bagian Ekspor notebook, lalu salin isi `dashboard_data/` ke folder `data/` di samping `app.py`. |
| Tab Assessing/Cleaning/Model kosong dengan pesan peringatan | File ekspor belum lengkap. Jalankan ulang bagian Ekspor notebook. |
| `streamlit run "app(1).py"` gagal | Nama file mengandung tanda kurung. Ganti nama jadi `app.py`. |

## Keputusan desain

- **Skema dimensi + fakta** dengan foreign key dan unique key: keterangan negara disimpan sekali, tabel fakta tidak saling merusak, dan duplikat ditolak di level database.
- **Data mentah tetap mentah di database.** Nilai kosong adalah bagian dari data (negara tidak melaporkan indikator itu), bukan nol; keputusan penanganannya diambil dan didokumentasikan di notebook.
- **Upsert, bukan truncate**, agar DAG idempoten.
- **Klasifikasi tertil** karena pertanyaannya "tinggi atau rendah dibanding negara lain" dan keputusannya berbentuk kategori; ambang dihitung dari data latih saja.
- **Pembagian per negara** agar model diuji pada negara yang belum pernah dilihat, bukan pada tahun lain dari negara yang sama.
- **Korelasi Spearman** untuk hubungan yang sebarannya miring (pupuk, GDP), dan tidak menonjolkan nilai p karena pengamatan negara-tahun tidak independen.

## Keterbatasan

1. Data observasional: hanya menunjukkan keterkaitan, bukan sebab-akibat.
2. Hasil serealia mencakup serealia secara gabungan, tidak per komoditas.
3. Iklim diambil di koordinat ibu kota sehingga hanya mewakili kondisi negara secara kasar.
4. Banyak nilai kosong pada indikator tertentu, terutama pupuk dan tahun-tahun terbaru.
5. Cakupan dibatasi pada 42 negara, bukan seluruh dunia.
6. Kelompok pendapatan memakai klasifikasi World Bank terkini untuk seluruh tahun.

## Sumber dan atribusi

- **World Bank Open Data** — indikator pertanian, ekonomi, dan kependudukan (lisensi CC BY 4.0).
- **NASA POWER** — suhu dan curah hujan (komunitas AG).

## Penulis

- Nama: `<isi>`
- NIM: `<isi>`
- Mata kuliah: `<isi>`
- Institusi: `<isi>`
