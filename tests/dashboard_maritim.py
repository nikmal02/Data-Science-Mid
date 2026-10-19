"""
Dashboard Maritim Kendari — Streamlit App
Jalankan dengan: streamlit run dashboard_maritim.py

Prasyarat: tabel raw_angin, raw_gelombang, raw_arus sudah terisi di MySQL
(hasil DAG extract_maritim_kendari di Airflow).
"""

import streamlit as st
import pandas as pd
import numpy as np
import mysql.connector
import plotly.express as px
import plotly.graph_objects as go
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score

# =========================================================
# KONFIGURASI HALAMAN
# =========================================================
st.set_page_config(
    page_title="Dashboard Maritim Kendari",
    page_icon="🌊",
    layout="wide",
)

DB_CONFIG = dict(host="localhost", port=3306, user="root", password="root", database="airflow_db")


# =========================================================
# 1. LOAD & CLEAN DATA (di-cache supaya tidak diulang terus)
# =========================================================
@st.cache_data(ttl=600)
def load_dan_bersihkan_data():
    conn = mysql.connector.connect(**DB_CONFIG)
    df_angin_raw = pd.read_sql("SELECT * FROM raw_angin", conn)
    df_gelombang_raw = pd.read_sql("SELECT * FROM raw_gelombang", conn)
    df_arus_raw = pd.read_sql("SELECT * FROM raw_arus", conn)
    conn.close()

    # --- Cleaning angin ---
    df_angin = df_angin_raw.copy()
    df_angin["tanggal"] = pd.to_datetime(df_angin["tanggal"])
    df_angin = df_angin.drop_duplicates(subset=["tanggal"])
    df_angin = df_angin.dropna(subset=["kecepatan_angin_kmh", "arah_angin_derajat"])
    df_angin = df_angin[df_angin["kecepatan_angin_kmh"] >= 0]
    df_angin = df_angin.sort_values("tanggal").reset_index(drop=True)

    # --- Cleaning gelombang ---
    df_gelombang = df_gelombang_raw.copy()
    df_gelombang["tanggal"] = pd.to_datetime(df_gelombang["tanggal"])
    df_gelombang = df_gelombang.drop_duplicates(subset=["tanggal"])
    df_gelombang = df_gelombang.dropna(subset=["tinggi_gelombang_m"])
    df_gelombang = df_gelombang[df_gelombang["tinggi_gelombang_m"] >= 0]
    df_gelombang = df_gelombang.sort_values("tanggal").reset_index(drop=True)

    # --- Cleaning + agregasi arus (jam -> harian) ---
    df_arus_jam = df_arus_raw.copy()
    df_arus_jam["tanggal"] = pd.to_datetime(df_arus_jam["tanggal"])
    df_arus_jam = df_arus_jam.drop_duplicates(subset=["tanggal"])
    df_arus_jam = df_arus_jam.dropna(subset=["kecepatan_arus_kmh", "arah_arus_derajat"])
    df_arus_jam = df_arus_jam[df_arus_jam["kecepatan_arus_kmh"] >= 0]
    df_arus_jam["tanggal_saja"] = df_arus_jam["tanggal"].dt.date
    df_arus = (
        df_arus_jam.groupby("tanggal_saja")
        .agg(kecepatan_arus_kmh=("kecepatan_arus_kmh", "mean"),
             arah_arus_derajat=("arah_arus_derajat", "mean"))
        .reset_index()
        .rename(columns={"tanggal_saja": "tanggal"})
    )
    df_arus["tanggal"] = pd.to_datetime(df_arus["tanggal"])
    df_arus = df_arus.sort_values("tanggal").reset_index(drop=True)

    # --- Gabungkan ---
    df = (
        df_angin[["tanggal", "kecepatan_angin_kmh", "arah_angin_derajat"]]
        .merge(df_gelombang[["tanggal", "tinggi_gelombang_m", "periode_gelombang_detik", "arah_gelombang_derajat"]],
               on="tanggal", how="inner")
        .merge(df_arus[["tanggal", "kecepatan_arus_kmh", "arah_arus_derajat"]], on="tanggal", how="inner")
    )

    df["angin_sin"] = np.sin(np.radians(df["arah_angin_derajat"]))
    df["angin_cos"] = np.cos(np.radians(df["arah_angin_derajat"]))
    df["arus_sin"] = np.sin(np.radians(df["arah_arus_derajat"]))
    df["arus_cos"] = np.cos(np.radians(df["arah_arus_derajat"]))

    batas_bawah = df["tinggi_gelombang_m"].quantile(0.33)
    batas_atas = df["tinggi_gelombang_m"].quantile(0.66)

    def kategori(t):
        if t <= batas_bawah:
            return "Tenang"
        elif t <= batas_atas:
            return "Sedang"
        return "Bergelombang"

    df["kategori"] = df["tinggi_gelombang_m"].apply(kategori)
    df["tahun"] = df["tanggal"].dt.year
    df["bulan"] = df["tanggal"].dt.month
    df["nama_bulan"] = df["tanggal"].dt.strftime("%B")

    return df, batas_bawah, batas_atas


