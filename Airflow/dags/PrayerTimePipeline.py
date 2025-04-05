from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime, timedelta
import requests
import json
import psycopg2
from datetime import date

# Database connection function
def get_conn_cursor():
    conn = psycopg2.connect(
        dbname="Adhan_db",
        user="postgres",
        password="postgres",
        host="host.docker.internal",  # instead of "localhost"
        port="5432",
        options="-c client_encoding=UTF8"
    )
    return conn, conn.cursor()

# API endpoints
CodeCities_API = "https://habous-prayer-times-api.onrender.com/api/v1/available-cities"
AdhanTime_API = "https://habous-prayer-times-api.onrender.com/api/v1/prayer-times?cityId={}"

# -- ETL FUNCTIONS --
def fetch_and_insert_cities():
    conn, cur = get_conn_cursor()
    response = requests.get(CodeCities_API)
    if response.status_code == 200:
        cities = response.json().get("cities", [])
        if cities:
            cities.pop()
            for city in cities:
                city_id = city.get("id")
                arabic_name = city.get("arabicCityName")
                french_name = city.get("frenshCityName")
                sql = """
                    INSERT INTO raw.cities (city_id, arabic_name, french_name)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (city_id) DO NOTHING;
                """
                cur.execute(sql, (city_id, arabic_name, french_name))
            conn.commit()
    cur.close()
    conn.close()

def fetch_and_insert_raw_prayer_times():
    conn, cur = get_conn_cursor()
    cur.execute("SELECT city_id FROM raw.cities;")
    city_ids = [row[0] for row in cur.fetchall()]
    for city_id in city_ids:
        response = requests.get(AdhanTime_API.format(city_id))
        if response.status_code == 200:
            json_data = response.json()
            sql = """
                INSERT INTO raw.prayer_times (city_id, timings)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING;
            """
            cur.execute(sql, (city_id, json.dumps(json_data)))
    conn.commit()
    cur.close()
    conn.close()

def transform_and_insert_refined():
    conn, cur = get_conn_cursor()
    cur.execute("SELECT city_id FROM raw.cities;")
    city_ids = [row[0] for row in cur.fetchall()]
    for city_id in city_ids:
        response = requests.get(AdhanTime_API.format(city_id))
        if response.status_code != 200:
            continue
        json_data = response.json()
        timings = json_data.get("data", {}).get("timings", [])
        sql = """
        INSERT INTO refined.prayer_times_details (
            gregorian_date, hijri_date, city_id, fajr, sunrise, dhuhr, asr, maghrib, ishaa
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (gregorian_date, city_id) DO NOTHING;
        """
        for timing in timings:
            date_info = timing["date"]
            try:
                gregorian_date = datetime.strptime(date_info["formatedDate"], "%d-%b-%Y").date()
            except:
                continue
            hijri = f"{date_info['hijri']['day']} {date_info['hijri']['month']} {date_info['hijri']['year']}"
            prayers = timing["prayers"]
            cur.execute(sql, (
                gregorian_date, hijri, city_id,
                prayers["fajr"], prayers["sunrise"], prayers["dhuhr"],
                prayers["asr"], prayers["maghrib"], prayers["ishaa"]
            ))
    conn.commit()
    cur.close()
    conn.close()

def insert_current_day_details():
    conn, cur = get_conn_cursor()
    current_date = date.today()
    sql_select = """
        SELECT gregorian_date, hijri_date, city_id, fajr, sunrise, dhuhr, asr, maghrib, ishaa
        FROM refined.prayer_times_details
        WHERE gregorian_date = %s;
    """
    sql_insert = """
        INSERT INTO refined.prayer_times_details_sub (
            gregorian_date, hijri_date, city_id, fajr, sunrise, dhuhr, asr, maghrib, ishaa
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (gregorian_date, city_id) DO NOTHING;
    """
    cur.execute(sql_select, (current_date,))
    rows = cur.fetchall()
    for row in rows:
        cur.execute(sql_insert, row)
    conn.commit()
    cur.close()
    conn.close()

# -- DAG DEFINITIONS --

default_args = {
    'owner': 'airflow',
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# 🔁 WEEKLY DAG
with DAG(
    dag_id='adhan_etl_weekly',
    default_args=default_args,
    description='Weekly ETL DAG for Adhan Data',
    schedule_interval='@weekly',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['adhan', 'weekly']
) as dag_weekly:

    fetch_cities_task = PythonOperator(
        task_id='fetch_and_insert_cities',
        python_callable=fetch_and_insert_cities
    )

    fetch_raw_task = PythonOperator(
        task_id='fetch_and_insert_raw_prayer_times',
        python_callable=fetch_and_insert_raw_prayer_times
    )

    transform_task = PythonOperator(
        task_id='transform_and_insert_refined',
        python_callable=transform_and_insert_refined
    )

    fetch_cities_task >> fetch_raw_task >> transform_task

# 🔁 DAILY DAG
with DAG(
    dag_id='adhan_insert_today_details',
    default_args=default_args,
    description='Daily ETL to insert current day prayer details',
    schedule_interval='@daily',
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['adhan', 'daily']
) as dag_daily:

    insert_today_task = PythonOperator(
        task_id='insert_current_day_details',
        python_callable=insert_current_day_details
    )
