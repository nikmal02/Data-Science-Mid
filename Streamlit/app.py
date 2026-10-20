"""
Dashboard Produktivitas Pertanian Antarnegara
=============================================
Membaca file hasil notebook dari folder `data/` (hasil ekspor folder `dashboard_data/`).
Tidak membutuhkan koneksi database, sehingga aman dipublikasikan di Streamlit Community Cloud.

Jalankan lokal:  streamlit run app.py
"""
import inspect
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy import stats

st.set_page_config(page_title="Produktivitas Pertanian Antarnegara", page_icon="🌾",
                   layout="wide", initial_sidebar_state="expanded")

# =============================================================================
# PALET (terang, satu keluarga warna: teal - sage - sand - peach - coral)
# =============================================================================
BG, KARTU, INK, MUTED, GARIS, GRID = "#F7FAF5", "#FFFFFF", "#2B3A42", "#566872", "#E3EEE8", "#EDF2EF"
TEAL, SAGE, SAND, PEACH, CORAL, SKY, LAV = "#2A9D8F", "#8AB17D", "#E9C46A", "#F4A261", "#E76F51", "#6BB8D9", "#B8A9C9"
MINT, KREM, PERSIK, LANGIT = "#E8F5F1", "#FDF3D7", "#FDE8D8", "#E3F2F9"

SERI = [TEAL, SAND, PEACH, SAGE, SKY, CORAL, LAV]
WARNA_INCOME = {"Low income": CORAL, "Lower middle income": PEACH, "Upper middle income": SAGE, "High income": TEAL}
WARNA_KELAS = {"Rendah": CORAL, "Sedang": SAND, "Tinggi": TEAL}
SKALA_DIV = [[0, CORAL], [0.5, "#FFFFFF"], [1, TEAL]]
SKALA_SEQ = [[0, "#FFFFFF"], [1, TEAL]]

URUT_INCOME = ["Low income", "Lower middle income", "Upper middle income", "High income"]
LABEL = ["Rendah", "Sedang", "Tinggi"]
ASEAN = ["IDN", "MYS", "THA", "VNM", "PHL", "SGP", "KHM", "LAO", "MMR", "BRN"]
TABEL = ["dim_country", "fact_agriculture", "fact_economic", "fact_climate"]
NAMA = {
    "cereal_yield_kg_ha": "Hasil serealia", "fertilizer_kg_ha": "Pupuk", "arable_land_pct": "Lahan arable",
    "agri_value_added_pct": "Nilai tambah agri", "agri_employment_pct": "Tenaga kerja agri",
    "log_gdp": "log GDP/kapita", "log_pop": "log Populasi", "avg_temp_c": "Suhu", "total_precip_mm": "Curah hujan",
}

st.markdown(f"<style>:root{{--bg:{BG};--kartu:{KARTU};--ink:{INK};--muted:{MUTED};--garis:{GARIS};"
            f"--teal:{TEAL};--sand:{SAND};--peach:{PEACH};--coral:{CORAL};--mint:{MINT};--krem:{KREM};--persik:{PERSIK};--langit:{LANGIT};}}</style>",
            unsafe_allow_html=True)