# =========================================================
# 2. LATIH MODEL (di-cache, hanya latih sekali)
# =========================================================
@st.cache_resource
def latih_model(df):
    fitur = ["kecepatan_angin_kmh", "angin_sin", "angin_cos",
              "kecepatan_arus_kmh", "arus_sin", "arus_cos"]
    X = df[fitur]
    y = df["kategori"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    model = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42)
    model.fit(X_train, y_train)
    akurasi = accuracy_score(y_test, model.predict(X_test))
    return model, akurasi


# =========================================================
# LOAD DATA
# =========================================================
try:
    df, batas_bawah, batas_atas = load_dan_bersihkan_data()
    model, akurasi_model = latih_model(df)
except Exception as e:
    st.error(f"Gagal konek/memuat data dari MySQL. Pastikan container MySQL sudah menyala.\n\nDetail error: {e}")
    st.stop()

WARNA_KATEGORI = {"Tenang": "#4CAF50", "Sedang": "#FFC107", "Bergelombang": "#F44336"}

# =========================================================
# SIDEBAR — FILTER
# =========================================================
st.sidebar.title("🌊 Filter Data")
st.sidebar.markdown("Pilih rentang waktu yang ingin ditampilkan pada dashboard.")

tahun_tersedia = sorted(df["tahun"].unique())
tahun_pilihan = st.sidebar.multiselect(
    "Tahun", options=tahun_tersedia, default=tahun_tersedia
)

bulan_map = {1: "Januari", 2: "Februari", 3: "Maret", 4: "April", 5: "Mei", 6: "Juni",
             7: "Juli", 8: "Agustus", 9: "September", 10: "Oktober", 11: "November", 12: "Desember"}
bulan_tersedia = sorted(df["bulan"].unique())
bulan_pilihan = st.sidebar.multiselect(
    "Bulan", options=bulan_tersedia, default=bulan_tersedia,
    format_func=lambda x: bulan_map[x]
)

df_filter = df[df["tahun"].isin(tahun_pilihan) & df["bulan"].isin(bulan_pilihan)]

st.sidebar.markdown("---")
st.sidebar.caption(f"Menampilkan **{len(df_filter)}** dari total {len(df)} baris data.")
st.sidebar.caption(f"Akurasi model klasifikasi: **{akurasi_model:.1%}**")

# =========================================================
# HALAMAN UTAMA — TAB
# =========================================================
st.title("🌊 Dashboard Maritim Perairan Kendari")
st.caption("Pipeline ETL (Apache Airflow) + Analisis Korelasi + Model Klasifikasi — Angin, Gelombang, Arus Laut")

tab1, tab2 = st.tabs(["📊 Ringkasan & Grafik", "🔮 Prediksi Kondisi Gelombang"])

