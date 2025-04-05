import requests
import json
import psycopg2
from datetime import datetime
from datetime import datetime as dt, date

# Database connection details
DB_NAME = "Adhan_db"
DB_USER = "postgres"
DB_PASSWORD = "postgres"
DB_HOST = "localhost"      # Change if hosted remotely
DB_PORT = "5432"           # Default PostgreSQL port

# Connect to PostgreSQL
try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        options="-c client_encoding=UTF8"
    )
    cur = conn.cursor()
    print("✅ Database connected successfully!")
except Exception as e:
    print(f"❌ Error connecting to the database: {e}")
    exit(1)

# API endpoints
CodeCities_API = "https://habous-prayer-times-api.onrender.com/api/v1/available-cities"
AdhanTime_API = "https://habous-prayer-times-api.onrender.com/api/v1/prayer-times?cityId={}"

#############################################
# RAW LAYER: Cities
#############################################
def fetch_CitiesCodes():
    """Fetch city data from API and remove the last city (if needed)"""
    response = requests.get(CodeCities_API)
    if response.status_code == 200:
        cities = response.json()
        if 'cities' in cities:
            cities['cities'].pop()  # Remove the last city if it’s not needed
            return cities
        else:
            print("❌ 'cities' key not found in the API response.")
            return None
    else:
        print("❌ Fetching Code Cities failed", response.status_code)
        return None

def insert_city(city_id, arabic_name, french_name):
    """Insert a single city into the raw.cities table"""
    sql = """
    INSERT INTO raw.cities (city_id, arabic_name, french_name)
    VALUES (%s, %s, %s)
    ON CONFLICT (city_id) DO NOTHING;
    """
    try:
        cur.execute(sql, (city_id, arabic_name, french_name))
        conn.commit()
    except Exception as e:
        print(f"❌ Error inserting city {city_id}: {e}")

#############################################
# RAW LAYER: Prayer Times
#############################################
def fetch_prayer_times(city_id):
    """Fetch the raw prayer times JSON for a given city_id"""
    response = requests.get(AdhanTime_API.format(city_id))
    if response.status_code == 200:
        data = response.json()
        # Uncomment the following line to see the raw JSON
        # print(json.dumps(data, indent=4, ensure_ascii=False))
        return data  # Return the full JSON response
    else:
        print(f"❌ Failed to fetch prayer times for city_id {city_id}: {response.status_code}")
        return None

def insert_raw_prayer_times(city_id, json_data):
    """Insert the raw prayer times JSON into raw.prayer_times"""
    sql = """
    INSERT INTO raw.prayer_times (city_id, timings)
    VALUES (%s, %s)
    ON CONFLICT DO NOTHING;
    """
    try:
        cur.execute(sql, (city_id, json.dumps(json_data)))
        conn.commit()
        print(f"✅ Raw prayer times inserted for city_id {city_id}.")
    except Exception as e:
        print(f"❌ Error inserting raw prayer times for city_id {city_id}: {e}")

#############################################
# REFINED LAYER: Prayer Times Details
#############################################
def insert_prayer_times_details(city_id, json_data):
    """
    Transform the raw JSON from raw.prayer_times into daily records
    and insert each timing record into refined.prayer_times_details.
    """
    sql = """
    INSERT INTO refined.prayer_times_details (
        gregorian_date, hijri_date, city_id, fajr, sunrise, dhuhr, asr, maghrib, ishaa
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (gregorian_date, city_id) DO NOTHING;
    """
    
    timings = json_data.get("data", {}).get("timings", [])
    if not timings:
        print("❌ No timings data found in JSON for city_id", city_id)
        return

    for timing in timings:
        try:
            # Extract date info
            date_info = timing["date"]
            # Convert formatted date string to a DATE type (adjust the format if needed)
            gregorian_date = datetime.strptime(date_info["formatedDate"], "%d-%b-%Y").date()
            # Build a hijri date string (if needed, you can format it differently)
            hijri_date = f"{date_info['hijri']['day']} {date_info['hijri']['month']} {date_info['hijri']['year']}"
            
            prayers = timing["prayers"]
            fajr = prayers["fajr"]
            sunrise = prayers["sunrise"]
            dhuhr = prayers["dhuhr"]
            asr = prayers["asr"]
            maghrib = prayers["maghrib"]
            ishaa = prayers["ishaa"]
            
            cur.execute(sql, (
                gregorian_date,
                hijri_date,
                city_id,
                fajr,
                sunrise,
                dhuhr,
                asr,
                maghrib,
                ishaa
            ))
        except Exception as e:
            print(f"❌ Error inserting refined record for city_id {city_id}: {e}")
    
    conn.commit()
    print(f"✅ Refined prayer times details inserted for city_id {city_id}.")

def insert_current_day_details():
    """
    Query refined.prayer_times_details for records matching the current date
    and insert them into refined.prayer_times_details_sub.
    """
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
    try:
        cur.execute(sql_select, (current_date,))
        rows = cur.fetchall()
        for row in rows:
            cur.execute(sql_insert, row)
        conn.commit()
        print(f"✅ Inserted current day prayer times for {current_date} into subtable.")
    except Exception as e:
        print(f"❌ Error inserting current day details: {e}")

#############################################
# MAIN ETL PROCESS
#############################################
# -- Step 1: Insert Cities into raw.cities --
Cities = fetch_CitiesCodes()
if Cities:
    for city in Cities['cities']:
        try:
            city_id = city.get("id")
            arabic_name = city.get("arabicCityName")
            french_name = city.get("frenshCityName")
            if city_id and arabic_name and french_name:
                insert_city(city_id, arabic_name, french_name)
            else:
                print(f"❌ Missing required data for city: {city}")
        except Exception as e:
            print(f"❌ Error processing city: {e}")

# -- Step 2: For each city, fetch raw prayer times and insert into raw.prayer_times --
# Re-fetch all city IDs from raw.cities
cur.execute("SELECT city_id FROM raw.cities;")
city_ids = [row[0] for row in cur.fetchall()]
print("✅ Fetched city IDs:", city_ids)

for city_id in city_ids:
    raw_prayer_json = fetch_prayer_times(city_id)
    if raw_prayer_json:
        # Insert the entire JSON into the raw layer table
        insert_raw_prayer_times(city_id, raw_prayer_json)
        # Then, transform and insert into the refined table
        insert_prayer_times_details(city_id, raw_prayer_json)

insert_current_day_details()
# -- Step 3: Close the Database Connection --
cur.close()
conn.close()
print("✅ Cities and prayer times ETL completed successfully!")