st.markdown("""
<style>
.stApp { background: var(--bg); color: var(--ink); }
.block-container { padding-top: 1.4rem; max-width: 1300px; }
section[data-testid="stSidebar"] { background: #EDF6F1; border-right: 1px solid var(--garis); }
h1, h2, h3, h4 { color: var(--ink); letter-spacing: -0.01em; }
h3 { margin-top: 1.2rem; }

/* ===== KONTRAS: paksa tema terang walau Streamlit di komputer pengguna memakai tema gelap ===== */
html, body { color-scheme: light !important; }
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] { background: var(--bg) !important; color: var(--ink) !important; }
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5 { color: var(--ink); }
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { color: var(--ink) !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p { color: var(--muted) !important; }

.hero { background: linear-gradient(115deg, #DDF2EC 0%, #FDF3D7 55%, #FDE8D8 100%);
        border: 1px solid var(--garis); border-radius: 24px; padding: 30px 36px; margin-bottom: 18px; }
.hero .eyebrow { font-size: 12px; letter-spacing: .14em; text-transform: uppercase; color: var(--teal); font-weight: 700; }
.hero h1 { margin: 6px 0 8px 0; font-size: 2.3rem; line-height: 1.15; }
.hero p { color: var(--muted); margin: 0 0 14px 0; max-width: 820px; font-size: 1.02rem; }
.chip { display: inline-block; background: rgba(255,255,255,.85); border: 1px solid var(--garis); color: var(--ink);
        border-radius: 999px; padding: 4px 12px; margin: 0 6px 6px 0; font-size: 12.5px; font-weight: 600; }

.kartu { background: var(--kartu); border-radius: 18px; padding: 16px 18px 14px 18px; border: 1px solid var(--garis);
         box-shadow: 0 4px 14px rgba(42,157,143,.08); height: 100%; }
.k-label { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); font-weight: 700; }
.k-angka { font-size: 2rem; font-weight: 800; line-height: 1.15; margin: 4px 0 2px 0; color: var(--ink); }
.k-sub { font-size: 12.5px; color: var(--muted); min-height: 18px; }
.delta { font-weight: 700; }
.delta.naik { color: #1F8A7D; } .delta.turun { color: #D9742F; } .delta.netral { color: var(--muted); font-weight: 500; }

.panel { background: var(--kartu); border: 1px solid var(--garis); border-radius: 18px; padding: 18px 22px; margin: 6px 0 12px 0; }
.panel p { margin: 0 0 8px 0; }
.temuan { background: #EAF6F3; border-left: 5px solid var(--teal); border-radius: 12px; padding: 12px 16px; margin: 10px 0 16px 0; }
.peringatan { background: #FFF4E5; border-left: 5px solid var(--peach); border-radius: 12px; padding: 12px 16px; margin: 10px 0 16px 0; }
.mengapa { color: var(--muted); font-size: 14px; margin: -2px 0 8px 0; }

.qkartu { border-radius: 18px; padding: 16px 18px; height: 100%; border: 1px solid var(--garis); }
.qkartu .q { font-size: 12px; font-weight: 800; letter-spacing: .1em; color: var(--ink); opacity: .7; }
.qkartu .t { font-size: 15px; font-weight: 700; margin: 4px 0 6px 0; }
.qkartu .j { font-size: 12.5px; color: var(--muted); }

.alur { display: flex; flex-wrap: wrap; align-items: stretch; gap: 8px; margin: 6px 0 10px 0; }
.langkah { flex: 1 1 140px; border-radius: 16px; padding: 12px 14px; border: 1px solid var(--garis); font-size: 13px; }
.langkah b { display: block; font-size: 14px; margin-bottom: 2px; }
.langkah span { color: var(--muted); font-size: 12px; }
.panah { align-self: center; color: var(--teal); font-weight: 800; font-size: 20px; }

.step { display: flex; gap: 14px; align-items: flex-start; background: var(--kartu); border: 1px solid var(--garis);
        border-radius: 14px; padding: 12px 16px; margin-bottom: 8px; }
.step .no { min-width: 34px; height: 34px; border-radius: 50%; background: var(--teal); color: #fff; font-weight: 800;
            display: flex; align-items: center; justify-content: center; }
div[data-testid="stVerticalBlockBorderWrapper"] { background: var(--kartu); border-radius: 18px; border-color: var(--garis) !important; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; background: #E3F1EC; padding: 6px; border-radius: 16px; flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] { border-radius: 11px; padding: 8px 14px; font-weight: 600; height: auto; }
.stTabs [aria-selected="true"] { background: #FFFFFF; color: var(--teal); box-shadow: 0 2px 8px rgba(42,157,143,.15); }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
.stDownloadButton button, .stButton button { border-radius: 12px; border: 1px solid var(--teal); color: var(--teal); background: #fff; font-weight: 600; }
.stDownloadButton button:hover, .stButton button:hover { background: var(--teal); color: #fff; border-color: var(--teal); }

/* bilah atas (tombol Deploy dan menu) */
header[data-testid="stHeader"] { background: var(--bg) !important; }
header[data-testid="stHeader"] * { color: var(--ink) !important; }

/* sidebar: judul dan label */
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] small { color: var(--ink) !important; }

/* kolom pilihan (selectbox, multiselect, input) */
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, div[data-baseweb="base-input"] {
    background-color: #FFFFFF !important; border-color: var(--garis) !important; color: var(--ink) !important; }
div[data-baseweb="select"] span, div[data-baseweb="select"] input, div[data-baseweb="select"] div { color: var(--ink) !important; }
div[data-baseweb="select"] svg { fill: var(--muted) !important; color: var(--muted) !important; }
div[data-baseweb="select"] input::placeholder { color: var(--muted) !important; }

/* chip pilihan: hijau muda lembut, bukan merah */
span[data-baseweb="tag"] { background-color: #D8EFEA !important; border-radius: 8px !important; }
span[data-baseweb="tag"] span, span[data-baseweb="tag"] svg { color: var(--ink) !important; fill: var(--ink) !important; }

/* daftar pilihan yang muncul saat dropdown dibuka */
div[data-baseweb="popover"] ul, div[data-baseweb="popover"] div[data-baseweb="menu"] { background: #FFFFFF !important; }
div[data-baseweb="popover"] li { color: var(--ink) !important; background: #FFFFFF !important; }
div[data-baseweb="popover"] li:hover, div[data-baseweb="popover"] li[aria-selected="true"] { background: var(--mint) !important; }

/* radio dan checkbox */
div[data-testid="stRadio"] label p, div[data-testid="stRadio"] label div, div[data-testid="stCheckbox"] label p { color: var(--ink) !important; }

/* tab */
.stTabs [data-baseweb="tab"], .stTabs [data-baseweb="tab"] p { color: var(--ink) !important; }
.stTabs [aria-selected="true"], .stTabs [aria-selected="true"] p { color: #1F7F73 !important; }

/* kode di dalam teks (misalnya info, describe): latar hijau muda, teks hijau tua */
.stApp code { background: #E4F3EF !important; color: #1B6E64 !important; border-radius: 6px; padding: 1px 6px; font-size: .88em; }

/* tabel markdown */
.stMarkdown table { border-collapse: collapse; width: 100%; }
.stMarkdown th { background: var(--mint) !important; color: var(--ink) !important; }
.stMarkdown th, .stMarkdown td { border: 1px solid var(--garis) !important; color: var(--ink) !important; padding: 6px 10px; }

/* kotak info/peringatan bawaan Streamlit */
div[data-testid="stAlert"] { background: #EAF6F3 !important; }
div[data-testid="stAlert"] p, div[data-testid="stAlert"] div { color: var(--ink) !important; }

/* tombol */
.stButton button p, .stDownloadButton button p { color: inherit !important; }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# Helper tampilan
# =============================================================================
def _lebar(fn):
    return {"width": "stretch"} if "width" in inspect.signature(fn).parameters else {"use_container_width": True}


def html(t):
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"`(.+?)`", r"<code>\1</code>", t)
    return t.replace("\n", "<br>")


def fmt(x, d=0):
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:,.{d}f}"


def kartu(label, nilai, sub="", warna=TEAL, ikon="", bg=KARTU):
    st.markdown(f'<div class="kartu" style="border-top:5px solid {warna};background:{bg}"><div class="k-label">{ikon} {label}</div>'
                f'<div class="k-angka">{nilai}</div><div class="k-sub">{sub}</div></div>', unsafe_allow_html=True)


def panel(t):
    st.markdown(f'<div class="panel">{html(t)}</div>', unsafe_allow_html=True)


def temuan(t):
    st.markdown(f'<div class="temuan">{html(t)}</div>', unsafe_allow_html=True)


def peringatan(t):
    st.markdown(f'<div class="peringatan">{html(t)}</div>', unsafe_allow_html=True)


def mengapa(t):
    st.markdown(f'<div class="mengapa">{html(t)}</div>', unsafe_allow_html=True)


def langkah(no, judul, isi):
    st.markdown(f'<div class="step"><div class="no">{no}</div><div><b>{judul}</b><br>'
                f'<span style="color:{MUTED}">{html(isi)}</span></div></div>', unsafe_allow_html=True)


def delta(nilai, acuan):
    if acuan in (0, None) or pd.isna(acuan) or pd.isna(nilai):
        return ""
    p = (nilai / acuan - 1) * 100
    if abs(p) < 0.5:
        return '<span class="delta netral">≈ sama dengan seluruh data</span>'
    return (f'<span class="delta naik">▲ {abs(p):.0f}% vs seluruh data</span>' if p > 0
            else f'<span class="delta turun">▼ {abs(p):.0f}% vs seluruh data</span>')


def gaya(fig, tinggi=None):
    fig.update_layout(template="plotly_white", paper_bgcolor="white", plot_bgcolor="white", colorway=SERI,
                      font=dict(family="Inter, Segoe UI, Helvetica, Arial, sans-serif", color=INK, size=13),
                      title=dict(font=dict(size=16)), margin=dict(l=14, r=14, t=56, b=14),
                      legend=dict(bgcolor="rgba(255,255,255,0)"))
    fig.update_xaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GARIS)
    fig.update_yaxes(gridcolor=GRID, zerolinecolor=GRID, linecolor=GARIS)
    if tinggi:
        fig.update_layout(height=tinggi)
    return fig


def grafik(fig, key, tinggi=None):
    with st.container(border=True):
        st.plotly_chart(gaya(fig, tinggi), theme=None, key=key, **_lebar(st.plotly_chart))


def tabel(df, **kw):
    st.dataframe(df, hide_index=True, **_lebar(st.dataframe), **kw)


def kekuatan(r):
    a = abs(r)
    k = "sangat lemah" if a < .2 else "lemah" if a < .4 else "sedang" if a < .6 else "kuat" if a < .8 else "sangat kuat"
    return f"{k}, {'positif' if r > 0 else 'negatif'}"


def metrik(m):
    """Akurasi dan metrik macro; konsisten dengan scikit-learn (macro atas kelas yang muncul)."""
    a, p = m["kategori_aktual"], m["prediksi_kategori"]
    labs = [l for l in LABEL if l in set(a) | set(p)]
    P, R, F = [], [], []
    for l in labs:
        tp = int(((a == l) & (p == l)).sum()); fp = int(((a != l) & (p == l)).sum()); fn = int(((a == l) & (p != l)).sum())
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        P.append(pr); R.append(rc); F.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return {"akurasi": float((a == p).mean()), "presisi": float(np.mean(P)), "recall": float(np.mean(R)), "f1": float(np.mean(F))}


# =============================================================================
# Muat data
# =============================================================================
BASE = Path(__file__).parent
DATA_DIR = BASE / "data" if (BASE / "data" / "data_bersih_pertanian.csv").exists() else BASE


@st.cache_data
def baca_csv(nama):
    p = DATA_DIR / nama
    return pd.read_csv(p) if p.exists() else None


@st.cache_data
def baca_meta():
    p = DATA_DIR / "meta_analisis.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


data = baca_csv("data_bersih_pertanian.csv")
hasil = baca_csv("hasil_klasifikasi.csv")
meta = baca_meta()

st.markdown(
    '<div class="hero"><div class="eyebrow">Sistem data end-to-end · Tugas Data Science</div>'
    '<h1>🌾 Produktivitas Pertanian Antarnegara</h1>'
    '<p>Dari API terbuka, Airflow, dan MySQL sampai analisis, model, dan dashboard: faktor apa yang berkaitan dengan hasil serealia per hektare?</p>'
    '<span class="chip">World Bank API</span><span class="chip">NASA POWER</span><span class="chip">Apache Airflow</span>'
    '<span class="chip">MySQL</span><span class="chip">Python · scikit-learn</span><span class="chip">Streamlit</span></div>',
    unsafe_allow_html=True)

if data is None or hasil is None:
    st.error("File data tidak ditemukan. Jalankan notebook sampai bagian **Ekspor**, lalu salin isi folder "
             "`dashboard_data/` ke folder `data/` di samping `app.py`.")
    st.stop()

data = data.merge(hasil[["country_code", "year", "kategori_aktual"]], on=["country_code", "year"], how="left")

# =============================================================================
# Sidebar: filter
# =============================================================================
SS = st.session_state
t_min, t_max = int(data["year"].min()), int(data["year"].max())
income_ada = [x for x in URUT_INCOME if x in data["income_level"].unique()] or sorted(data["income_level"].dropna().unique())
kawasan_ada = sorted(data["region"].dropna().unique())
DEFAULT = {"f_tahun": (t_min, t_max), "f_income": income_ada, "f_kawasan": kawasan_ada, "f_negara": [], "f_kategori": LABEL}
for k, v in DEFAULT.items():
    SS.setdefault(k, v)


def reset_filter():
    for k, v in DEFAULT.items():
        SS[k] = v


st.sidebar.markdown("## 🎛️ Filter")
st.sidebar.slider("Rentang tahun", t_min, t_max, key="f_tahun")
st.sidebar.multiselect("Kelompok pendapatan", income_ada, key="f_income")
st.sidebar.multiselect("Kawasan", kawasan_ada, key="f_kawasan")
negara_ada = sorted(data[data["income_level"].isin(SS.f_income) & data["region"].isin(SS.f_kawasan)]["country_name"].dropna().unique())
SS.f_negara = [x for x in SS.f_negara if x in negara_ada]
st.sidebar.multiselect("Negara (kosong = semua)", negara_ada, key="f_negara")
st.sidebar.multiselect("Kategori hasil serealia", LABEL, key="f_kategori")
st.sidebar.button("↺ Reset filter", on_click=reset_filter)
st.sidebar.caption("Filter berlaku untuk **kartu angka, EDA tabel, EDA gabungan, dan tabel data**. Assessing, cleaning, assessing ulang, "
                   "dan angka resmi model menampilkan hasil lengkap dari notebook (tidak terfilter).")
if meta.get("dibuat"):
    st.sidebar.caption(f"Data notebook dibuat: {meta['dibuat']}")


def terapkan(df):
    m = df["year"].between(*SS.f_tahun) & df["income_level"].isin(SS.f_income) & df["region"].isin(SS.f_kawasan)
    if SS.f_negara:
        m &= df["country_name"].isin(SS.f_negara)
    if set(SS.f_kategori) != set(LABEL):
        m &= df["kategori_aktual"].isin(SS.f_kategori)
    return df[m]


d = terapkan(data)
h = terapkan(hasil.assign(kategori_aktual=hasil["kategori_aktual"]))

# =============================================================================
# Kartu angka (selalu tampil di atas)
# =============================================================================
if d.empty:
    peringatan("**Tidak ada data** untuk kombinasi filter ini. Longgarkan filter di sidebar atau tekan **Reset filter**.")
    st.stop()

c = st.columns(5)
with c[0]:
    kartu("Negara", fmt(d["country_code"].nunique()), f"dari {data['country_code'].nunique()} negara", TEAL, "🌍", MINT)
with c[1]:
    kartu("Hasil serealia", f"{fmt(d['cereal_yield_kg_ha'].mean())}<small> kg/ha</small>",
          delta(d["cereal_yield_kg_ha"].mean(), data["cereal_yield_kg_ha"].mean()), SAGE, "🌾")
with c[2]:
    kartu("Pupuk", f"{fmt(d['fertilizer_kg_ha'].mean())}<small> kg/ha</small>",
          delta(d["fertilizer_kg_ha"].mean(), data["fertilizer_kg_ha"].mean()), SAND, "🧪", KREM)
with c[3]:
    kartu("GDP per kapita (median)", f"${fmt(d['gdp_per_capita_usd'].median())}",
          delta(d["gdp_per_capita_usd"].median(), data["gdp_per_capita_usd"].median()), PEACH, "💵", PERSIK)
with c[4]:
    kartu("Periode", f"{SS.f_tahun[0]}–{SS.f_tahun[1]}", f"{len(d):,} baris data", SKY, "📅", LANGIT)
st.write("")

tabs = st.tabs(["🏠 Beranda", "📘 Penjelasan", "🗂️ Per tabel", "🔗 Gabungan & EDA (Q1–Q3)", "🤖 Model (Q4)", "📁 Data & Kesimpulan"])


# =============================================================================
# 0. BERANDA
# =============================================================================
with tabs[0]:
    st.markdown("### Latar belakang")
    panel("Serealia (padi, jagung, gandum) adalah sumber kalori utama dunia, sehingga kemampuan sebuah negara menghasilkan serealia dari tiap hektare lahan "
          "(**produktivitas**) sangat memengaruhi ketahanan pangannya. Luas lahan saja tidak cukup menjelaskan: negara berlahan sempit bisa lebih produktif "
          "daripada negara berlahan luas. Perbedaan ini diduga berkaitan dengan input produksi (misalnya pupuk), struktur ekonomi, dan kondisi iklim.\n\n"
          "Untuk Indonesia, yang pangan pokoknya beras dan menghadapi tekanan lahan serta perubahan iklim, memahami faktor-faktor ini membantu menilai posisi "
          "kita dibanding negara lain.")
    temuan("**Catatan metodologi:** data ini observasional, jadi seluruh temuan adalah **keterkaitan (asosiasi)**, bukan bukti sebab-akibat.")

    st.markdown("### Empat pertanyaan")
    q = st.columns(4)
    qs = [("Q1 · SEDERHANA", "Negara dan kawasan mana yang hasil serealianya tertinggi?", "Tab EDA", MINT),
          ("Q2 · ANALISIS", "Apakah pemakaian pupuk berkaitan dengan hasil serealia?", "Tab EDA", KREM),
          ("Q3 · ANALISIS LANJUTAN", "Apakah ekonomi dan iklim berkaitan dengan hasil serealia, dan di mana posisi Indonesia?", "Tab EDA", PERSIK),
          ("Q4 · MODEL AI", "Dapatkah karakteristik negara mengklasifikasikan hasil serealia: Rendah / Sedang / Tinggi?", "Tab Model", LANGIT)]
    for kol, (a, b, j, bg) in zip(q, qs):
        with kol:
            st.markdown(f'<div class="qkartu" style="background:{bg}"><div class="q">{a}</div><div class="t">{b}</div><div class="j">→ {j}</div></div>',
                        unsafe_allow_html=True)

    st.markdown("### Alur sistem")
    st.markdown(
        '<div class="alur">'
        f'<div class="langkah" style="background:{MINT}"><b>🌐 Sumber terbuka</b><span>World Bank API · NASA POWER</span></div><div class="panah">➜</div>'
        f'<div class="langkah" style="background:{KREM}"><b>⚙️ Apache Airflow</b><span>extract → validate → load (upsert)</span></div><div class="panah">➜</div>'
        f'<div class="langkah" style="background:{PERSIK}"><b>🗄️ MySQL</b><span>1 tabel dimensi + 3 tabel fakta, unique key &amp; FK</span></div><div class="panah">➜</div>'
        f'<div class="langkah" style="background:{LANGIT}"><b>📓 Notebook</b><span>assessing → cleaning → EDA → model</span></div><div class="panah">➜</div>'
        f'<div class="langkah" style="background:{MINT}"><b>📊 Dashboard</b><span>filter &amp; visualisasi interaktif</span></div>'
        '</div>', unsafe_allow_html=True)

    st.markdown("### Struktur database")
    mengapa("Satu tabel dimensi (`dim_country`) dirujuk tiga tabel fakta lewat *foreign key* `country_id`. Setiap tabel fakta punya *unique key* "
            "`(country_id, year)` sehingga tidak ada baris ganda, dan ketiganya digabungkan lewat negara + tahun.")
    st.graphviz_chart(r'''digraph G {
        rankdir=LR; bgcolor="transparent";
        node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, color="#2A9D8F", fillcolor="#E8F5F1", fontcolor="#2B3A42"];
        edge [color="#6B7C85", fontname="Helvetica", fontsize=10, fontcolor="#6B7C85"];
        dim_country [label="dim_country\l PK country_id\l UQ country_code\l country_name, region\l income_level, capital_lat/lon\l", fillcolor="#FDF3D7", color="#E9C46A"];
        fact_agriculture [label="fact_agriculture  (data utama)\l PK agriculture_id\l FK country_id\l UQ (country_id, year)\l hasil serealia, pupuk, lahan arable,\l nilai tambah & tenaga kerja agri\l"];
        fact_economic [label="fact_economic\l PK economic_id\l FK country_id\l UQ (country_id, year)\l GDP per kapita, populasi\l", fillcolor="#FDE8D8", color="#F4A261"];
        fact_climate [label="fact_climate\l PK climate_id\l FK country_id\l UQ (country_id, year)\l suhu, curah hujan\l", fillcolor="#E3F2F9", color="#6BB8D9"];
        dim_country -> fact_agriculture [label="1 : N"];
        dim_country -> fact_economic [label="1 : N"];
        dim_country -> fact_climate [label="1 : N"];
    }''')


# =============================================================================
# 1b. PENJELASAN
# =============================================================================
with tabs[1]:
    st.markdown("### Judul penelitian")
    panel("**Analisis Keterkaitan Pupuk, Ekonomi, dan Iklim terhadap Produktivitas Serealia Antarnegara**\n"
          "Sistem data end-to-end dengan Apache Airflow, MySQL, notebook analisis, model klasifikasi, dan dashboard.")

    st.markdown("### Latar belakang")
    panel("**1. Pangan itu penting.** Serealia (padi, jagung, gandum) adalah sumber kalori utama dunia, sehingga kemampuan sebuah negara menghasilkan serealia "
          "sangat memengaruhi ketahanan pangannya.\n"
          "**2. Ukurannya produktivitas, bukan luas lahan.** Yang dibandingkan adalah berapa kg serealia dihasilkan dari setiap hektare. "
          "Negara berlahan sempit bisa lebih produktif daripada negara berlahan luas.\n"
          "**3. Produktivitas sangat berbeda antarnegara.** Perbedaan ini diduga berkaitan dengan input produksi (misalnya pupuk), kondisi ekonomi, dan iklim.\n"
          "**4. Relevan untuk Indonesia.** Pangan pokok kita beras, dan kita menghadapi tekanan lahan serta perubahan iklim, sehingga penting tahu posisi kita "
          "dan faktor apa yang berkaitan dengan produktivitas.\n"
          "**5. Masalah dari sisi data.** Data pertanian, ekonomi, dan iklim tersebar di sumber berbeda. Perlu sistem otomatis untuk mengumpulkan, merapikan, "
          "dan menganalisisnya.")

    st.markdown("### Tujuan")
    panel("**Tujuan analisis**\n"
          "1. Mengetahui negara dan kawasan dengan produktivitas serealia tertinggi, serta posisi Indonesia.\n"
          "2. Mengetahui apakah pupuk, kondisi ekonomi, dan iklim berkaitan dengan produktivitas serealia.\n"
          "3. Menguji apakah karakteristik sebuah negara cukup untuk mengklasifikasikan tingkat produktivitasnya (Rendah, Sedang, Tinggi).\n\n"
          "**Tujuan teknis:** membangun sistem data end-to-end (API → Airflow → MySQL → notebook → dashboard) dengan penilaian dan pembersihan data yang benar.")

    st.markdown("### Alur penelitian")
    langkah(1, "Ambil data dari API terbuka", "Airflow mengambil indikator pertanian dan ekonomi dari World Bank, dan suhu serta curah hujan dari NASA POWER.")
    langkah(2, "Simpan ke MySQL", "Data masuk ke 4 tabel (1 dimensi + 3 fakta) dengan foreign key dan unique key. Penyimpanan memakai upsert sehingga aman diulang.")
    langkah(3, "Muat ke notebook", "Notebook membaca keempat tabel dari MySQL.")
    langkah(4, "Kerjakan tiap tabel satu per satu", "Untuk dim_country, fact_agriculture, fact_economic, lalu fact_climate: **assessing → cleaning → assessing ulang → EDA tabel**. "
            "Tiap tabel punya masalah dan sebaran berbeda, jadi dipahami dulu sebelum digabung.")
    langkah(5, "Gabungkan tabel", "Keempat tabel bersih digabung lewat country_id + year. Diperiksa bahwa jumlah baris tidak bertambah (tidak ada baris ganda).")
    langkah(6, "EDA gabungan dan analisis (Q1–Q3)", "Peringkat negara, hubungan pupuk dengan hasil, serta hubungan ekonomi dan iklim dengan hasil.")
    langkah(7, "Model (Q4)", "Mengklasifikasikan tingkat hasil serealia (Rendah/Sedang/Tinggi) dan menilai modelnya dengan jujur.")
    langkah(8, "Dashboard dan presentasi", "Hasil diekspor dan ditampilkan di dashboard interaktif dengan filter, lalu dipresentasikan.")

    st.markdown("### Memahami data: tabel dimensi dan tabel fakta")
    st.markdown("""
| Jenis | Tabel | Isinya | Satu baris mewakili |
|---|---|---|---|
| **Tabel dimensi** (keterangan) | `dim_country` | Identitas negara yang tidak berubah tiap tahun | 1 negara |
| **Tabel fakta** (angka hasil pengukuran) | `fact_agriculture`, `fact_economic`, `fact_climate` | Angka yang berubah tiap tahun | 1 negara pada 1 tahun |
""")
    panel("**Fakta** = angka yang diukur, misalnya *hasil serealia Indonesia tahun 2020* atau *GDP per kapita Indonesia tahun 2020*.\n"
          "**Dimensi** = keterangan tentang \"siapa\" yang diukur, misalnya Indonesia itu negara apa, di kawasan mana, dan masuk kelompok pendapatan apa.")
    if "country_id" in data.columns:
        ex = data[data["country_code"] == "IDN"]
        if ex.empty:
            ex = data[data["country_code"] == data["country_code"].iloc[0]]
        ex = ex.dropna(subset=["cereal_yield_kg_ha"]).sort_values("year")
        cid, kode, nm = int(ex["country_id"].iloc[0]), ex["country_code"].iloc[0], ex["country_name"].iloc[0]
        mengapa(f"**Contoh nyata dari data Anda: {nm}.** Perhatikan `country_id` = {cid} muncul di semua tabel. Itulah foreign key-nya.")
        st.markdown("`dim_country` (1 baris = 1 negara)")
        tabel(pd.DataFrame([{"country_id": cid, "country_code": kode, "country_name": nm, "region": ex["region"].iloc[0],
                             "income_level": ex["income_level"].iloc[0]}]))
        ek = ex.tail(3)
        st.markdown("`fact_agriculture` (1 baris = 1 negara pada 1 tahun)")
        tabel(ek[["country_id", "year", "cereal_yield_kg_ha", "fertilizer_kg_ha"]].round(1))
        st.markdown("`fact_economic`")
        tabel(ek[["country_id", "year", "gdp_per_capita_usd", "population"]].round(0))
        st.markdown("`fact_climate`")
        tabel(ek[["country_id", "year", "avg_temp_c", "total_precip_mm"]].round(1))

    st.markdown("**Mengapa dipecah menjadi tiga tabel fakta?**")
    panel("1. Isinya berbeda topik dan sumber: pertanian dan ekonomi dari World Bank, iklim dari NASA POWER.\n"
          "2. Keterangan negara (nama, kawasan, kelompok pendapatan) cukup disimpan **satu kali** di `dim_country`, tidak diulang di ribuan baris.\n"
          "3. Tiap tabel bisa diperbarui sendiri; kalau pengambilan iklim gagal, data pertanian tidak ikut rusak.\n"
          "4. Ketiganya berbentuk sama (negara + tahun), sehingga mudah digabung kembali saat analisis.")
    st.markdown("**Bagaimana foreign key bekerja?**")
    panel("Tiap tabel fakta tidak menulis nama negara, hanya nomor negara (`country_id`) yang menunjuk ke satu baris di `dim_country`. "
          "Seperti nomor induk mahasiswa pada lembar absen: nama dan jurusan ada di daftar mahasiswa, lembar absen cukup menulis nomornya.\n\n"
          "Saat memuat data, DAG Airflow:\n"
          "1. memuat `dim_country` lebih dulu, lalu MySQL memberi tiap negara sebuah `country_id`;\n"
          "2. untuk setiap baris dari World Bank (yang membawa kode negara seperti `IDN`), DAG mencari `country_id` milik kode itu;\n"
          "3. menyimpan `country_id` tersebut di tabel fakta. MySQL menolak baris yang `country_id`-nya tidak ada di `dim_country`.\n\n"
          "**Unique key** `(country_id, year)` menjamin satu negara hanya punya satu baris per tahun di tiap tabel fakta.")

    st.markdown("### Memahami target dan fitur")
    panel("Model belajar dari pasangan **input → jawaban**.\n"
          "• **Target (y)** = jawaban yang ingin ditebak: tingkat hasil serealia suatu negara pada suatu tahun, yaitu **Rendah, Sedang, atau Tinggi**. "
          "Label ini dibuat dari angka hasil serealia (kg/ha) dengan memotongnya menjadi tiga kelompok sama besar (*tertil*).\n"
          "• **Fitur (X)** = keterangan yang diberikan ke model untuk menebak: pupuk, lahan, ekonomi, iklim, tahun, kawasan, dan kelompok pendapatan.\n"
          "• **Hasil serealia tidak boleh menjadi fitur**, karena itu adalah jawabannya. Memasukkannya sama dengan memberi contekan.\n"
          "• Satu **baris data** = satu negara pada satu tahun.")
    fitur_tab = pd.DataFrame([
        ("fertilizer_kg_ha", "Pemakaian pupuk (kg per hektare lahan arable)", "numerik", "fact_agriculture"),
        ("arable_land_pct", "Lahan arable (% dari luas lahan)", "numerik", "fact_agriculture"),
        ("agri_value_added_pct", "Nilai tambah pertanian (% dari PDB)", "numerik", "fact_agriculture"),
        ("agri_employment_pct", "Tenaga kerja di pertanian (% dari total)", "numerik", "fact_agriculture"),
        ("log_gdp", "GDP per kapita (skala log10)", "numerik", "fact_economic"),
        ("log_pop", "Populasi (skala log10)", "numerik", "fact_economic"),
        ("avg_temp_c", "Suhu rata-rata tahunan (°C)", "numerik", "fact_climate"),
        ("total_precip_mm", "Curah hujan tahunan (mm)", "numerik", "fact_climate"),
        ("year", "Tahun pengamatan", "numerik", "-"),
        ("region", "Kawasan negara", "kategori", "dim_country"),
        ("income_level", "Kelompok pendapatan World Bank", "kategori", "dim_country"),
    ], columns=["fitur (X)", "arti", "jenis", "asal tabel"])
    tabel(fitur_tab)

    pm_ = meta.get("model", {})
    if pm_:
        c = st.columns(3)
        with c[0]: kartu("Rendah", f"≤ {fmt(pm_['ambang_rendah_maks'])}", "kg/ha", CORAL, "🔻")
        with c[1]: kartu("Sedang", f"≤ {fmt(pm_['ambang_sedang_maks'])}", "kg/ha", SAND, "➖", KREM)
        with c[2]: kartu("Tinggi", f"> {fmt(pm_['ambang_sedang_maks'])}", "kg/ha", TEAL, "🔺", MINT)
        st.write("")
    ct = data[data["country_code"] == "IDN"].dropna(subset=["cereal_yield_kg_ha"]).sort_values("year")
    if not ct.empty:
        rc = ct.iloc[-1]
        fcols = ["fertilizer_kg_ha", "arable_land_pct", "agri_value_added_pct", "agri_employment_pct", "log_gdp", "log_pop",
                 "avg_temp_c", "total_precip_mm", "year", "region", "income_level"]
        fcols = [x for x in fcols if x in ct.columns]
        mengapa(f"**Contoh satu baris: {rc['country_name']}, tahun {int(rc['year'])}.** Ini yang diberikan ke model (X), lalu jawabannya (y).")
        tabel(pd.DataFrame({"fitur (X)": fcols, "nilai": [str(round(rc[x], 2)) if isinstance(rc[x], (int, float, np.floating, np.integer)) else str(rc[x]) for x in fcols]}))
        hr = hasil[(hasil["country_code"] == rc["country_code"]) & (hasil["year"] == rc["year"])]
        ket = f"Hasil serealia sebenarnya **{fmt(rc['cereal_yield_kg_ha'])} kg/ha**"
        if not hr.empty:
            ket += (f" → target (y) = **{hr.iloc[0]['kategori_aktual']}**. Tebakan model: **{hr.iloc[0]['prediksi_kategori']}** "
                    f"(baris ini termasuk data **{hr.iloc[0]['split']}**).")
        temuan(ket)

    st.markdown("### Pengolahan data sebelum masuk model")
    n_total, n_kosong = len(data), int(data["cereal_yield_kg_ha"].isna().sum())
    langkah(1, "Mulai dari data bersih", f"{n_total:,} baris (negara × tahun).")
    langkah(2, "Buang baris tanpa target", f"{n_kosong:,} baris dibuang karena hasil serealia kosong, sehingga tidak bisa diberi label." +
            (f" Sisa {pm_['n_latih'] + pm_['n_uji']:,} baris." if pm_ else ""))
    langkah(3, "Bagi data per negara", "Satu negara hanya masuk data latih **atau** data uji, tidak keduanya." +
            (f" Latih: {pm_['n_latih']:,} baris ({pm_['negara_latih']} negara); uji: {pm_['n_uji']:,} baris ({pm_['negara_uji']} negara)." if pm_ else ""))
    langkah(4, "Buat label dari data latih", "Ambang tertil dihitung hanya dari data latih, lalu dipakai untuk memberi label Rendah/Sedang/Tinggi pada data latih dan data uji.")
    langkah(5, "Siapkan fitur di dalam pipeline", "Nilai kosong pada fitur numerik diisi median, dan pada fitur kategori diisi nilai terbanyak, keduanya dipelajari **hanya dari data latih**. "
            "Fitur kategori (kawasan, kelompok pendapatan) diubah menjadi kolom 0/1 (one-hot).")
    langkah(6, "Latih empat model", "Baseline, Decision Tree, Random Forest, dan Gradient Boosting dilatih pada data latih.")
    langkah(7, "Nilai pada data uji", "Akurasi, presisi, recall, dan F1 dihitung pada negara yang belum pernah dilihat model. Validasi silang per negara dipakai untuk memeriksa kestabilan.")


# =============================================================================
# 2. PER TABEL: assessing -> cleaning -> assessing ulang -> EDA tabel
# =============================================================================
ring, kol, des = baca_csv("ringkasan_assessing.csv"), baca_csv("kolom_assessing.csv"), baca_csv("describe_assessing.csv")
log, pk, dimc = baca_csv("log_cleaning.csv"), baca_csv("pola_kosong.csv"), baca_csv("dim_country_bersih.csv")
ADA_ASSESS = ring is not None and kol is not None and des is not None and log is not None
LAMBAT = ["arable_land_pct", "agri_value_added_pct", "agri_employment_pct"]
ID_KOLOM = ["agriculture_id", "economic_id", "climate_id", "loaded_at", "country_id", "year"]


def belum_ada():
    peringatan("Bagian ini membutuhkan file ekspor terbaru dari notebook (`ringkasan_assessing.csv`, `kolom_assessing.csv`, `describe_assessing.csv`, "
               "`log_cleaning.csv`, `pola_kosong.csv`, `dim_country_bersih.csv`, `meta_analisis.json`). Jalankan ulang sel **Ekspor** di notebook "
               "dan salin isi `dashboard_data/` ke folder `data/`.")


KETERANGAN = {
    "dim_country": "**Tabel dimensi (keterangan negara).** Satu baris = satu negara. Dikerjakan lebih dulu karena dirujuk tiga tabel fakta lewat foreign key.",
    "fact_agriculture": "**Tabel fakta, data utama.** Satu baris = satu negara pada satu tahun. Berisi hasil serealia, pupuk, lahan arable, nilai tambah dan tenaga kerja pertanian (World Bank).",
    "fact_economic": "**Tabel fakta, ekonomi.** Satu baris = satu negara pada satu tahun. Berisi GDP per kapita dan populasi (World Bank).",
    "fact_climate": "**Tabel fakta, data pendukung.** Satu baris = satu negara pada satu tahun. Berisi suhu dan curah hujan tahunan di koordinat ibu kota (NASA POWER).",
}
KEPUTUSAN = {
    "dim_country": """
| Masalah | Keputusan | Alasan |
|---|---|---|
| Kolom teknis `loaded_at` | Dibuang | Tidak dipakai dalam analisis |
| Spasi berlebih dan huruf pada teks | Dirapikan (`strip`, kode negara huruf besar) | Mencegah gagal gabung karena beda penulisan |
| Duplikat `country_code` | Dihapus | Satu negara satu baris |
| Koordinat bertipe DECIMAL dari MySQL | Diubah menjadi angka | Agar bisa dihitung dan digambar |
""",
    "fact_agriculture": """
| Masalah | Keputusan | Alasan |
|---|---|---|
| Kolom teknis (`agriculture_id`, `loaded_at`) | Dibuang | Tidak dipakai dalam analisis |
| Duplikat pada (negara, tahun) | Dihapus, simpan yang terakhir | Satu negara-tahun hanya satu baris |
| Nilai di luar aturan validitas | Diubah menjadi kosong (NaN) | Baris masih punya indikator lain yang valid |
| Baris yang seluruh indikatornya kosong | Dihapus | Tidak membawa informasi |
| Celah pendek (≤ 2 tahun) pada lahan arable, nilai tambah, tenaga kerja | Interpolasi linear dalam satu negara | Indikator ini berubah bertahap |
| Kosong pada hasil serealia dan pupuk | **Tidak** diisi | Variabel inti; mengisinya berarti mengarang data |
| Outlier hasil serealia | Ditandai (`outlier_yield`), **tidak** dihapus | Hasil sangat tinggi mungkin memang nyata |
""",
    "fact_economic": """
| Masalah | Keputusan | Alasan |
|---|---|---|
| Kolom teknis (`economic_id`, `loaded_at`) | Dibuang | Tidak dipakai dalam analisis |
| Duplikat pada (negara, tahun) | Dihapus | Satu negara-tahun hanya satu baris |
| GDP atau populasi ≤ 0 | Diubah menjadi kosong | Tidak masuk akal |
| Baris yang seluruh indikatornya kosong | Dihapus | Tidak membawa informasi |
| Kosong pada GDP | **Tidak** diisi | Mengisi berarti mengarang data |
| Skala log GDP dan populasi | Dilakukan **setelah penggabungan** | Sebaran sangat miring; transformasi adalah fitur turunan |
""",
    "fact_climate": """
| Masalah | Keputusan | Alasan |
|---|---|---|
| Kolom teknis (`climate_id`, `loaded_at`) | Dibuang | Tidak dipakai dalam analisis |
| Duplikat pada (negara, tahun) | Dihapus | Satu negara-tahun hanya satu baris |
| Suhu di luar −60..60 °C, curah hujan negatif, bulan valid di luar 0..12 | Diubah menjadi kosong | Tidak masuk akal |
| Baris yang seluruh indikatornya kosong | Dihapus | Tidak membawa informasi |
| Kosong pada suhu atau curah hujan | **Tidak** diisi | Mengisi berarti mengarang data |
""",
}


def hist(df_, kolom, judul, label, warna, key, nbins=40):
    f = px.histogram(df_.dropna(subset=[kolom]), x=kolom, nbins=nbins, color_discrete_sequence=[warna], labels={kolom: label}, title=judul)
    f.update_layout(yaxis_title="jumlah baris", bargap=0.04)
    grafik(f, key, 400)


def garis(x, ys, judul, ytitle, key, tinggi=400):
    f = go.Figure()
    for nama, y, warna in ys:
        f.add_trace(go.Scatter(x=x, y=y, name=nama, mode="lines+markers", line=dict(color=warna, width=3)))
    f.update_layout(title=judul, xaxis_title="Tahun", yaxis_title=ytitle)
    grafik(f, key, tinggi)


with tabs[2]:
    st.markdown("### Per tabel: assessing → cleaning → assessing ulang → EDA")
    mengapa("Setiap tabel dikerjakan **sendiri-sendiri** dengan urutan yang sama, baru kemudian digabung (tab berikutnya). Tiap tabel punya masalah dan sebaran berbeda, "
            "jadi harus dipahami satu per satu lebih dulu. Bagian A–C menampilkan hasil notebook apa adanya; bagian D mengikuti filter di sidebar.")
    pilih = st.radio("Pilih tabel", TABEL, horizontal=True, key="pt_tabel")
    panel(KETERANGAN[pilih])
    if not ADA_ASSESS or not meta:
        belum_ada()
    else:
        sb_ = ring[(ring["tabel"] == pilih) & (ring["fase"] == "sebelum")].iloc[0]
        ss_ = ring[(ring["tabel"] == pilih) & (ring["fase"] == "sesudah")].iloc[0]

        # ------------------------------------------------------------------ A. ASSESSING
        st.markdown("## A. Assessing (data mentah)")
        mengapa("Memeriksa ukuran dan tipe (`info`), statistik (`describe`), nilai kosong, duplikat, dan nilai yang tidak masuk akal.")
        c = st.columns(4)
        with c[0]: kartu("Baris", fmt(sb_["baris"]), "jumlah record", TEAL, "📄", MINT)
        with c[1]: kartu("Nilai kosong", fmt(sb_["total_null"]), "total sel NULL", PEACH, "🕳️", PERSIK)
        with c[2]: kartu("Duplikat", fmt(sb_["duplikat_baris"]), f"pada kunci: {fmt(sb_['duplikat_kunci'])}", SAND, "👯", KREM)
        with c[3]: kartu("Tidak valid", fmt(sb_["nilai_tidak_valid"]), "di luar aturan validitas", CORAL, "⚠️")
        st.write("")
        k_sb = kol[(kol["tabel"] == pilih) & (kol["fase"] == "sebelum")].copy()
        st.markdown("**`info()`: kolom, tipe, dan kelengkapan**")
        tabel(k_sb[["kolom", "tipe", "non_null", "jumlah_null", "persen_null"]].rename(
            columns={"non_null": "terisi", "jumlah_null": "kosong", "persen_null": "% kosong"}),
            column_config={"% kosong": st.column_config.ProgressColumn("% kosong", min_value=0, max_value=100, format="%.1f%%")})
        st.markdown("**`describe()`: statistik deskriptif kolom numerik**")
        tabel(des[(des["tabel"] == pilih) & (des["fase"] == "sebelum")].drop(columns=["tabel", "fase"]).round(2))
        nl = k_sb[k_sb["persen_null"] > 0].sort_values("persen_null")
        if not nl.empty:
            f = px.bar(nl, x="persen_null", y="kolom", orientation="h", color_discrete_sequence=[PEACH],
                       labels={"persen_null": "% kosong", "kolom": ""}, title="Nilai kosong per kolom (%)")
            grafik(f, f"pt_null_{pilih}", 130 + 36 * len(nl))

        # peta nilai kosong (negara x tahun)
        if pilih == "dim_country":
            mengapa("Tabel dimensi tidak punya dimensi tahun, sehingga peta nilai kosong (negara × tahun) tidak berlaku.")
        elif pk is None:
            peringatan("Peta nilai kosong membutuhkan `pola_kosong.csv` dari notebook terbaru.")
        else:
            kn = pk[pk["tabel"] == pilih].groupby("kolom")["kosong"].sum().sort_values(ascending=False)
            kn = kn[kn > 0]
            st.markdown("**Pola nilai kosong (negara × tahun)**")
            mengapa("Total kosong belum cukup. Peta ini menunjukkan *di mana* kosongnya: acak, menumpuk pada tahun tertentu, atau seluruh negara. Merah = kosong.")
            if kn.empty:
                st.info("Tidak ada nilai kosong pada tabel ini, jadi tidak ada pola yang perlu dipetakan.")
            else:
                kp = st.selectbox("Kolom untuk peta nilai kosong", list(kn.index), key=f"pt_kolom_{pilih}")
                m = pk[(pk["tabel"] == pilih) & (pk["kolom"] == kp)].pivot_table(index="country_name", columns="year", values="kosong", aggfunc="max")
                f = px.imshow(m, color_continuous_scale=[[0, MINT], [1, CORAL]], zmin=0, zmax=1, aspect="auto",
                              labels=dict(x="Tahun", y="", color="kosong"), title=f"Pola nilai kosong: {kp}")
                f.update_layout(coloraxis_showscale=False)
                grafik(f, f"pt_peta_{pilih}", 170 + 20 * len(m))
                pt = m.mean(axis=0) * 100
                garis(pt.index, [("% negara kosong", pt.values, CORAL)], f"Persentase kosong per tahun: {kp}", "% kosong", f"pt_pertahun_{pilih}")
                penuh = m.index[(m == 1).all(axis=1)].tolist()
                th, rata = int(pt.idxmax()), pt.mean()
                menumpuk = pt.max() >= max(20, 2 * rata)
                tk = (f"**Temuan assessing.** Kolom `{kp}` paling kosong pada tahun **{th}** ({pt.max():.0f}% negara; rata-rata semua tahun {rata:.0f}%), " +
                      ("jadi kosongnya **menumpuk pada tahun tertentu**, bukan acak. " if menumpuk
                       else "dan tidak jauh di atas tahun lain, jadi kosongnya **relatif tersebar** antartahun. "))
                if penuh:
                    tk += f"Negara yang kosong di **semua tahun**: **{', '.join(penuh)}** (kosong struktural). "
                tk += "Nilai kosong berarti data tidak tersedia atau tidak dilaporkan, bukan nol, sehingga **tidak boleh** diisi 0."
                temuan(tk)

        # ------------------------------------------------------------------ B. CLEANING
        st.markdown("## B. Cleaning")
        mengapa("Setiap keputusan cleaning punya alasan. Prinsipnya: jangan mengarang data.")
        st.markdown(KEPUTUSAN[pilih])
        lg = log[log["tabel"] == pilih]
        if not lg.empty:
            lg = lg.iloc[0]
            c = st.columns(4)
            with c[0]: kartu("Duplikat dihapus", fmt(lg["duplikat_dihapus"]), "", SAND, "👯", KREM)
            with c[1]: kartu("Tidak valid → kosong", fmt(lg["nilai_tidak_valid_jadi_NaN"]), "", CORAL, "⚠️")
            with c[2]: kartu("Baris kosong dihapus", fmt(lg["baris_semua_kosong_dihapus"]), "", PEACH, "🗑️", PERSIK)
            with c[3]: kartu("Baris akhir", fmt(lg["baris_akhir"]), f"dari {fmt(lg['baris_awal'])} baris awal", TEAL, "✅", MINT)
            st.write("")
        if pilih == "fact_agriculture":
            ip = pd.Series(meta.get("interpolasi", {})).rename("terisi").rename_axis("indikator").reset_index()
            if not ip.empty:
                f = px.bar(ip, x="indikator", y="terisi", color_discrete_sequence=[SAGE], title="Nilai terisi lewat interpolasi (celah ≤ 2 tahun)",
                           labels={"terisi": "jumlah nilai", "indikator": ""})
                grafik(f, "pt_interp", 380)
            ot = meta.get("outlier", {})
            tn = pd.Series(ot.get("top_negara", {})).rename("baris").rename_axis("negara").reset_index()
            if not tn.empty:
                f = px.bar(tn.sort_values("baris"), x="baris", y="negara", orientation="h", color_discrete_sequence=[SAND],
                           title="Negara dengan baris outlier hasil serealia terbanyak", labels={"baris": "baris ditandai", "negara": ""})
                grafik(f, "pt_outlier", 380)
            temuan(f"**Temuan cleaning.** Batas outlier atas (aturan IQR) adalah **{fmt(ot.get('batas_atas'))} kg/ha**, dan **{fmt(ot.get('jumlah'))} baris** ditandai. "
                   "Baris itu tetap dipakai karena negara berproduktivitas tinggi (umumnya dengan irigasi dan input intensif) adalah fenomena nyata, bukan kesalahan data.")
        elif not lg.empty:
            temuan(f"**Temuan cleaning.** Dari {fmt(lg['baris_awal'])} baris, {fmt(lg['baris_akhir'])} dipertahankan; {fmt(lg['duplikat_dihapus'])} duplikat dihapus dan "
                   f"{fmt(lg['nilai_tidak_valid_jadi_NaN'])} nilai tidak valid diubah menjadi kosong. Nilai kosong yang tersisa sengaja tidak diisi.")

        # ------------------------------------------------------------------ C. ASSESSING ULANG
        st.markdown("## C. Assessing ulang (data bersih)")
        mengapa("Pemeriksaan yang sama dijalankan pada data bersih untuk membuktikan kualitas data memang membaik.")
        c = st.columns(4)
        with c[0]: kartu("Baris", f"{fmt(sb_['baris'])} → {fmt(ss_['baris'])}", "sebelum → sesudah", TEAL, "📄", MINT)
        with c[1]: kartu("Nilai kosong", f"{fmt(sb_['total_null'])} → {fmt(ss_['total_null'])}", "sebelum → sesudah", PEACH, "🕳️", PERSIK)
        with c[2]: kartu("Duplikat kunci", f"{fmt(sb_['duplikat_kunci'])} → {fmt(ss_['duplikat_kunci'])}", "sebelum → sesudah", SAND, "👯", KREM)
        with c[3]: kartu("Tidak valid", f"{fmt(sb_['nilai_tidak_valid'])} → {fmt(ss_['nilai_tidak_valid'])}", "sebelum → sesudah", CORAL, "⚠️")
        st.write("")
        tabel(pd.DataFrame([sb_, ss_], index=["sebelum", "sesudah"]).drop(columns=["tabel", "fase"]).reset_index().rename(columns={"index": "fase"}))
        kk = kol[kol["tabel"] == pilih][["fase", "kolom", "persen_null"]]
        kk = kk[~kk["kolom"].isin(ID_KOLOM)]
        f = px.bar(kk, x="kolom", y="persen_null", color="fase", barmode="group", color_discrete_map={"sebelum": PEACH, "sesudah": TEAL},
                   category_orders={"fase": ["sebelum", "sesudah"]}, labels={"persen_null": "% kosong", "kolom": "", "fase": "Fase"},
                   title=f"% nilai kosong per kolom: {pilih}")
        grafik(f, f"pt_banding_{pilih}", 400)
        temuan(f"**Temuan assessing ulang.** Nilai tidak valid: {fmt(sb_['nilai_tidak_valid'])} → {fmt(ss_['nilai_tidak_valid'])}; duplikat kunci: "
               f"{fmt(sb_['duplikat_kunci'])} → {fmt(ss_['duplikat_kunci'])}; baris: {fmt(sb_['baris'])} → {fmt(ss_['baris'])}; nilai kosong: "
               f"{fmt(sb_['total_null'])} → {fmt(ss_['total_null'])}. Nilai kosong sengaja **tidak** ditutup dengan angka karangan; yang berubah adalah kita tahu persis di mana kosongnya.")

        # ------------------------------------------------------------------ D. EDA TABEL
        st.markdown("## D. EDA tabel")
        mengapa("Mengenal sebaran tiap tabel **sebelum digabung**. Dihitung dari data bersih yang mengikuti filter di sidebar.")
        if pilih == "dim_country":
            dk = dimc[dimc["country_code"].isin(d["country_code"].unique())] if dimc is not None else d.drop_duplicates("country_code")
            reg = dk["region"].value_counts().sort_values().rename_axis("region").reset_index(name="jumlah")
            f = px.bar(reg, x="jumlah", y="region", orientation="h", color_discrete_sequence=[TEAL], title="Jumlah negara per kawasan",
                       labels={"jumlah": "jumlah negara", "region": ""})
            grafik(f, "pd_reg", 130 + 40 * len(reg))
            inc = dk["income_level"].value_counts().reindex(income_ada).fillna(0).rename_axis("income_level").reset_index(name="jumlah")
            f = px.bar(inc, x="income_level", y="jumlah", color="income_level", color_discrete_map=WARNA_INCOME,
                       title="Jumlah negara per kelompok pendapatan", labels={"income_level": "", "jumlah": "jumlah negara"})
            f.update_layout(showlegend=False)
            grafik(f, "pd_inc", 400)
            if dimc is not None and {"capital_lat", "capital_lon"} <= set(dimc.columns):
                f = px.scatter(dk.dropna(subset=["capital_lat", "capital_lon"]), x="capital_lon", y="capital_lat", color="region",
                               hover_name="country_name", color_discrete_sequence=SERI,
                               labels={"capital_lon": "bujur", "capital_lat": "lintang", "region": "Kawasan"},
                               title="Posisi ibu kota negara (titik pengambilan data iklim)")
                f.update_traces(marker=dict(size=11, line=dict(width=1, color="white")))
                grafik(f, "pd_peta", 480)
            temuan(f"**Temuan EDA tabel.** Pada filter ini ada **{len(dk)} negara** di **{dk['region'].nunique()} kawasan**; kawasan terbanyak: "
                   f"**{reg.iloc[-1]['region']}** ({int(reg.iloc[-1]['jumlah'])} negara). Karena iklim diambil di koordinat ibu kota, nilainya hanya mewakili iklim negara secara kasar.")

        elif pilih == "fact_agriculture":
            hist(d, "cereal_yield_kg_ha", "Sebaran hasil serealia", "kg per hektare", TEAL, "pa_hist_y")
            ff = d[d["fertilizer_kg_ha"] > 0].assign(log_pupuk=lambda x: np.log10(x["fertilizer_kg_ha"]))
            hist(ff, "log_pupuk", "Sebaran pemakaian pupuk (skala log10)", "log10 (kg pupuk per hektare)", SAND, "pa_hist_f")
            pj = d[LAMBAT].rename(columns={"arable_land_pct": "Lahan arable", "agri_value_added_pct": "Nilai tambah agri", "agri_employment_pct": "Tenaga kerja agri"}) \
                .melt(var_name="indikator", value_name="persen").dropna()
            f = px.box(pj, x="indikator", y="persen", color="indikator", color_discrete_sequence=[SAGE, PEACH, SKY],
                       labels={"indikator": "", "persen": "persen"}, title="Sebaran tiga indikator persentase")
            f.update_layout(showlegend=False)
            grafik(f, "pa_box", 420)
            tr_ = d.groupby("year")["cereal_yield_kg_ha"].agg(["mean", "median"]).dropna()
            if not tr_.empty:
                garis(tr_.index, [("rata-rata", tr_["mean"].values, TEAL), ("median", tr_["median"].values, CORAL)],
                      "Hasil serealia per tahun (seluruh negara terfilter)", "kg per hektare", "pa_tren")
            yv = d["cereal_yield_kg_ha"].dropna()
            if len(yv) > 3:
                arah = "miring ke kanan (sebagian kecil negara berhasil sangat tinggi)" if yv.skew() > .5 else "relatif simetris"
                tk = f"**Temuan EDA tabel.** Hasil serealia rata-rata {fmt(yv.mean())} kg/ha, median {fmt(yv.median())} kg/ha; sebarannya {arah}. "
                if len(tr_) > 1:
                    tk += f"Dari {int(tr_.index.min())} ke {int(tr_.index.max())}, rata-rata berubah {((tr_['mean'].iloc[-1] / tr_['mean'].iloc[0]) - 1) * 100:+.0f}%. "
                temuan(tk + "Pupuk sangat miring sehingga dipakai skala log pada analisis berikutnya.")

        elif pilih == "fact_economic":
            hist(d, "log_gdp", "Sebaran GDP per kapita (skala log10)", "log10 (US$ per kapita)", PEACH, "pe_hist_g")
            hist(d, "log_pop", "Sebaran populasi (skala log10)", "log10 (jumlah penduduk)", SAGE, "pe_hist_p")
            gm = d.groupby("year")["gdp_per_capita_usd"].median().dropna()
            if not gm.empty:
                garis(gm.index, [("median GDP per kapita", gm.values, PEACH)], "Median GDP per kapita per tahun", "US$ per kapita", "pe_tren")
            gv, pv = d["gdp_per_capita_usd"].dropna(), d["population"].dropna()
            if len(gv) and len(pv):
                temuan(f"**Temuan EDA tabel.** Median GDP per kapita {fmt(gv.median())} US$, rata-rata {fmt(gv.mean())} US$. "
                       + ("Rata-rata jauh di atas median: tanda sebaran miring ke kanan. " if gv.mean() > 1.3 * gv.median() else "")
                       + f"Populasi sangat timpang (dari {fmt(pv.min())} sampai {fmt(pv.max())} jiwa). Karena itu GDP dan populasi dipakai dalam skala log pada analisis dan model.")

        else:  # fact_climate
            hist(d, "avg_temp_c", "Sebaran suhu rata-rata tahunan", "°C", CORAL, "pc_hist_t")
            hist(d, "total_precip_mm", "Sebaran curah hujan tahunan", "mm per tahun", SKY, "pc_hist_p")
            cm_ = d.groupby(["country_code", "country_name"])[["avg_temp_c", "total_precip_mm"]].mean().reset_index().dropna()
            cm_["negara"] = np.where(cm_["country_code"] == "IDN", "Indonesia", "Negara lain")
            f = px.scatter(cm_, x="avg_temp_c", y="total_precip_mm", color="negara", hover_name="country_name",
                           color_discrete_map={"Indonesia": CORAL, "Negara lain": TEAL},
                           labels={"avg_temp_c": "Suhu rata-rata (°C)", "total_precip_mm": "Curah hujan (mm/tahun)", "negara": ""},
                           title="Suhu vs curah hujan (rata-rata per negara)")
            f.update_traces(marker=dict(size=12, line=dict(width=1, color="white")))
            grafik(f, "pc_scatter", 460)
            tm = d.groupby("year")["avg_temp_c"].mean().dropna()
            if not tm.empty:
                garis(tm.index, [("suhu rata-rata", tm.values, CORAL)], "Suhu rata-rata ibu kota per tahun", "°C", "pc_tren")
            tv, pr = d["avg_temp_c"].dropna(), d["total_precip_mm"].dropna()
            if len(tv) and len(pr):
                temuan(f"**Temuan EDA tabel.** Suhu rata-rata ibu kota {tv.mean():.1f} °C (rentang {tv.min():.1f} sampai {tv.max():.1f}), curah hujan rata-rata {fmt(pr.mean())} mm per tahun. "
                       "Garis suhu adalah rata-rata dari ibu kota negara dalam scope, **bukan** suhu global, sehingga jangan ditafsirkan sebagai bukti pemanasan global.")


# =============================================================================
# 4. EDA
# =============================================================================
with tabs[3]:
    st.markdown("### 7. Menggabungkan tabel")
    mengapa("Setelah keempat tabel bersih, barulah digabung. Tabel pertanian jadi dasar, lalu tabel ekonomi dan iklim ditempelkan lewat **`country_id` + `year`**, "
            "dan keterangan negara lewat `country_id` (foreign key bekerja). Jumlah baris **tidak bertambah** setelah digabung, bukti tidak ada baris ganda.")
    cg = st.columns(4)
    with cg[0]: kartu("Baris gabungan", fmt(len(data)), "negara × tahun", TEAL, "🔗", MINT)
    with cg[1]: kartu("Kolom", fmt(data.shape[1]), "setelah digabung", SAGE, "🧱")
    with cg[2]: kartu("Negara", fmt(data["country_code"].nunique()), "dalam scope", SAND, "🌍", KREM)
    with cg[3]: kartu("Rentang tahun", f"{t_min}–{t_max}", "", SKY, "📅", LANGIT)
    st.write("")
    kg = pd.Series(meta.get("kosong_gabungan", {})).rename("persen").rename_axis("kolom").reset_index()
    if not kg.empty:
        kg["kolom"] = kg["kolom"].map(lambda x: NAMA.get(x, x.replace("_", " ")))
        f = px.bar(kg.sort_values("persen"), x="persen", y="kolom", orientation="h", color_discrete_sequence=[SKY],
                   labels={"persen": "% kosong", "kolom": ""}, title="Persentase nilai kosong pada data gabungan")
        grafik(f, "gb_kosong", 440)
        temuan(f"**Temuan penggabungan.** Data gabungan berisi {fmt(len(data))} baris. Kolom dengan kosong terbanyak: **{kg.sort_values('persen').iloc[-1]['kolom']}** "
               f"({kg['persen'].max():.1f}%). Kekosongan ini diperlakukan per analisis: dibuang pada pasangan variabel yang dipakai, atau diimputasi di dalam pipeline model supaya tidak bocor.")
    st.markdown("### 8. EDA data gabungan (menjawab Q1–Q3)")
    mengapa("Seluruh grafik di bagian ini mengikuti filter di sidebar.")

    # ---------------- Q1
    st.markdown("### Q1. Negara dan kawasan mana yang hasil serealianya tertinggi?")
    mengapa("**Bar chart** dipilih karena tujuannya membandingkan peringkat antarkategori. Nilai = rata-rata pada rentang tahun yang dipilih.")
    n_top = st.slider("Jumlah negara yang ditampilkan", 5, 20, 10, key="q1_n")
    q1 = (d.groupby(["country_code", "country_name", "region"], as_index=False)["cereal_yield_kg_ha"].mean()
            .dropna().sort_values("cereal_yield_kg_ha", ascending=False).reset_index(drop=True))
    q1["peringkat"] = q1.index + 1
    if q1.empty:
        st.info("Tidak ada data hasil serealia pada filter ini.")
    else:
        top = q1.head(n_top).iloc[::-1]
        f = px.bar(top, x="cereal_yield_kg_ha", y="country_name", orientation="h", color="region", color_discrete_sequence=SERI,
                   labels={"cereal_yield_kg_ha": "kg per hektare", "country_name": "", "region": "Kawasan"},
                   title=f"{len(top)} negara dengan hasil serealia tertinggi")
        grafik(f, "q1_top", 120 + 34 * len(top))
        reg = q1.groupby("region")["cereal_yield_kg_ha"].median().sort_values().reset_index()
        f = px.bar(reg, x="cereal_yield_kg_ha", y="region", orientation="h", color_discrete_sequence=[SAND],
                   labels={"cereal_yield_kg_ha": "median kg per hektare", "region": ""}, title="Median hasil serealia per kawasan")
        grafik(f, "q1_reg", 120 + 40 * len(reg))
        t1 = q1.iloc[0]
        teks = (f"**Temuan Q1.** Tertinggi: **{t1['country_name']}** ({fmt(t1['cereal_yield_kg_ha'])} kg/ha); kawasan dengan median tertinggi: "
                f"**{reg.iloc[-1]['region']}**. ")
        idn = q1[q1["country_code"] == "IDN"]
        if not idn.empty:
            teks += f"Indonesia berada di peringkat **{int(idn.iloc[0]['peringkat'])} dari {len(q1)}** ({fmt(idn.iloc[0]['cereal_yield_kg_ha'])} kg/ha)."
        temuan(teks)

    # ---------------- Q2
    st.markdown("### Q2. Apakah pemakaian pupuk berkaitan dengan hasil serealia?")
    mengapa("**Scatter plot** dipilih karena yang dilihat adalah hubungan dua variabel numerik. Sumbu pupuk berskala log karena sebarannya sangat miring. "
            "Kekuatan hubungan diukur dengan korelasi **Spearman** (berbasis peringkat, tahan outlier) dan **Pearson** pada pupuk skala log.")
    q2 = d[["country_code", "country_name", "income_level", "year", "fertilizer_kg_ha", "cereal_yield_kg_ha"]].dropna()
    q2 = q2[q2["fertilizer_kg_ha"] > 0].copy()
    if len(q2) < 10:
        st.info("Data terlalu sedikit untuk analisis hubungan. Longgarkan filter.")
    else:
        q2["log_fert"] = np.log10(q2["fertilizer_kg_ha"])
        rho = q2["fertilizer_kg_ha"].corr(q2["cereal_yield_kg_ha"], method="spearman")
        r_p = q2["log_fert"].corr(q2["cereal_yield_kg_ha"])
        per_neg = q2.groupby("country_code")[["fertilizer_kg_ha", "cereal_yield_kg_ha"]].mean()
        rho_neg = per_neg["fertilizer_kg_ha"].corr(per_neg["cereal_yield_kg_ha"], method="spearman") if len(per_neg) > 2 else np.nan
        f = px.scatter(q2, x="fertilizer_kg_ha", y="cereal_yield_kg_ha", color="income_level", log_x=True, opacity=.7,
                       color_discrete_map=WARNA_INCOME, category_orders={"income_level": income_ada},
                       hover_data={"country_name": True, "year": True},
                       labels={"fertilizer_kg_ha": "Pupuk (kg/ha lahan arable, skala log)", "cereal_yield_kg_ha": "Hasil serealia (kg/ha)",
                               "income_level": "Kelompok pendapatan"}, title="Pupuk vs hasil serealia")
        b, a = np.polyfit(q2["log_fert"], q2["cereal_yield_kg_ha"], 1)
        xs = np.linspace(q2["log_fert"].min(), q2["log_fert"].max(), 50)
        f.add_trace(go.Scatter(x=10 ** xs, y=a + b * xs, mode="lines", name="garis tren", line=dict(color=INK, dash="dash", width=2)))
        grafik(f, "q2_scatter", 480)
        c = st.columns(4)
        with c[0]: kartu("Spearman", f"{rho:.2f}", kekuatan(rho), TEAL, "📈", MINT)
        with c[1]: kartu("Pearson (log pupuk)", f"{r_p:.2f}", "pada pupuk skala log", SAGE)
        with c[2]: kartu("Spearman per negara", "–" if np.isnan(rho_neg) else f"{rho_neg:.2f}", f"rata-rata {len(per_neg)} negara", SAND, "🌍", KREM)
        with c[3]: kartu("Pasangan data", fmt(len(q2)), "negara-tahun", SKY, "🔢", LANGIT)
        st.write("")
        temuan(f"**Temuan Q2.** Hubungan pupuk dan hasil serealia tergolong **{kekuatan(rho)}**. Korelasi dihitung juga pada rata-rata per negara supaya kesimpulan "
               "tidak hanya bergantung pada banyaknya tahun per negara. **Penafsiran hati-hati:** ini keterkaitan, bukan sebab-akibat. Pupuk juga mewakili faktor lain "
               "(irigasi, benih, kekayaan negara), sehingga bukan bukti bahwa pupuk menyebabkan hasil naik. Nilai p tidak ditonjolkan karena pengamatan negara-tahun tidak independen.")

    # ---------------- Q3
    st.markdown("### Q3. Apakah ekonomi dan iklim berkaitan dengan hasil serealia, dan bagaimana posisi Indonesia?")
    mengapa("Tiga visual dengan tujuan berbeda: **heatmap** (semua hubungan sekaligus), **boxplot + uji Kruskal-Wallis** (perbandingan antar kelompok), "
            "dan **garis tren** (perubahan waktu Indonesia dibanding ASEAN).")
    kol_ada = [k for k in NAMA if k in d.columns]
    sub = d[kol_ada].dropna(thresh=max(2, len(kol_ada) // 2))
    if len(sub) >= 20:
        corr = sub.rename(columns=NAMA).corr(method="spearman")
        f = px.imshow(corr, text_auto=".2f", color_continuous_scale=SKALA_DIV, zmin=-1, zmax=1, aspect="auto", title="Korelasi Spearman antarvariabel")
        grafik(f, "q3_heat", 560)
        ky = corr["Hasil serealia"].drop("Hasil serealia").dropna()
        top3 = ky.reindex(ky.abs().sort_values(ascending=False).index).head(3)
        temuan("**Temuan heatmap.** Paling berkaitan dengan hasil serealia: " + "; ".join(f"**{k}** ({v:.2f}, {kekuatan(v)})" for k, v in top3.items()) +
               ". Tanda negatif pada *nilai tambah agri* kemungkinan mencerminkan tingkat pembangunan (negara miskin porsi pertaniannya besar), "
               "bukan dampak buruk pertanian terhadap hasil.")
    else:
        st.info("Data terlalu sedikit untuk heatmap.")

    dd = d.dropna(subset=["cereal_yield_kg_ha"])
    f = px.box(dd, x="income_level", y="cereal_yield_kg_ha", color="income_level", color_discrete_map=WARNA_INCOME,
               category_orders={"income_level": income_ada}, labels={"income_level": "", "cereal_yield_kg_ha": "Hasil serealia (kg/ha)"},
               title="Hasil serealia per kelompok pendapatan")
    f.update_layout(showlegend=False)
    grafik(f, "q3_box", 460)
    f = px.scatter(dd.dropna(subset=["gdp_per_capita_usd"]), x="gdp_per_capita_usd", y="cereal_yield_kg_ha", color="income_level", log_x=True,
                   color_discrete_map=WARNA_INCOME, category_orders={"income_level": income_ada}, opacity=.65,
                   hover_data={"country_name": True, "year": True},
                   labels={"gdp_per_capita_usd": "GDP per kapita (US$, skala log)", "cereal_yield_kg_ha": "kg/ha", "income_level": "Kelompok"},
                   title="GDP per kapita vs hasil serealia")
    grafik(f, "q3_gdp", 480)
    grup = [g["cereal_yield_kg_ha"].dropna() for _, g in dd.groupby("income_level")]
    grup = [g for g in grup if len(g) > 2]
    d3 = dd[["log_gdp", "cereal_yield_kg_ha"]].dropna()
    c = st.columns(3)
    rho_g = d3["log_gdp"].corr(d3["cereal_yield_kg_ha"], method="spearman") if len(d3) > 5 else np.nan
    with c[0]: kartu("Spearman GDP vs hasil", "–" if np.isnan(rho_g) else f"{rho_g:.2f}", "" if np.isnan(rho_g) else kekuatan(rho_g), TEAL, "💵", MINT)
    if len(grup) >= 2:
        H, p_kw = stats.kruskal(*grup)
        with c[1]: kartu("Kruskal-Wallis (H)", f"{H:.1f}", f"p = {p_kw:.3g}", SAGE, "🧮")
        with c[2]: kartu("Beda antar kelompok", "Signifikan" if p_kw < .05 else "Tidak signifikan", "pada α = 0,05", SAND, "✅" if p_kw < .05 else "➖", KREM)
        med = dd.groupby("income_level")["cereal_yield_kg_ha"].median().reindex(income_ada).dropna()
        st.write("")
        temuan("**Temuan.** Median hasil serealia per kelompok: " + "; ".join(f"{k} = {fmt(v)}" for k, v in med.items()) + ". "
               "Kelompok pendapatan adalah klasifikasi World Bank **terkini** yang diterapkan ke seluruh tahun. GDP tidak 'menyebabkan' hasil panen naik; keduanya "
               "sama-sama berkaitan dengan teknologi, infrastruktur, dan investasi.")

    ref = data[data["year"].between(*SS.f_tahun)]
    semua = ref.groupby("year")["cereal_yield_kg_ha"].mean()
    asean = ref[ref["country_code"].isin(ASEAN)].groupby("year")["cereal_yield_kg_ha"].mean()
    indo = ref[ref["country_code"] == "IDN"].groupby("year")["cereal_yield_kg_ha"].mean()
    ft = go.Figure()
    ft.add_trace(go.Scatter(x=semua.index, y=semua.values, name="Rata-rata seluruh negara", line=dict(color=MUTED, width=2)))
    ft.add_trace(go.Scatter(x=asean.index, y=asean.values, name="Rata-rata ASEAN", line=dict(color=TEAL, width=3)))
    if not indo.dropna().empty:
        ft.add_trace(go.Scatter(x=indo.index, y=indo.values, name="Indonesia", line=dict(color=CORAL, width=4)))
    ft.update_layout(title="Tren hasil serealia: Indonesia vs ASEAN vs seluruh negara (referensi seluruh data)",
                     xaxis_title="Tahun", yaxis_title="kg per hektare")
    grafik(ft, "q3_tren", 420)
    if len(indo.dropna()) >= 2:
        a0, a1 = indo.dropna().index.min(), indo.dropna().index.max()
        tk = (f"**Temuan tren.** Hasil serealia Indonesia berubah dari {fmt(indo[a0])} kg/ha ({a0}) menjadi {fmt(indo[a1])} kg/ha ({a1}), "
              f"yaitu {((indo[a1] / indo[a0]) - 1) * 100:+.0f}%. ")
        if a1 in asean.index:
            tk += f"Pada {a1}, rata-rata ASEAN = {fmt(asean[a1])} kg/ha dan rata-rata seluruh negara = {fmt(semua[a1])} kg/ha."
        temuan(tk)


# =============================================================================
# 5. MODEL
# =============================================================================
with tabs[4]:
    st.markdown("### 6. Q4: model klasifikasi tingkat hasil serealia")
    mengapa("Dapatkah karakteristik pertanian, ekonomi, dan iklim mengklasifikasikan hasil serealia menjadi **Rendah / Sedang / Tinggi**?")
    panel("**Rancangan yang menjaga kualitas analisis:**\n"
          "• **Target** dari tertil hasil serealia; ambang dihitung **hanya dari data latih**.\n"
          "• **Hasil serealia tidak dipakai sebagai fitur** (itu target itu sendiri).\n"
          "• **Pemisahan latih/uji per negara**: satu negara tidak muncul di kedua sisi, supaya tidak bocor.\n"
          "• **Imputasi nilai kosong di dalam pipeline**, belajar hanya dari data latih.\n"
          "• Ada **baseline** sebagai pembanding. Fokusnya pada proses dan interpretasi, bukan mengejar akurasi.")

    pm, imp_df, lap = baca_csv("perbandingan_model.csv"), baca_csv("importance_fitur.csv"), baca_csv("laporan_klasifikasi.csv")
    mm = meta.get("model", {})
    uji = hasil[hasil["split"] == "uji"].dropna(subset=["kategori_aktual", "prediksi_kategori"])

    # ---- metrik resmi (sama persis dengan notebook)
    st.markdown("#### Kinerja model terbaik pada data uji (angka resmi notebook)")
    if pm is not None and mm.get("terbaik") in set(pm["model"]):
        b = pm[pm["model"] == mm["terbaik"]].iloc[0]
        resmi = {"akurasi": b["accuracy"], "presisi": b["precision_macro"], "recall": b["recall_macro"], "f1": b["f1_macro"]}
        nama_model = mm["terbaik"]
    else:
        resmi, nama_model = metrik(uji), "Model terbaik"
    c = st.columns(5)
    sub_model = f"{fmt(mm.get('n_uji', len(uji)))} baris uji" + (f" · {fmt(mm.get('negara_uji'))} negara" if mm.get("negara_uji") else " · nama model: salin meta_analisis.json")
    with c[0]: kartu("Model", nama_model, sub_model, TEAL, "🏆", MINT)
    with c[1]: kartu("Akurasi", f"{resmi['akurasi']:.3f}", f"{resmi['akurasi'] * 100:.1f}%", SAGE, "🎯")
    with c[2]: kartu("Presisi (macro)", f"{resmi['presisi']:.3f}", "rata-rata tiga kelas", SAND, "🔬", KREM)
    with c[3]: kartu("Recall (macro)", f"{resmi['recall']:.3f}", "rata-rata tiga kelas", PEACH, "📡", PERSIK)
    with c[4]: kartu("F1 (macro)", f"{resmi['f1']:.3f}", "ukuran utama", SKY, "⚖️", LANGIT)
    st.write("")
    if mm.get("cv_mean") is not None:
        temuan(f"**Validasi silang per negara (5-lipat):** F1-macro = **{mm['cv_mean']:.3f} ± {mm['cv_std']:.3f}**. Angka ini lebih stabil daripada satu kali pembagian "
               "latih/uji, dan sebaiknya menjadi angka utama saat presentasi.")

    # ---- mengapa angka data latih jauh lebih tinggi
    if "split" in hasil.columns:
        baris_bagian = []
        for nm_, sub_ in [("Data latih (sudah pernah dilihat model)", hasil[hasil["split"] == "latih"]),
                          ("Data uji (negara yang belum pernah dilihat)", hasil[hasil["split"] == "uji"]),
                          ("Semua data (latih + uji)", hasil)]:
            sub_ = sub_.dropna(subset=["kategori_aktual", "prediksi_kategori"])
            if len(sub_):
                m_ = metrik(sub_)
                baris_bagian.append({"bagian data": nm_, "baris": len(sub_), "akurasi": round(m_["akurasi"], 3), "F1-macro": round(m_["f1"], 3)})
        if len(baris_bagian) >= 2:
            st.markdown("#### Mengapa angka pada data latih jauh lebih tinggi?")
            tabel(pd.DataFrame(baris_bagian), column_config={
                "akurasi": st.column_config.ProgressColumn("akurasi", min_value=0, max_value=1, format="%.3f"),
                "F1-macro": st.column_config.ProgressColumn("F1-macro", min_value=0, max_value=1, format="%.3f")})
            a_lat, a_uji = baris_bagian[0]["akurasi"], baris_bagian[1]["akurasi"]
            if a_lat - a_uji > 0.15:
                temuan(f"**Temuan.** Akurasi pada data latih **{a_lat:.3f}**, pada data uji hanya **{a_uji:.3f}** (selisih {a_lat - a_uji:.2f}). Selisih sebesar ini adalah tanda "
                       "**overfitting**: model, terutama yang berbasis banyak pohon keputusan, dapat nyaris menghafal baris yang dipakai untuk belajar, sehingga hampir selalu benar di sana. "
                       "Angka itu tidak menunjukkan kemampuan menebak negara baru. Kemampuan sebenarnya ditunjukkan data uji (negara yang belum pernah dilihat) dan validasi silang per negara. "
                       "Karena itu data dibagi **per negara**, dan angka yang dilaporkan adalah angka data uji.")
            else:
                temuan(f"**Temuan.** Akurasi data latih {a_lat:.3f} dan data uji {a_uji:.3f}; selisihnya kecil, jadi tidak ada tanda kuat overfitting.")

    # ---- perbandingan model
    if pm is not None:
        st.markdown("#### Perbandingan model")
        mengapa("**Grouped bar** dipilih agar empat metrik dari tiap model dapat dibandingkan sekaligus. F1-macro dipakai sebagai penentu karena memperlakukan ketiga kelas setara.")
        pmm = pm.melt(id_vars="model", var_name="metrik", value_name="nilai")
        pmm["metrik"] = pmm["metrik"].map({"accuracy": "Akurasi", "precision_macro": "Presisi", "recall_macro": "Recall", "f1_macro": "F1-macro"})
        f = px.bar(pmm, x="model", y="nilai", color="metrik", barmode="group", color_discrete_sequence=[TEAL, SAND, PEACH, SKY],
                   labels={"nilai": "nilai", "model": "", "metrik": "Metrik"}, title="Metrik per model (data uji)", range_y=[0, 1])
        grafik(f, "m_banding", 420)
        cfg = {c_: st.column_config.ProgressColumn(c_, min_value=0, max_value=1, format="%.3f") for c_ in ["accuracy", "precision_macro", "recall_macro", "f1_macro"]}
        tabel(pm, column_config=cfg)
        peringatan("**Catatan baca baseline:** karena tiga kelas latih dibuat sama besar (tertil), baseline 'kelas terbanyak' memilih satu kelas secara arbitrer, sehingga skornya bisa sangat rendah. "
                   "Pembanding yang lebih adil untuk tiga kelas seimbang adalah tebakan acak (F1 ≈ 0.33). Perhatikan juga sebaran kelas pada data uji di bawah: "
                   "bila satu kelas mendominasi, akurasi saja dapat menyesatkan.")

    # ---- confusion matrix dan importance
    st.markdown("#### Confusion matrix dan fitur penting")
    s1, s2 = st.columns([1, 1])
    with s1:
        pil = st.radio("Data yang dievaluasi", ["uji", "latih", "semua"], horizontal=True, key="m_split",
                       help="Metrik pada data latih terlalu optimistis. Gunakan 'uji' untuk menilai kemampuan model.")
    with s2:
        pakai = st.checkbox("Terapkan filter sidebar pada bagian ini", value=False, key="m_filter")
    base = h if pakai else hasil
    mset = base if pil == "semua" else base[base["split"] == pil]
    mset = mset.dropna(subset=["kategori_aktual", "prediksi_kategori"])
    if pil == "latih":
        peringatan("Metrik pada data latih tidak menunjukkan kemampuan generalisasi model: model sudah pernah melihat baris-baris ini saat belajar.")
    elif pil == "semua":
        peringatan("Pilihan **semua** mencampur data latih (yang sudah pernah dilihat model) dengan data uji, sehingga angkanya **terlalu optimistis**. "
                   "Untuk menilai kemampuan sebenarnya, pilih **uji**.")
    if len(mset) < 5:
        st.info("Data terlalu sedikit pada pilihan ini.")
    else:
        if len(mset) < 30:
            peringatan(f"Hanya {len(mset)} baris dievaluasi, sehingga metrik kurang stabil.")
        mt = metrik(mset)
        if pakai or pil != "uji":
            c = st.columns(4)
            with c[0]: kartu("Akurasi", f"{mt['akurasi']:.3f}", f"{len(mset):,} baris dievaluasi", SAGE, "🎯")
            with c[1]: kartu("Presisi (macro)", f"{mt['presisi']:.3f}", "", SAND, "🔬", KREM)
            with c[2]: kartu("Recall (macro)", f"{mt['recall']:.3f}", "", PEACH, "📡", PERSIK)
            with c[3]: kartu("F1 (macro)", f"{mt['f1']:.3f}", "", SKY, "⚖️", LANGIT)
            st.write("")
        cm = pd.crosstab(mset["kategori_aktual"], mset["prediksi_kategori"]).reindex(index=LABEL, columns=LABEL, fill_value=0)
        f = px.imshow(cm, text_auto=True, color_continuous_scale=SKALA_SEQ, aspect="auto",
                      labels=dict(x="Prediksi", y="Aktual", color="Jumlah"), title=f"Confusion matrix ({pil})")
        grafik(f, "m_cm", 440)
        if imp_df is not None:
            im = imp_df.sort_values("importance")
            f = go.Figure(go.Bar(x=im["importance"], y=im["fitur"], orientation="h",
                                 marker_color=[TEAL if v > 0 else CORAL for v in im["importance"]]))
            f.update_layout(title="Pentingnya fitur (permutation importance, data uji)", xaxis_title="Penurunan F1-macro bila fitur diacak")
            grafik(f, "m_imp", 460)
        else:
            st.info("File `importance_fitur.csv` belum ada.")
        if imp_df is not None:
            tp = imp_df.sort_values("importance", ascending=False).head(3)["fitur"].tolist()
            temuan("**Fitur paling berpengaruh:** " + ", ".join(f"**{x}**" for x in tp) + ". Nilai mendekati nol atau negatif berarti fitur itu hampir tidak membantu "
                   "(mengacaknya tidak merusak prediksi).")

        dist = pd.concat([mset["kategori_aktual"].value_counts().rename("Aktual"), mset["prediksi_kategori"].value_counts().rename("Prediksi")],
                         axis=1).reindex(LABEL).fillna(0).reset_index().rename(columns={"index": "Kategori", "kategori_aktual": "Kategori"})
        dist = dist.melt(id_vars=dist.columns[0], var_name="Jenis", value_name="Jumlah").rename(columns={dist.columns[0]: "Kategori"})
        f = px.bar(dist, x="Kategori", y="Jumlah", color="Jenis", barmode="group", color_discrete_map={"Aktual": SKY, "Prediksi": TEAL},
                   title="Sebaran kategori: aktual vs prediksi")
        salah = mset[mset["kategori_aktual"] != mset["prediksi_kategori"]]
        urutan = {l: i for i, l in enumerate(LABEL)}
        dekat = (salah["kategori_aktual"].map(urutan) - salah["prediksi_kategori"].map(urutan)).abs().eq(1).mean() if len(salah) else np.nan
        grafik(f, "m_dist", 400)
        st.markdown("**Negara dengan salah prediksi terbanyak**")
        if len(salah):
            tabel(salah.groupby("country_name").size().sort_values(ascending=False).head(8).rename("jumlah salah").reset_index())
        else:
            st.write("Tidak ada salah prediksi.")
        if len(salah):
            temuan(f"Dari {len(salah)} salah prediksi, **{dekat:.0%}** terjadi antar-kelas bersebelahan (Rendah↔Sedang atau Sedang↔Tinggi). Ini wajar karena kategori dibuat dengan "
                   "memotong data kontinu, sehingga data di dekat ambang mudah tertukar.")

    # ---- laporan klasifikasi + sebaran latih/uji
    if lap is not None and mm:
        st.markdown("#### Laporan per kelas dan pembagian data")
        st.markdown("**Laporan klasifikasi (data uji, dari notebook)**")
        lp = lap.rename(columns={"f1-score": "f1"})
        tabel(lp.round(3))
        sb = pd.DataFrame({"Kelas": LABEL, "Latih": [mm["sebaran_latih"].get(k, 0) for k in LABEL], "Uji": [mm["sebaran_uji"].get(k, 0) for k in LABEL]})
        sbm = sb.melt(id_vars="Kelas", var_name="Data", value_name="Baris")
        f = px.bar(sbm, x="Kelas", y="Baris", color="Data", barmode="group", color_discrete_map={"Latih": SAGE, "Uji": PEACH},
                   title="Sebaran kelas pada data latih dan uji")
        grafik(f, "m_sebaran", 380)
        c = st.columns(3)
        with c[0]: kartu("Ambang Rendah → Sedang", f"{fmt(mm['ambang_rendah_maks'])}", "kg/ha (tertil ke-1 data latih)", CORAL, "📏")
        with c[1]: kartu("Ambang Sedang → Tinggi", f"{fmt(mm['ambang_sedang_maks'])}", "kg/ha (tertil ke-2 data latih)", SAND, "📏", KREM)
        with c[2]: kartu("Data latih / uji", f"{fmt(mm['n_latih'])} / {fmt(mm['n_uji'])}", f"{mm['negara_latih']} / {mm['negara_uji']} negara", TEAL, "✂️", MINT)
        st.write("")
        peringatan("**Keterbatasan:** jumlah negara terbatas dan data bersifat observasional, sehingga model ini menunjukkan keterkaitan fitur dengan tingkat hasil, bukan alat prediksi kebijakan.")

    # ---- cek per negara
    st.markdown("#### Cek prediksi per negara")
    neg = st.selectbox("Pilih negara", sorted(hasil["country_name"].dropna().unique()),
                       index=sorted(hasil["country_name"].dropna().unique()).index("Indonesia") if "Indonesia" in set(hasil["country_name"]) else 0, key="m_negara")
    hn = hasil[hasil["country_name"] == neg].sort_values("year").copy()
    hn["benar?"] = np.where(hn["kategori_aktual"] == hn["prediksi_kategori"], "✅", "❌")
    st.caption(f"{neg}: **{(hn['benar?'] == '✅').sum()} dari {len(hn)}** tahun diprediksi benar. Kolom *split* menunjukkan apakah negara ini masuk data latih atau uji.")
    tabel(hn[["year", "cereal_yield_kg_ha", "kategori_aktual", "prediksi_kategori", "benar?", "split"]].rename(
        columns={"year": "tahun", "cereal_yield_kg_ha": "hasil (kg/ha)"}).round(0))


# =============================================================================
# 6. DATA & KESIMPULAN
# =============================================================================
with tabs[5]:
    st.markdown("### Data terfilter")
    kolom_t = ["country_name", "region", "income_level", "year", "cereal_yield_kg_ha", "fertilizer_kg_ha", "arable_land_pct", "agri_value_added_pct",
               "agri_employment_pct", "gdp_per_capita_usd", "population", "avg_temp_c", "total_precip_mm", "kategori_aktual"]
    kolom_t = [k for k in kolom_t if k in d.columns]
    tabel(d[kolom_t].sort_values(["country_name", "year"]).round(2), height=380)
    st.download_button("⬇️ Unduh data terfilter (CSV)", d[kolom_t].to_csv(index=False).encode("utf-8"), file_name="data_terfilter.csv", mime="text/csv")

    st.markdown("### Kesimpulan")
    panel("Ringkasan jawaban keempat pertanyaan ada pada paragraf **Temuan** di bawah tiap visual (angka dihitung otomatis dari data). "
          "Alur ceritanya: latar belakang → pipeline → assessing (sebelum) → cleaning → assessing ulang (sesudah) → Q1 → Q2 → Q3 → Q4 → keterbatasan.")
    st.markdown("### Keterbatasan")
    peringatan("1. Data observasional: hanya menunjukkan **keterkaitan**, bukan sebab-akibat.\n"
               "2. Hasil serealia mencakup serealia secara gabungan, tidak per komoditas.\n"
               "3. Iklim diambil di koordinat ibu kota sehingga hanya mewakili kondisi negara secara kasar.\n"
               "4. Banyak nilai kosong pada indikator tertentu, terutama pupuk dan tahun-tahun terbaru.\n"
               "5. Cakupan dibatasi pada scope negara (ASEAN dan pembanding), bukan seluruh dunia.\n"
               "6. Kelompok pendapatan memakai klasifikasi World Bank terkini untuk seluruh tahun.")
    st.markdown("### Sumber data")
    panel("**World Bank Open Data** (indikator pertanian, ekonomi, dan kependudukan; lisensi CC BY 4.0) dan **NASA POWER** (suhu dan curah hujan, komunitas AG). "
          "Data diambil lewat Apache Airflow, disimpan di MySQL, lalu dianalisis di notebook. Dashboard ini membaca hasil ekspor notebook.")