# ---------------------------------------------------------
# TAB 1: RINGKASAN & GRAFIK
# ---------------------------------------------------------
with tab1:
    if df_filter.empty:
        st.warning("Tidak ada data pada filter yang dipilih. Coba ubah pilihan tahun/bulan di sidebar.")
    else:
        # --- KPI Cards ---
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Rata-rata Tinggi Gelombang", f"{df_filter['tinggi_gelombang_m'].mean():.3f} m")
        col2.metric("Rata-rata Kecepatan Angin", f"{df_filter['kecepatan_angin_kmh'].mean():.2f} km/jam")
        col3.metric("Rata-rata Kecepatan Arus", f"{df_filter['kecepatan_arus_kmh'].mean():.3f} km/jam")
        kategori_dominan = df_filter["kategori"].mode()[0]
        col4.metric("Kondisi Paling Sering", kategori_dominan)

        st.markdown("---")

        # --- Time series tinggi gelombang ---
        fig_ts = px.line(
            df_filter.sort_values("tanggal"), x="tanggal", y="tinggi_gelombang_m",
            title="Tren Tinggi Gelombang", labels={"tanggal": "Tanggal", "tinggi_gelombang_m": "Tinggi gelombang (m)"}
        )
        fig_ts.update_traces(line_color="#F44336")
        st.plotly_chart(fig_ts, use_container_width=True)

        colA, colB = st.columns(2)

        with colA:
            # --- Distribusi kategori ---
            jumlah_kat = df_filter["kategori"].value_counts().reindex(["Tenang", "Sedang", "Bergelombang"])
            fig_bar = px.bar(
                x=jumlah_kat.index, y=jumlah_kat.values,
                color=jumlah_kat.index, color_discrete_map=WARNA_KATEGORI,
                title="Distribusi Kategori Kondisi Gelombang",
                labels={"x": "Kategori", "y": "Jumlah hari"}
            )
            fig_bar.update_layout(showlegend=False)
            st.plotly_chart(fig_bar, use_container_width=True)

        with colB:
            # --- Scatter angin vs gelombang ---
            fig_scatter = px.scatter(
                df_filter, x="kecepatan_angin_kmh", y="tinggi_gelombang_m",
                color="kategori", color_discrete_map=WARNA_KATEGORI,
                title="Angin vs Tinggi Gelombang",
                labels={"kecepatan_angin_kmh": "Kecepatan angin (km/jam)", "tinggi_gelombang_m": "Tinggi gelombang (m)"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        # --- Heatmap korelasi ---
        kolom_numerik = ["kecepatan_angin_kmh", "arah_angin_derajat", "tinggi_gelombang_m",
                           "periode_gelombang_detik", "arah_gelombang_derajat",
                           "kecepatan_arus_kmh", "arah_arus_derajat"]
        matriks_korelasi = df_filter[kolom_numerik].corr()
        fig_heat = px.imshow(
            matriks_korelasi, text_auto=".2f", color_continuous_scale="RdBu_r", zmin=-1, zmax=1,
            title="Heatmap Korelasi Variabel Maritim"
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        # --- Boxplot per bulan ---
        fig_box = px.box(
            df_filter, x="nama_bulan", y="tinggi_gelombang_m",
            title="Sebaran Tinggi Gelombang per Bulan",
            labels={"nama_bulan": "Bulan", "tinggi_gelombang_m": "Tinggi gelombang (m)"}
        )
        st.plotly_chart(fig_box, use_container_width=True)

        # --- Tabel data mentah (opsional, bisa di-expand) ---
        with st.expander("Lihat data tabel (sesuai filter)"):
            st.dataframe(df_filter.sort_values("tanggal"), use_container_width=True)

# ---------------------------------------------------------
# TAB 2: PREDIKSI
# ---------------------------------------------------------
with tab2:
    st.subheader("Prediksi Kondisi Gelombang")
    st.info(
        f"Model klasifikasi (Random Forest) memiliki akurasi **{akurasi_model:.1%}** pada data uji — "
        "lebih baik dibanding tebakan acak (33% untuk 3 kelas), namun belum sepenuhnya akurat. "
        "Gunakan hasil prediksi ini sebagai referensi tambahan, bukan satu-satunya acuan keputusan melaut."
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Kondisi Angin**")
        input_angin_kmh = st.slider("Kecepatan angin (km/jam)", 0.0, 60.0, 15.0, 0.5)
        input_arah_angin = st.slider("Arah angin (derajat, 0=Utara)", 0, 360, 180, 5)

    with col2:
        st.markdown("**Kondisi Arus Laut**")
        input_arus_kmh = st.slider("Kecepatan arus (km/jam)", 0.0, 5.0, 1.0, 0.1)
        input_arah_arus = st.slider("Arah arus (derajat, 0=Utara)", 0, 360, 90, 5)

    if st.button("🔮 Prediksi Sekarang", type="primary"):
        data_baru = pd.DataFrame([{
            "kecepatan_angin_kmh": input_angin_kmh,
            "angin_sin": np.sin(np.radians(input_arah_angin)),
            "angin_cos": np.cos(np.radians(input_arah_angin)),
            "kecepatan_arus_kmh": input_arus_kmh,
            "arus_sin": np.sin(np.radians(input_arah_arus)),
            "arus_cos": np.cos(np.radians(input_arah_arus)),
        }])

        hasil = model.predict(data_baru)[0]
        proba = dict(zip(model.classes_, model.predict_proba(data_baru)[0]))

        warna = WARNA_KATEGORI[hasil]
        st.markdown(
            f"<h2 style='color:{warna};'>Prediksi: {hasil}</h2>",
            unsafe_allow_html=True
        )

        fig_proba = go.Figure(go.Bar(
            x=list(proba.values()), y=list(proba.keys()), orientation="h",
            marker_color=[WARNA_KATEGORI[k] for k in proba.keys()]
        ))
        fig_proba.update_layout(
            title="Tingkat Keyakinan Model per Kategori",
            xaxis_title="Probabilitas", xaxis_range=[0, 1], height=300
        )
        st.plotly_chart(fig_proba, use_container_width=True)

    st.markdown("---")
    st.caption(
        f"Ambang batas kategori (berdasarkan persentil data aktual): "
        f"Tenang ≤ {batas_bawah:.3f} m | Sedang {batas_bawah:.3f}–{batas_atas:.3f} m | "
        f"Bergelombang > {batas_atas:.3f} m"
    )
