from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as MySqlOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import requests
import pandas as pd
import mysql.connector
import json

LAT, LON = -3.9985, 122.5127  # Koordinat Kendari
PAST_DAYS = 90

RAW_WEATHER = "/usr/local/airflow/dags/data/cuaca_raw.json"
RAW_AQ = "/usr/local/airflow/dags/data/udara_raw.json"
CLEAN_CUACA = "/usr/local/airflow/dags/data/cuaca_clean.csv"
CLEAN_UDARA = "/usr/local/airflow/dags/data/udara_clean.csv"
CLEAN_KORELASI = "/usr/local/airflow/dags/data/korelasi_clean.csv"

default_args = {
    'owner': 'airflow',
    'start_date': datetime.now() - timedelta(days=1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='etl_cuaca_kualitas_udara',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['etl', 'cuaca', 'kualitas-udara', 'mysql'],
) as dag:

    create_tables = MySqlOperator(
        task_id='create_tables_mysql',
        conn_id='mysql-local',
        sql="""
        CREATE TABLE IF NOT EXISTS cuaca_harian (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanggal DATE,
            suhu_max_c DECIMAL(4,1),
            suhu_min_c DECIMAL(4,1),
            curah_hujan_mm DECIMAL(6,2),
            kelembaban_persen DECIMAL(5,1),
            kecepatan_angin_kmh DECIMAL(5,1)
        );
        CREATE TABLE IF NOT EXISTS kualitas_udara_harian (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanggal DATE,
            pm2_5 DECIMAL(6,2),
            pm10 DECIMAL(6,2),
            ozon DECIMAL(6,2),
            no2 DECIMAL(6,2),
            kategori_aqi VARCHAR(30)
        );
        CREATE TABLE IF NOT EXISTS korelasi_cuaca_udara (
            id INT AUTO_INCREMENT PRIMARY KEY,
            variabel_cuaca VARCHAR(50),
            variabel_udara VARCHAR(50),
            koefisien_korelasi DECIMAL(5,3),
            interpretasi VARCHAR(255)
        );
        """,
    )

    def extract(**kwargs):
        url_cuaca = (
            f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,"
            f"relative_humidity_2m_mean,windspeed_10m_max"
            f"&past_days={PAST_DAYS}&forecast_days=1&timezone=auto"
        )
        r1 = requests.get(url_cuaca, timeout=15)
        r1.raise_for_status()
        with open(RAW_WEATHER, "w") as f:
            f.write(r1.text)

        url_udara = (
            f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={LAT}&longitude={LON}"
            f"&hourly=pm2_5,pm10,ozone,nitrogen_dioxide"
            f"&past_days={PAST_DAYS}&forecast_days=1&timezone=auto"
        )
        r2 = requests.get(url_udara, timeout=15)
        r2.raise_for_status()
        with open(RAW_AQ, "w") as f:
            f.write(r2.text)

        print("Data cuaca & kualitas udara berhasil diambil")

    extract_task = PythonOperator(task_id='extract', python_callable=extract)

    def transform(**kwargs):
        with open(RAW_WEATHER) as f:
            cuaca_json = json.load(f)
        with open(RAW_AQ) as f:
            udara_json = json.load(f)

        # --- TABEL CUACA ---
        df_cuaca = pd.DataFrame({
            "tanggal": cuaca_json["daily"]["time"],
            "suhu_max_c": cuaca_json["daily"]["temperature_2m_max"],
            "suhu_min_c": cuaca_json["daily"]["temperature_2m_min"],
            "curah_hujan_mm": cuaca_json["daily"]["precipitation_sum"],
            "kelembaban_persen": cuaca_json["daily"]["relative_humidity_2m_mean"],
            "kecepatan_angin_kmh": cuaca_json["daily"]["windspeed_10m_max"],
        })
        # Hanya buang baris kalau suhu (kolom inti) kosong, bukan semua kolom
        df_cuaca = df_cuaca.dropna(subset=["suhu_max_c", "suhu_min_c"])
        # Kolom lain yang mungkin kosong, isi pakai nilai hari sebelumnya
        df_cuaca = df_cuaca.fillna(method="ffill").fillna(method="bfill")

        # --- TABEL KUALITAS UDARA (agregasi dari data per jam ke per hari) ---
        df_udara_hourly = pd.DataFrame({
            "waktu": pd.to_datetime(udara_json["hourly"]["time"]),
            "pm2_5": udara_json["hourly"]["pm2_5"],
            "pm10": udara_json["hourly"]["pm10"],
            "ozon": udara_json["hourly"]["ozone"],
            "no2": udara_json["hourly"]["nitrogen_dioxide"],
        })
        df_udara_hourly = df_udara_hourly.dropna()
        df_udara_hourly["tanggal"] = df_udara_hourly["waktu"].dt.date

        df_udara = df_udara_hourly.groupby("tanggal").agg(
            pm2_5=("pm2_5", "max"),
            pm10=("pm10", "max"),
            ozon=("ozon", "max"),
            no2=("no2", "max"),
        ).reset_index()
        df_udara["tanggal"] = df_udara["tanggal"].astype(str)

        def kategori_aqi(pm25):
            if pm25 <= 15:
                return "Baik"
            elif pm25 <= 35:
                return "Sedang"
            else:
                return "Tidak Sehat"
        df_udara["kategori_aqi"] = df_udara["pm2_5"].apply(kategori_aqi)

        # --- SAMAKAN RENTANG TANGGAL kedua tabel (ambil irisan tanggal yang sama-sama ada) ---
        tanggal_sama = set(df_cuaca["tanggal"]) & set(df_udara["tanggal"])
        df_cuaca = df_cuaca[df_cuaca["tanggal"].isin(tanggal_sama)].sort_values("tanggal")
        df_udara = df_udara[df_udara["tanggal"].isin(tanggal_sama)].sort_values("tanggal")

        # --- GABUNGKAN buat hitung korelasi ---
        gabungan = pd.merge(df_cuaca, df_udara, on="tanggal", how="inner")

        korelasi_rows = [
            {
                "variabel_cuaca": "curah_hujan_mm",
                "variabel_udara": "pm2_5",
                "koefisien_korelasi": round(gabungan["curah_hujan_mm"].corr(gabungan["pm2_5"]), 3),
                "interpretasi": "Hujan tinggi umumnya menurunkan PM2.5 (mencuci partikel debu)"
            },
            {
                "variabel_cuaca": "kecepatan_angin_kmh",
                "variabel_udara": "pm10",
                "koefisien_korelasi": round(gabungan["kecepatan_angin_kmh"].corr(gabungan["pm10"]), 3),
                "interpretasi": "Angin kencang menyebarkan/mengencerkan polutan PM10"
            },
            {
                "variabel_cuaca": "suhu_max_c",
                "variabel_udara": "ozon",
                "koefisien_korelasi": round(gabungan["suhu_max_c"].corr(gabungan["ozon"]), 3),
                "interpretasi": "Suhu tinggi & sinar matahari kuat memicu pembentukan ozon permukaan"
            },
        ]
        df_korelasi = pd.DataFrame(korelasi_rows)

        df_cuaca.to_csv(CLEAN_CUACA, index=False)
        df_udara.to_csv(CLEAN_UDARA, index=False)
        df_korelasi.to_csv(CLEAN_KORELASI, index=False)
        print(f"Cuaca: {len(df_cuaca)} baris, Udara: {len(df_udara)} baris, Korelasi: {len(df_korelasi)} baris")

    transform_task = PythonOperator(task_id='transform', python_callable=transform)

    def load(**kwargs):
        mysql_conn = BaseHook.get_connection('mysql-local')
        conn = mysql.connector.connect(
            host=mysql_conn.host, user=mysql_conn.login,
            password=mysql_conn.password, database=mysql_conn.schema
        )
        cursor = conn.cursor()

        # Kosongkan dulu tabel lama, supaya tidak numpuk/dobel tiap kali DAG di-run
        cursor.execute("TRUNCATE TABLE cuaca_harian")
        cursor.execute("TRUNCATE TABLE kualitas_udara_harian")
        cursor.execute("TRUNCATE TABLE korelasi_cuaca_udara")

        df_cuaca = pd.read_csv(CLEAN_CUACA)
        for _, row in df_cuaca.iterrows():
            cursor.execute("""
                INSERT INTO cuaca_harian (tanggal, suhu_max_c, suhu_min_c, curah_hujan_mm, kelembaban_persen, kecepatan_angin_kmh)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, tuple(row))

        df_udara = pd.read_csv(CLEAN_UDARA)
        for _, row in df_udara.iterrows():
            cursor.execute("""
                INSERT INTO kualitas_udara_harian (tanggal, pm2_5, pm10, ozon, no2, kategori_aqi)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, tuple(row))

        df_korelasi = pd.read_csv(CLEAN_KORELASI)
        for _, row in df_korelasi.iterrows():
            cursor.execute("""
                INSERT INTO korelasi_cuaca_udara (variabel_cuaca, variabel_udara, koefisien_korelasi, interpretasi)
                VALUES (%s, %s, %s, %s)
            """, tuple(row))

        conn.commit()
        cursor.close()
        conn.close()
        print("Semua data berhasil dimasukkan ke MySQL (3 tabel, data lama sudah dibersihkan)")

    load_task = PythonOperator(task_id='load_to_mysql', python_callable=load)

    create_tables >> extract_task >> transform_task >> load_task