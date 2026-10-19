"""
DAG: pertanian_worldbank_pipeline
=================================
Topik : Faktor yang berkaitan dengan produktivitas pertanian (serealia) antarnegara

Sumber (keduanya tanpa API key):
  - World Bank Indicators API  -> data UTAMA (pertanian) + data ekonomi
  - NASA POWER Monthly/Annual API (komunitas AG) -> data PENDUKUNG (iklim di koordinat ibu kota)

Tabel MySQL:
  dim_country                       UNIQUE (country_code)
  fact_agriculture  FK country_id   UNIQUE (country_id, year)
  fact_economic     FK country_id   UNIQUE (country_id, year)
  fact_climate      FK country_id   UNIQUE (country_id, year)

Prinsip:
  - DAG hanya EXTRACT -> VALIDATE -> LOAD. Nilai kosong (NULL) sengaja DIBIARKAN
    apa adanya; cleaning dilakukan di notebook (assessing -> cleaning -> assessing ulang).
  - Load memakai UPSERT (INSERT ... ON DUPLICATE KEY UPDATE) sehingga DAG aman
    dijalankan berulang tanpa membuat baris ganda dan tanpa TRUNCATE
    (TRUNCATE tidak bisa dipakai pada tabel yang dirujuk foreign key).

Kebutuhan (requirements.txt Astro):
  requests, pandas, mysql-connector-python, apache-airflow-providers-mysql
Koneksi Airflow: conn_id "mysql-local" (database/schema harus sudah ada).
"""
import calendar
import logging
import math
import os
import time
from datetime import datetime, timedelta

import mysql.connector
import pandas as pd
import requests
from airflow import DAG
from airflow.hooks.base import BaseHook
from airflow.operators.python import PythonOperator
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator

log = logging.getLogger("airflow.task")

# ----------------------------------------------------------------------------
# KONFIGURASI (ubah di sini sesuai scope tugas)
# ----------------------------------------------------------------------------
MYSQL_CONN_ID = "mysql-local"
START_YEAR, END_YEAR = 2000, 2024

# Scope negara (kode ISO3): ASEAN + produsen pertanian besar + pembanding.
SCOPE = [
    # ASEAN
    "IDN", "MYS", "THA", "VNM", "PHL", "SGP", "KHM", "LAO", "MMR", "BRN",
    # Asia lain
    "CHN", "IND", "JPN", "KOR", "BGD", "PAK",
    # Amerika
    "USA", "BRA", "ARG", "MEX", "CAN", "COL", "PER",
    # Eropa
    "FRA", "DEU", "GBR", "ESP", "ITA", "NLD", "POL",
    # Afrika
    "NGA", "ETH", "EGY", "ZAF", "KEN", "TZA", "GHA",
    # Oseania
    "AUS", "NZL",
    # Lainnya
    "RUS", "TUR", "IRN",
]

# kode indikator World Bank -> nama kolom di MySQL
AGRI_INDICATORS = {
    "AG.YLD.CREL.KG": "cereal_yield_kg_ha",     # hasil serealia (kg/ha)
    "AG.CON.FERT.ZS": "fertilizer_kg_ha",       # pupuk (kg/ha lahan arable)
    "AG.LND.ARBL.ZS": "arable_land_pct",        # lahan arable (% luas lahan)
    "NV.AGR.TOTL.ZS": "agri_value_added_pct",   # nilai tambah pertanian (% PDB)
    "SL.AGR.EMPL.ZS": "agri_employment_pct",    # tenaga kerja pertanian (%)
}
ECON_INDICATORS = {
    "NY.GDP.PCAP.CD": "gdp_per_capita_usd",
    "SP.POP.TOTL": "population",
}

WB_BASE = "https://api.worldbank.org/v2"
POWER_MONTHLY = "https://power.larc.nasa.gov/api/temporal/monthly/point"
HEADERS = {"User-Agent": "tugas-kuliah-pipeline-pertanian/1.0"}

CLIMATE_SLEEP_SEC = 2.0      # jeda antar-request NASA POWER (sopan terhadap batas akses)
CLIMATE_CACHE_DAYS = 7       # hasil per negara dipakai ulang jika retry/jalankan ulang

DATA_DIR = os.environ.get("PIPELINE_DATA_DIR", "/usr/local/airflow/include/data")
CACHE_DIR = os.path.join(DATA_DIR, "power_cache")
CSV_COUNTRY = os.path.join(DATA_DIR, "raw_country.csv")
CSV_AGRI = os.path.join(DATA_DIR, "raw_agriculture.csv")
CSV_ECON = os.path.join(DATA_DIR, "raw_economic.csv")
CSV_CLIMATE = os.path.join(DATA_DIR, "raw_climate.csv")

