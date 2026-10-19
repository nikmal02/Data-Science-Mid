from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as MySqlOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import requests
import pandas as pd
import mysql.connector
import json

LAT, LON = -3.9700, 122.6100  # Perairan Teluk Kendari
PAST_DAYS = 90

RAW_ANGIN = "/usr/local/airflow/dags/data/angin_raw.json"
RAW_MARINE = "/usr/local/airflow/dags/data/marine_raw.json"
CLEAN_ANGIN = "/usr/local/airflow/dags/data/angin_clean.csv"
CLEAN_GELOMBANG = "/usr/local/airflow/dags/data/gelombang_clean.csv"
CLEAN_ARUS = "/usr/local/airflow/dags/data/arus_clean.csv"
CLEAN_KORELASI = "/usr/local/airflow/dags/data/korelasi_clean.csv"

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2026, 9, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='etl_maritim_kendari',
    default_args=default_args,
    schedule="@daily",
    catchup=False,
    tags=['etl', 'maritim', 'angin', 'gelombang', 'arus', 'mysql'],
) as dag:

    create_tables = MySqlOperator(
        task_id='create_tables_mysql',
        conn_id='mysql-local',
        sql="""
        DROP TABLE IF EXISTS cuaca_angin_harian;
        DROP TABLE IF EXISTS gelombang_laut_harian;
        DROP TABLE IF EXISTS arus_laut_harian;
        DROP TABLE IF EXISTS korelasi_maritim;

        CREATE TABLE cuaca_angin_harian (
            id INT AUTO_INCREMENT PRIMARY KEY,
            waktu DATETIME UNIQUE,
            kecepatan_angin_kmh DECIMAL(6,2),
            arah_angin_derajat DECIMAL(6,2)
        );
        CREATE TABLE gelombang_laut_harian (
            id INT AUTO_INCREMENT PRIMARY KEY,
            waktu DATETIME UNIQUE,
            tinggi_gelombang_m DECIMAL(6,2),
            periode_gelombang_detik DECIMAL(6,2),
            arah_gelombang_derajat DECIMAL(6,2)
        );
        CREATE TABLE arus_laut_harian (
            id INT AUTO_INCREMENT PRIMARY KEY,
            waktu DATETIME UNIQUE,
            kecepatan_arus_kmh DECIMAL(6,2),
            arah_arus_derajat DECIMAL(6,2)
        );
        CREATE TABLE korelasi_maritim (
            id INT AUTO_INCREMENT PRIMARY KEY,
            variabel_1 VARCHAR(50),
            variabel_2 VARCHAR(50),
            koefisien_korelasi DECIMAL(5,3),
            interpretasi VARCHAR(255)
        );
        """,
    )

    def extract(**kwargs):
        url_angin = (
            f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}"
            f"&hourly=windspeed_10m,winddirection_10m"
            f"&past_days={PAST_DAYS}&forecast_days=1&timezone=auto"
        )
        r1 = requests.get(url_angin, timeout=60)
        r1.raise_for_status()
        with open(RAW_ANGIN, "w") as f:
            f.write(r1.text)

        url_marine = (
            f"https://marine-api.open-meteo.com/v1/marine?latitude={LAT}&longitude={LON}"
            f"&hourly=wave_height,wave_period,wave_direction,ocean_current_velocity,ocean_current_direction"
            f"&cell_selection=sea"
            f"&past_days={PAST_DAYS}&forecast_days=1&timezone=auto"
        )
        r2 = requests.get(url_marine, timeout=60)
        r2.raise_for_status()
        with open(RAW_MARINE, "w") as f:
            f.write(r2.text)

        print("Data angin & marine (per jam) berhasil diambil")

    extract_task = PythonOperator(task_id='extract', python_callable=extract)

    def transform(**kwargs):
        with open(RAW_ANGIN) as f:
            angin_json = json.load(f)
        with open(RAW_MARINE) as f:
            marine_json = json.load(f)

        # --- TABEL 1: ANGIN (per jam) ---
        df_angin = pd.DataFrame({
            "waktu": pd.to_datetime(angin_json["hourly"]["time"]),
            "kecepatan_angin_kmh": angin_json["hourly"]["windspeed_10m"],
            "arah_angin_derajat": angin_json["hourly"]["winddirection_10m"],
        })
        df_angin = df_angin.dropna()

        # --- TABEL 2: GELOMBANG (per jam) ---
        df_gelombang = pd.DataFrame({
            "waktu": pd.to_datetime(marine_json["hourly"]["time"]),
            "tinggi_gelombang_m": marine_json["hourly"]["wave_height"],
            "periode_gelombang_detik": marine_json["hourly"]["wave_period"],
            "arah_gelombang_derajat": marine_json["hourly"]["wave_direction"],
        })
        df_gelombang = df_gelombang.dropna()

        # --- TABEL 3: ARUS LAUT (per jam) ---
        df_arus = pd.DataFrame({
            "waktu": pd.to_datetime(marine_json["hourly"]["time"]),
            "kecepatan_arus_kmh": marine_json["hourly"]["ocean_current_velocity"],
            "arah_arus_derajat": marine_json["hourly"]["ocean_current_direction"],
        })
        df_arus = df_arus.dropna()

        # --- SAMAKAN rentang waktu ketiga tabel ---
        waktu_sama = set(df_angin["waktu"]) & set(df_gelombang["waktu"]) & set(df_arus["waktu"])
        df_angin = df_angin[df_angin["waktu"].isin(waktu_sama)].sort_values("waktu")
        df_gelombang = df_gelombang[df_gelombang["waktu"].isin(waktu_sama)].sort_values("waktu")
        df_arus = df_arus[df_arus["waktu"].isin(waktu_sama)].sort_values("waktu")

        # --- GABUNGKAN buat hitung korelasi ---
        gabungan = df_angin.merge(df_gelombang, on="waktu").merge(df_arus, on="waktu")

        korelasi_rows = [
            {
                "variabel_1": "kecepatan_angin_kmh",
                "variabel_2": "tinggi_gelombang_m",
                "koefisien_korelasi": round(gabungan["kecepatan_angin_kmh"].corr(gabungan["tinggi_gelombang_m"]), 3),
                "interpretasi": "Angin kencang mendorong terbentuknya gelombang lebih tinggi"
            },
            {
                "variabel_1": "kecepatan_angin_kmh",
                "variabel_2": "kecepatan_arus_kmh",
                "koefisien_korelasi": round(gabungan["kecepatan_angin_kmh"].corr(gabungan["kecepatan_arus_kmh"]), 3),
                "interpretasi": "Angin permukaan turut menggerakkan arus laut (wind-driven current)"
            },
            {
                "variabel_1": "tinggi_gelombang_m",
                "variabel_2": "kecepatan_arus_kmh",
                "koefisien_korelasi": round(gabungan["tinggi_gelombang_m"].corr(gabungan["kecepatan_arus_kmh"]), 3),
                "interpretasi": "Gelombang & arus sama-sama digerakkan angin, sehingga cenderung berpola serupa"
            },
        ]
        df_korelasi = pd.DataFrame(korelasi_rows)

        df_angin.to_csv(CLEAN_ANGIN, index=False)
        df_gelombang.to_csv(CLEAN_GELOMBANG, index=False)
        df_arus.to_csv(CLEAN_ARUS, index=False)
        df_korelasi.to_csv(CLEAN_KORELASI, index=False)
        print(f"Angin: {len(df_angin)} baris, Gelombang: {len(df_gelombang)} baris, Arus: {len(df_arus)} baris")

    transform_task = PythonOperator(task_id='transform', python_callable=transform)

    def load(**kwargs):
        mysql_conn = BaseHook.get_connection('mysql-local')
        conn = mysql.connector.connect(
            host=mysql_conn.host, user=mysql_conn.login,
            password=mysql_conn.password, database=mysql_conn.schema
        )
        cursor = conn.cursor()

        df_angin = pd.read_csv(CLEAN_ANGIN)
        for _, row in df_angin.iterrows():
            cursor.execute("""
                INSERT INTO cuaca_angin_harian (waktu, kecepatan_angin_kmh, arah_angin_derajat)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    kecepatan_angin_kmh = VALUES(kecepatan_angin_kmh),
                    arah_angin_derajat = VALUES(arah_angin_derajat)
            """, tuple(row))

        df_gelombang = pd.read_csv(CLEAN_GELOMBANG)
        for _, row in df_gelombang.iterrows():
            cursor.execute("""
                INSERT INTO gelombang_laut_harian (waktu, tinggi_gelombang_m, periode_gelombang_detik, arah_gelombang_derajat)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    tinggi_gelombang_m = VALUES(tinggi_gelombang_m),
                    periode_gelombang_detik = VALUES(periode_gelombang_detik),
                    arah_gelombang_derajat = VALUES(arah_gelombang_derajat)
            """, tuple(row))

        df_arus = pd.read_csv(CLEAN_ARUS)
        for _, row in df_arus.iterrows():
            cursor.execute("""
                INSERT INTO arus_laut_harian (waktu, kecepatan_arus_kmh, arah_arus_derajat)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    kecepatan_arus_kmh = VALUES(kecepatan_arus_kmh),
                    arah_arus_derajat = VALUES(arah_arus_derajat)
            """, tuple(row))

        # Tabel korelasi tetap ditimpa tiap run (snapshot analisis terbaru)
        cursor.execute("TRUNCATE TABLE korelasi_maritim")
        df_korelasi = pd.read_csv(CLEAN_KORELASI)
        for _, row in df_korelasi.iterrows():
            cursor.execute("""
                INSERT INTO korelasi_maritim (variabel_1, variabel_2, koefisien_korelasi, interpretasi)
                VALUES (%s, %s, %s, %s)
            """, tuple(row))

        conn.commit()
        cursor.close()
        conn.close()
        print("Semua data (per jam) berhasil dimasukkan/diupdate ke MySQL")

    load_task = PythonOperator(task_id='load_to_mysql', python_callable=load)

    create_tables >> extract_task >> transform_task >> load_task