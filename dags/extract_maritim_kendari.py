from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as MySqlOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta, date
import requests
import pandas as pd
import mysql.connector
import json

LAT, LON = -3.9700, 122.6100
JUMLAH_HARI_KEBELAKANG = 365
UKURAN_CHUNK = 90  # trik teknis saja, hasil akhir tetap digabung jadi 1 rentang utuh

RAW_ANGIN_JSON = "/usr/local/airflow/dags/data/raw_angin.json"
RAW_GELOMBANG_JSON = "/usr/local/airflow/dags/data/raw_gelombang.json"
RAW_ARUS_JSON = "/usr/local/airflow/dags/data/raw_arus.json"
CSV_ANGIN = "/usr/local/airflow/dags/data/raw_angin.csv"
CSV_GELOMBANG = "/usr/local/airflow/dags/data/raw_gelombang.csv"
CSV_ARUS = "/usr/local/airflow/dags/data/raw_arus.csv"

default_args = {
    'owner': 'airflow',
    'start_date': datetime(2026, 9, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='extract_maritim_kendari',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['extract', 'maritim', 'raw', 'mysql'],
) as dag:

    # Tabel RAW — sengaja TIDAK ada UNIQUE constraint / cleaning apapun.
    # Biarkan NULL, duplikat, dsb masuk apa adanya, supaya bisa dianalisis di notebook.
    create_tables = MySqlOperator(
        task_id='create_tables_mysql',
        conn_id='mysql-local',
        sql="""
        CREATE TABLE IF NOT EXISTS raw_angin (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanggal VARCHAR(20),
            kecepatan_angin_kmh FLOAT,
            arah_angin_derajat FLOAT
        );
        CREATE TABLE IF NOT EXISTS raw_gelombang (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanggal VARCHAR(20),
            tinggi_gelombang_m FLOAT,
            periode_gelombang_detik FLOAT,
            arah_gelombang_derajat FLOAT
        );
        CREATE TABLE IF NOT EXISTS raw_arus (
            id INT AUTO_INCREMENT PRIMARY KEY,
            tanggal VARCHAR(20),
            kecepatan_arus_kmh FLOAT,
            arah_arus_derajat FLOAT
        );
        """,
    )

    def tarik_chunk(url_template, timeout=90):
        """Helper: tarik data per-chunk 90 harian, gabung jadi 1 dict utuh."""
        hasil_gabungan = None
        awal = date.today() - timedelta(days=JUMLAH_HARI_KEBELAKANG)
        akhir_total = date.today()

        while awal < akhir_total:
            akhir_chunk = min(awal + timedelta(days=UKURAN_CHUNK), akhir_total)
            url = url_template.format(mulai=awal.isoformat(), akhir=akhir_chunk.isoformat())
            print(f"Menarik chunk: {awal.isoformat()} s/d {akhir_chunk.isoformat()}")

            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            chunk_json = r.json()

            if hasil_gabungan is None:
                hasil_gabungan = chunk_json
            else:
                for key in hasil_gabungan.get("daily", {}):
                    hasil_gabungan["daily"][key].extend(chunk_json["daily"][key])
                for key in hasil_gabungan.get("hourly", {}):
                    hasil_gabungan["hourly"][key].extend(chunk_json["hourly"][key])

            awal = akhir_chunk + timedelta(days=1)

        return hasil_gabungan

    def extract(**kwargs):
        # 1. ANGIN (daily) — digabung jadi 1 rentang 365 hari utuh
        template_angin = (
            f"https://archive-api.open-meteo.com/v1/archive?latitude={LAT}&longitude={LON}"
            f"&daily=windspeed_10m_max,winddirection_10m_dominant"
            f"&start_date={{mulai}}&end_date={{akhir}}&timezone=auto"
        )
        hasil_angin = tarik_chunk(template_angin)
        with open(RAW_ANGIN_JSON, "w") as f:
            json.dump(hasil_angin, f)
        print(f"Angin: {len(hasil_angin['daily']['time'])} baris (gabungan seluruh chunk)")

        # 2. GELOMBANG (daily) — digabung jadi 1 rentang 365 hari utuh
        template_gelombang = (
            f"https://marine-api.open-meteo.com/v1/marine?latitude={LAT}&longitude={LON}"
            f"&daily=wave_height_max,wave_period_max,wave_direction_dominant"
            f"&cell_selection=sea&start_date={{mulai}}&end_date={{akhir}}&timezone=auto"
        )
        hasil_gelombang = tarik_chunk(template_gelombang)
        with open(RAW_GELOMBANG_JSON, "w") as f:
            json.dump(hasil_gelombang, f)
        print(f"Gelombang: {len(hasil_gelombang['daily']['time'])} baris (gabungan seluruh chunk)")

        # 3. ARUS (hourly) — digabung jadi 1 rentang 365 hari utuh
        template_arus = (
            f"https://marine-api.open-meteo.com/v1/marine?latitude={LAT}&longitude={LON}"
            f"&hourly=ocean_current_velocity,ocean_current_direction"
            f"&cell_selection=sea&start_date={{mulai}}&end_date={{akhir}}&timezone=auto"
        )
        hasil_arus = tarik_chunk(template_arus)
        with open(RAW_ARUS_JSON, "w") as f:
            json.dump(hasil_arus, f)
        print(f"Arus: {len(hasil_arus['hourly']['time'])} baris jam (gabungan seluruh chunk)")

    extract_task = PythonOperator(task_id='extract', python_callable=extract)

    def simpan_csv(**kwargs):
        """Cuma konversi JSON gabungan -> CSV, TANPA cleaning apapun (tidak dropna, tidak dedup)."""
        with open(RAW_ANGIN_JSON) as f:
            angin_json = json.load(f)
        df_angin = pd.DataFrame({
            "tanggal": angin_json["daily"]["time"],
            "kecepatan_angin_kmh": angin_json["daily"]["windspeed_10m_max"],
            "arah_angin_derajat": angin_json["daily"]["winddirection_10m_dominant"],
        })
        df_angin.to_csv(CSV_ANGIN, index=False)

        with open(RAW_GELOMBANG_JSON) as f:
            gelombang_json = json.load(f)
        df_gelombang = pd.DataFrame({
            "tanggal": gelombang_json["daily"]["time"],
            "tinggi_gelombang_m": gelombang_json["daily"]["wave_height_max"],
            "periode_gelombang_detik": gelombang_json["daily"]["wave_period_max"],
            "arah_gelombang_derajat": gelombang_json["daily"]["wave_direction_dominant"],
        })
        df_gelombang.to_csv(CSV_GELOMBANG, index=False)

        # Arus tetap disimpan per JAM (mentah), belum diagregasi ke harian —
        # agregasi itu nanti PROSES CLEANING yang dilakukan di notebook, bukan di sini
        with open(RAW_ARUS_JSON) as f:
            arus_json = json.load(f)
        df_arus = pd.DataFrame({
            "tanggal": arus_json["hourly"]["time"],
            "kecepatan_arus_kmh": arus_json["hourly"]["ocean_current_velocity"],
            "arah_arus_derajat": arus_json["hourly"]["ocean_current_direction"],
        })
        df_arus.to_csv(CSV_ARUS, index=False)

        print(f"CSV mentah disimpan: angin={len(df_angin)}, gelombang={len(df_gelombang)}, arus={len(df_arus)}")

    simpan_csv_task = PythonOperator(task_id='simpan_csv', python_callable=simpan_csv)

    def load(**kwargs):
        mysql_conn = BaseHook.get_connection('mysql-local')
        conn = mysql.connector.connect(
            host=mysql_conn.host, user=mysql_conn.login,
            password=mysql_conn.password, database=mysql_conn.schema
        )
        cursor = conn.cursor()

        # TRUNCATE dulu supaya tidak numpuk tiap kali DAG di-trigger ulang
        # (datanya sendiri TETAP mentah/belum dibersihkan, cuma menghindari duplikasi run)
        cursor.execute("TRUNCATE TABLE raw_angin")
        cursor.execute("TRUNCATE TABLE raw_gelombang")
        cursor.execute("TRUNCATE TABLE raw_arus")

        df_angin = pd.read_csv(CSV_ANGIN)
        cursor.executemany(
            "INSERT INTO raw_angin (tanggal, kecepatan_angin_kmh, arah_angin_derajat) VALUES (%s, %s, %s)",
            [tuple(row) for row in df_angin.itertuples(index=False)]
        )

        df_gelombang = pd.read_csv(CSV_GELOMBANG)
        cursor.executemany(
            "INSERT INTO raw_gelombang (tanggal, tinggi_gelombang_m, periode_gelombang_detik, arah_gelombang_derajat) VALUES (%s, %s, %s, %s)",
            [tuple(row) for row in df_gelombang.itertuples(index=False)]
        )

        df_arus = pd.read_csv(CSV_ARUS)
        cursor.executemany(
            "INSERT INTO raw_arus (tanggal, kecepatan_arus_kmh, arah_arus_derajat) VALUES (%s, %s, %s)",
            [tuple(row) for row in df_arus.itertuples(index=False)]
        )

        conn.commit()
        cursor.close()
        conn.close()
        print("Data MENTAH (belum di-cleaning) berhasil disimpan ke MySQL")

    load_task = PythonOperator(task_id='load_to_mysql', python_callable=load)

    create_tables >> extract_task >> simpan_csv_task >> load_task