default_args = {
    "owner": "airflow",
    "start_date": datetime(2026, 9, 1),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


# ----------------------------------------------------------------------------
# HELPER
# ----------------------------------------------------------------------------
def _get_json(url, params=None, tries=5, timeout=90):
    """GET dengan retry untuk error jaringan, HTTP 429, dan 5xx."""
    err = ""
    for attempt in range(1, tries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
        except requests.RequestException as e:
            err = str(e)
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code != 429 and r.status_code < 500:
                # error permanen (mis. parameter salah) -> jangan diulang
                raise RuntimeError(f"HTTP {r.status_code} dari {url}: {r.text[:300]}")
            err = f"HTTP {r.status_code}: {r.text[:150]}"
        if attempt < tries:
            wait = 15 * attempt
            log.warning("Percobaan %s/%s gagal (%s). Tunggu %ss...", attempt, tries, err, wait)
            time.sleep(wait)
    raise RuntimeError(f"Gagal setelah {tries} percobaan: {url} ({err})")


def _wb_paginate(path, params):
    """Ambil semua halaman dari World Bank API. Respons: [meta, daftar_data]."""
    items, page = [], 1
    while True:
        data = _get_json(
            f"{WB_BASE}/{path}",
            params={**params, "format": "json", "per_page": 10000, "page": page},
        )
        if not isinstance(data, list) or len(data) < 2 or data[1] is None:
            # World Bank kadang membalas 200 berisi pesan error (mis. kode indikator salah)
            raise ValueError(f"World Bank tidak mengembalikan data untuk '{path}': {str(data)[:300]}")
        meta, rows = data[0], data[1]
        items.extend(rows)
        if page >= int(meta.get("pages", 1)):
            break
        page += 1
    return items


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def _i(v):
    return None if v is None or pd.isna(v) else int(round(float(v)))


def _s(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    v = str(v).strip()
    return v or None


def _connect():
    c = BaseHook.get_connection(MYSQL_CONN_ID)
    return mysql.connector.connect(
        host=c.host, port=c.port or 3306, user=c.login,
        password=c.password, database=c.schema, charset="utf8mb4",
    )


# ----------------------------------------------------------------------------
# EXTRACT
# ----------------------------------------------------------------------------
def extract_countries():
    """Metadata negara dari World Bank (region, income level, koordinat ibu kota)."""
    os.makedirs(DATA_DIR, exist_ok=True)
    items = _wb_paginate("country", {})
    rows = []
    for c in items:
        code = c.get("id")
        if code not in SCOPE:  # sekaligus membuang baris agregat (WLD, kawasan, dll.)
            continue
        rows.append({
            "country_code": code,
            "country_name": c.get("name"),
            "region": (c.get("region") or {}).get("value"),
            "income_level": (c.get("incomeLevel") or {}).get("value"),
            "capital_city": c.get("capitalCity"),
            "capital_lat": c.get("latitude"),
            "capital_lon": c.get("longitude"),
        })
    df = pd.DataFrame(rows)
    missing = set(SCOPE) - set(df["country_code"]) if not df.empty else set(SCOPE)
    if missing:
        log.warning("Kode negara tidak ditemukan di World Bank: %s", sorted(missing))
    df.to_csv(CSV_COUNTRY, index=False)
    log.info("Negara tersimpan: %s dari %s", len(df), len(SCOPE))


def _extract_indicator_group(indicators, out_csv, essential=()):
    """Indikator 'essential' yang gagal menghentikan DAG; yang lain dilewati (kolom jadi NULL)."""
    frames, failed = [], []
    for code, col in indicators.items():
        try:
            items = _wb_paginate(f"country/all/indicator/{code}", {"date": f"{START_YEAR}:{END_YEAR}"})
        except Exception as e:
            if col in essential:
                raise
            log.error("INDIKATOR DILEWATI %s (%s): %s -> kolom dimuat sebagai NULL semua", code, col, e)
            failed.append(col)
            continue
        df = pd.DataFrame([
            {
                "country_code": i.get("countryiso3code"),
                "year": int(i["date"]),
                "indicator": col,
                "value": i.get("value"),
            }
            for i in items
        ])
        df = df[df["country_code"].isin(SCOPE)].copy()
        df["value"] = pd.to_numeric(df["value"], errors="coerce")  # tipe saja, NULL tetap NULL
        log.info("%s (%s): %s baris, %s kosong", code, col, len(df), int(df["value"].isna().sum()))
        frames.append(df)

    long_df = pd.concat(frames, ignore_index=True)
    if long_df.empty:
        raise ValueError(f"Tidak ada data untuk {list(indicators)}")
    wide = long_df.pivot(index=["country_code", "year"], columns="indicator", values="value")
    wide = wide.reset_index()
    wide.columns.name = None
    for col in failed:
        wide[col] = None
    wide = wide[["country_code", "year", *indicators.values()]]
    wide.to_csv(out_csv, index=False)
    log.info("Disimpan %s (%s baris). Indikator dilewati: %s", out_csv, len(wide), failed or "tidak ada")


def extract_worldbank():
    os.makedirs(DATA_DIR, exist_ok=True)
    _extract_indicator_group(AGRI_INDICATORS, CSV_AGRI, essential=("cereal_yield_kg_ha",))
    _extract_indicator_group(ECON_INDICATORS, CSV_ECON, essential=("gdp_per_capita_usd",))


def _power_to_yearly(data, code):
    """Ubah respons NASA POWER (bulanan + nilai tahunan 'MM=13') menjadi 1 baris per tahun."""
    par = data["properties"]["parameter"]
    t2m, prec = par["T2M"], par["PRECTOTCORR"]

    def val(series, key):
        v = series.get(key)
        return None if v is None or float(v) <= -990 else float(v)   # -999 = data hilang

    rows = []
    for year in range(START_YEAR, END_YEAR + 1):
        t_annual = val(t2m, f"{year}13")
        p_annual = val(prec, f"{year}13")            # satuan: mm/hari (rata-rata tahunan)
        months_ok = sum(val(t2m, f"{year}{m:02d}") is not None for m in range(1, 13))
        days = 366 if calendar.isleap(year) else 365
        rows.append({
            "country_code": code,
            "year": year,
            "avg_temp_c": t_annual,
            "total_precip_mm": None if p_annual is None else p_annual * days,
            "months_with_data": months_ok,
        })
    return pd.DataFrame(rows)


def extract_climate():
    """Iklim tahunan per negara dari NASA POWER (koordinat ibu kota, komunitas AG)."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    countries = pd.read_csv(CSV_COUNTRY)
    frames, failed, consecutive = [], [], 0
    for r in countries.itertuples(index=False):
        if pd.isna(r.capital_lat) or pd.isna(r.capital_lon):
            log.warning("%s tidak punya koordinat ibu kota, dilewati", r.country_code)
            continue

        cache = os.path.join(CACHE_DIR, f"{r.country_code}.csv")
        if os.path.exists(cache) and (time.time() - os.path.getmtime(cache)) < CLIMATE_CACHE_DAYS * 86400:
            frames.append(pd.read_csv(cache))
            continue

        try:
            data = _get_json(POWER_MONTHLY, params={
                "parameters": "T2M,PRECTOTCORR",
                "community": "AG",
                "latitude": r.capital_lat,
                "longitude": r.capital_lon,
                "start": START_YEAR,
                "end": END_YEAR,
                "format": "JSON",
            })
            agg = _power_to_yearly(data, r.country_code)
        except Exception as e:
            failed.append(r.country_code)
            consecutive += 1
            log.error("Iklim %s GAGAL: %s", r.country_code, e)
            if consecutive >= 3:
                raise RuntimeError(
                    "3 negara berturut-turut gagal mengambil iklim dari NASA POWER. "
                    "Periksa pesan error di atas. Data yang sudah berhasil tersimpan di cache."
                )
            continue
        consecutive = 0
        agg.to_csv(cache, index=False)
        frames.append(agg)
        log.info("Iklim %s selesai (%s tahun)", r.country_code, len(agg))
        time.sleep(CLIMATE_SLEEP_SEC)

    if not frames:
        raise ValueError("Tidak ada data iklim yang berhasil diambil")
    if len(failed) > 0.25 * len(countries):
        raise RuntimeError(f"Terlalu banyak negara tanpa data iklim ({len(failed)}): {failed}")
    if failed:
        log.warning("Negara tanpa data iklim (akan kosong di fact_climate): %s", failed)
    pd.concat(frames, ignore_index=True).to_csv(CSV_CLIMATE, index=False)


# ----------------------------------------------------------------------------
# VALIDATE (hanya memeriksa, TIDAK membersihkan)
# ----------------------------------------------------------------------------
def validate():
    for path in (CSV_COUNTRY, CSV_AGRI, CSV_ECON, CSV_CLIMATE):
        df = pd.read_csv(path)
        if df.empty:
            raise ValueError(f"{path} kosong")
        if "year" in df.columns and df.duplicated(["country_code", "year"]).any():
            raise ValueError(f"{path} punya duplikat (country_code, year); melanggar unique key")
        nulls = (df.isna().mean() * 100).round(1)
        log.info("%s: %s baris | %% kosong per kolom:\n%s", os.path.basename(path), len(df), nulls.to_string())

    n_country = pd.read_csv(CSV_COUNTRY)["country_code"].nunique()
    n_climate = pd.read_csv(CSV_CLIMATE)["country_code"].nunique()
    log.info("Cakupan negara: dim=%s, iklim=%s, scope=%s", n_country, n_climate, len(SCOPE))


# ----------------------------------------------------------------------------
# LOAD (UPSERT; aman dijalankan berulang)
# ----------------------------------------------------------------------------
def load_dim_country():
    df = pd.read_csv(CSV_COUNTRY)
    rows = [
        (r.country_code, r.country_name, _s(r.region), _s(r.income_level),
         _s(r.capital_city), _f(r.capital_lat), _f(r.capital_lon))
        for r in df.itertuples(index=False)
    ]
    sql = """
        INSERT INTO dim_country
            (country_code, country_name, region, income_level, capital_city, capital_lat, capital_lon)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            country_name = VALUES(country_name), region = VALUES(region),
            income_level = VALUES(income_level), capital_city = VALUES(capital_city),
            capital_lat = VALUES(capital_lat), capital_lon = VALUES(capital_lon)
    """
    conn = _connect()
    cur = conn.cursor()
    cur.executemany(sql, rows)
    conn.commit()
    cur.close()
    conn.close()
    log.info("dim_country: %s baris di-upsert", len(rows))


def _load_fact(table, csv_path, value_cols, int_cols=()):
    df = pd.read_csv(csv_path)
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT country_id, country_code FROM dim_country")
    id_map = {code: cid for cid, code in cur.fetchall()}

    col_list = ", ".join(f"`{c}`" for c in value_cols)
    placeholders = ", ".join(["%s"] * (2 + len(value_cols)))
    updates = ", ".join(f"`{c}` = VALUES(`{c}`)" for c in value_cols)
    sql = (
        f"INSERT INTO {table} (country_id, `year`, {col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {updates}"
    )

    rows, skipped = [], 0
    for r in df.to_dict("records"):
        cid = id_map.get(r["country_code"])
        if cid is None:
            skipped += 1
            continue
        vals = [_i(r[c]) if c in int_cols else _f(r[c]) for c in value_cols]
        rows.append((cid, int(r["year"]), *vals))

    for i in range(0, len(rows), 1000):
        cur.executemany(sql, rows[i:i + 1000])
    conn.commit()
    cur.close()
    conn.close()
    log.info("%s: %s baris di-upsert, %s dilewati (negara tidak ada di dim_country)", table, len(rows), skipped)


def load_fact_agriculture():
    _load_fact("fact_agriculture", CSV_AGRI, list(AGRI_INDICATORS.values()))


def load_fact_economic():
    _load_fact("fact_economic", CSV_ECON, list(ECON_INDICATORS.values()), int_cols=("population",))


def load_fact_climate():
    _load_fact("fact_climate", CSV_CLIMATE,
               ["avg_temp_c", "total_precip_mm", "months_with_data"], int_cols=("months_with_data",))


def verify_load():
    """Penutup: pastikan tabel terisi, FK konsisten, dan hitung baris lengkap untuk analisis/ML."""
    conn = _connect()
    cur = conn.cursor()
    empty = []
    for t in ("dim_country", "fact_agriculture", "fact_economic", "fact_climate"):
        cur.execute(f"SELECT COUNT(*) FROM {t}")
        n = cur.fetchone()[0]
        log.info("%s: %s baris", t, n)
        if n == 0:
            empty.append(t)
    for t in ("fact_agriculture", "fact_economic", "fact_climate"):
        cur.execute(
            f"SELECT COUNT(*) FROM {t} f LEFT JOIN dim_country d ON d.country_id = f.country_id "
            "WHERE d.country_id IS NULL"
        )
        orphan = cur.fetchone()[0]
        if orphan:
            raise ValueError(f"{t} punya {orphan} baris tanpa induk di dim_country")
    cur.execute("""
        SELECT COUNT(*) FROM fact_agriculture a
        JOIN fact_economic e ON e.country_id = a.country_id AND e.`year` = a.`year`
        JOIN fact_climate  c ON c.country_id = a.country_id AND c.`year` = a.`year`
        WHERE a.cereal_yield_kg_ha IS NOT NULL
    """)
    log.info("Baris gabungan 3 tabel dengan cereal_yield terisi: %s", cur.fetchone()[0])
    cur.close()
    conn.close()
    if empty:
        raise ValueError(f"Tabel kosong setelah load: {empty}")
    log.info("SELESAI. Semua data sudah di MySQL; lanjut ke notebook.")


# ----------------------------------------------------------------------------
# DDL (urutan penting: tabel induk dulu, baru tabel yang punya FK)
# ----------------------------------------------------------------------------
DDL = [
    """
    CREATE TABLE IF NOT EXISTS dim_country (
        country_id    INT AUTO_INCREMENT PRIMARY KEY,
        country_code  CHAR(3)      NOT NULL,
        country_name  VARCHAR(100) NOT NULL,
        region        VARCHAR(80),
        income_level  VARCHAR(50),
        capital_city  VARCHAR(80),
        capital_lat   DECIMAL(9,6),
        capital_lon   DECIMAL(9,6),
        loaded_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_country_code (country_code)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_agriculture (
        agriculture_id       INT AUTO_INCREMENT PRIMARY KEY,
        country_id           INT      NOT NULL,
        `year`               SMALLINT NOT NULL,
        cereal_yield_kg_ha   DOUBLE,
        fertilizer_kg_ha     DOUBLE,
        arable_land_pct      DOUBLE,
        agri_value_added_pct DOUBLE,
        agri_employment_pct  DOUBLE,
        loaded_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_agri_country_year (country_id, `year`),
        CONSTRAINT fk_agri_country FOREIGN KEY (country_id) REFERENCES dim_country (country_id)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_economic (
        economic_id        INT AUTO_INCREMENT PRIMARY KEY,
        country_id         INT      NOT NULL,
        `year`             SMALLINT NOT NULL,
        gdp_per_capita_usd DOUBLE,
        population         BIGINT,
        loaded_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_econ_country_year (country_id, `year`),
        CONSTRAINT fk_econ_country FOREIGN KEY (country_id) REFERENCES dim_country (country_id)
    ) ENGINE=InnoDB
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_climate (
        climate_id      INT AUTO_INCREMENT PRIMARY KEY,
        country_id      INT      NOT NULL,
        `year`          SMALLINT NOT NULL,
        avg_temp_c      DOUBLE,
        total_precip_mm DOUBLE,
        months_with_data SMALLINT,
        loaded_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY uq_climate_country_year (country_id, `year`),
        CONSTRAINT fk_climate_country FOREIGN KEY (country_id) REFERENCES dim_country (country_id)
    ) ENGINE=InnoDB
    """,
]

# ----------------------------------------------------------------------------
# DAG
# ----------------------------------------------------------------------------
with DAG(
    dag_id="pertanian_worldbank_pipeline",
    default_args=default_args,
    schedule="@once",       # jalan SEKALI otomatis begitu DAG di-unpause; bisa juga di-trigger manual
    catchup=False,
    tags=["worldbank", "nasa-power", "pertanian", "mysql"],
) as dag:

    create_tables = SQLExecuteQueryOperator(
        task_id="create_tables_mysql",
        conn_id=MYSQL_CONN_ID,
        sql=DDL,
    )

    t_countries = PythonOperator(task_id="extract_countries", python_callable=extract_countries)
    t_worldbank = PythonOperator(task_id="extract_worldbank", python_callable=extract_worldbank)
    t_climate = PythonOperator(task_id="extract_climate", python_callable=extract_climate)
    t_validate = PythonOperator(task_id="validate", python_callable=validate)

    t_load_dim = PythonOperator(task_id="load_dim_country", python_callable=load_dim_country)
    t_load_agri = PythonOperator(task_id="load_fact_agriculture", python_callable=load_fact_agriculture)
    t_load_econ = PythonOperator(task_id="load_fact_economic", python_callable=load_fact_economic)
    t_load_climate = PythonOperator(task_id="load_fact_climate", python_callable=load_fact_climate)

    t_verify = PythonOperator(task_id="verify_load", python_callable=verify_load)

    create_tables >> t_countries >> [t_worldbank, t_climate] >> t_validate >> t_load_dim
    t_load_dim >> [t_load_agri, t_load_econ, t_load_climate] >> t_verify
