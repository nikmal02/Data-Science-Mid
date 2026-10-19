from airflow import DAG
from airflow.providers.common.sql.operators.sql import SQLExecuteQueryOperator as MySqlOperator
from airflow.operators.python import PythonOperator
from airflow.hooks.base import BaseHook
from datetime import datetime, timedelta
import pandas as pd
import mysql.connector

default_args = {
    'owner': 'airflow',
    'start_date': datetime.now() - timedelta(days=1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    dag_id='etl_stock_to_mysql',
    default_args=default_args,
    schedule=None,
    catchup=False,
    tags=['example', 'mysql', 'etl'],
) as dag:

    create_table = MySqlOperator(
        task_id='create_table_mysql',
        conn_id='mysql-local',
        sql="""
        CREATE TABLE IF NOT EXISTS stock_data (
            id INT AUTO_INCREMENT PRIMARY KEY,
            date DATETIME,
            open_price DECIMAL(10, 2),
            high_price DECIMAL(10, 2),
            low_price DECIMAL(10, 2),
            close_price DECIMAL(10, 2),
            volume BIGINT
        );
        """,
    )

    def extract_transform():
        file_path = "/usr/local/airflow/dags/data/BTC-USD.csv"
        df = pd.read_csv(file_path)
        df['Date'] = pd.to_datetime(df['Date']).dt.tz_localize(None)
        transformed_path = "/usr/local/airflow/dags/data/transformed_stock_data.csv"
        df.to_csv(transformed_path, index=False)
        print(f"Data transformed and saved to {transformed_path}")

    extract_transform_task = PythonOperator(
        task_id='extract_transform',
        python_callable=extract_transform,
    )

    def load_to_mysql():
        mysql_conn = BaseHook.get_connection('mysql-local')
        conn = mysql.connector.connect(
            host=mysql_conn.host,
            user=mysql_conn.login,
            password=mysql_conn.password,
            database=mysql_conn.schema
        )
        cursor = conn.cursor()
        transformed_path = "/usr/local/airflow/dags/data/transformed_stock_data.csv"
        df = pd.read_csv(transformed_path)
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO stock_data (date, open_price, high_price, low_price, close_price, volume)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (row['Date'], row['Open'], row['High'], row['Low'], row['Close'], row['Volume']))
        conn.commit()
        cursor.close()
        conn.close()
        print("Data successfully loaded into MySQL!")

    load_to_mysql_task = PythonOperator(
        task_id='load_to_mysql',
        python_callable=load_to_mysql,
    )

    create_table >> extract_transform_task >> load_to_mysql_task