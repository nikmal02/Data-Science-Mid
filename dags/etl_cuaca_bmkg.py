from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as MySqlOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import requests
import pandas as pd
import mysql.connector
import json

ADM4_CODE = "31.71.03.1001"  # Kelurahan Kemayoran, Jakarta Pusat — sudah pasti valid

RAW_PATH = "/usr/local/airflow/dags/data/cuaca_raw.json"
CLEAN_PATH = "/usr/local/airflow/dags/data/cuaca_clean.csv"

default_args = {
    'owner': 'airflow',
    'start_date': datetime.now() - timedelta(days=1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='etl_cuaca_bmkg',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['etl', 'bmkg', 'cuaca', 'mysql'],
) as dag:

    create_table = MySqlOperator(
        task_id='create_table_mysql',
        conn_id='mysql-local',
        sql="""
        CREATE TABLE IF NOT EXISTS cuaca_wilayah (
            id INT AUTO_INCREMENT PRIMARY KEY,
            desa VARCHAR(100),
            kecamatan VARCHAR(100),
            kotkab VARCHAR(100),
            provinsi VARCHAR(100),
            waktu_lokal DATETIME,
            suhu_c DECIMAL(4,1),
            kategori_suhu VARCHAR(20),
            kelembaban_persen DECIMAL(5,1),
            kondisi_cuaca VARCHAR(100),
            kecepatan_angin_kmh DECIMAL(5,1),
            arah_angin VARCHAR(10),
            tutupan_awan_persen DECIMAL(5,1)
        );
        """,
    )

    def extract(**kwargs):
        url = f"https://api.bmkg.go.id/publik/prakiraan-cuaca?adm4={ADM4_CODE}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with open(RAW_PATH, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"Data mentah disimpan ke {RAW_PATH}")

    extract_task = PythonOperator(task_id='extract', python_callable=extract)

    def transform(**kwargs):
        with open(RAW_PATH, "r", encoding="utf-8") as f:
            raw = json.load(f)

        lokasi = raw["lokasi"]
        rows = []
        for hari in raw["data"][0]["cuaca"]:
            for slot in hari:
                rows.append(slot)

        df = pd.DataFrame(rows)

        # --- PREPROCESSING ---
        df["waktu_lokal"] = pd.to_datetime(df["local_datetime"])
        df["suhu_c"] = df["t"].astype(float)
        df["kelembaban_persen"] = df["hu"].astype(float)
        df["kondisi_cuaca"] = df["weather_desc"].astype(str).str.strip()
        df["kecepatan_angin_kmh"] = df["ws"].astype(float)
        df["arah_angin"] = df["wd"].astype(str).str.strip()
        df["tutupan_awan_persen"] = df["tcc"].astype(float)

        def kategori_suhu(t):
            if t < 24:
                return "Sejuk"
            elif t < 30:
                return "Normal"
            else:
                return "Panas"
        df["kategori_suhu"] = df["suhu_c"].apply(kategori_suhu)

        df["desa"] = lokasi.get("desa", "")
        df["kecamatan"] = lokasi.get("kecamatan", "")
        df["kotkab"] = lokasi.get("kotkab", "")
        df["provinsi"] = lokasi.get("provinsi", "")

        df = df.drop_duplicates(subset=["waktu_lokal"]).sort_values("waktu_lokal")

        final_df = df[[
            "desa", "kecamatan", "kotkab", "provinsi",
            "waktu_lokal", "suhu_c", "kategori_suhu",
            "kelembaban_persen", "kondisi_cuaca",
            "kecepatan_angin_kmh", "arah_angin", "tutupan_awan_persen"
        ]]

        final_df.to_csv(CLEAN_PATH, index=False)
        print(f"Data bersih disimpan, total {len(final_df)} baris")

    transform_task = PythonOperator(task_id='transform', python_callable=transform)

    def load(**kwargs):
        mysql_conn = BaseHook.get_connection('mysql-local')
        conn = mysql.connector.connect(
            host=mysql_conn.host,
            user=mysql_conn.login,
            password=mysql_conn.password,
            database=mysql_conn.schema
        )
        cursor = conn.cursor()
        df = pd.read_csv(CLEAN_PATH)
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO cuaca_wilayah
                (desa, kecamatan, kotkab, provinsi, waktu_lokal, suhu_c, kategori_suhu,
                 kelembaban_persen, kondisi_cuaca, kecepatan_angin_kmh, arah_angin, tutupan_awan_persen)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, tuple(row))
        conn.commit()
        cursor.close()
        conn.close()
        print("Data cuaca berhasil dimasukkan ke MySQL!")

    load_task = PythonOperator(task_id='load_to_mysql', python_callable=load)

    create_table >> extract_task >> transform_task >> load_task