import psycopg2
from datetime import datetime, timedelta

def get_prayer_times_by_city(user_city):
    # Connect to PostgreSQL
    conn = psycopg2.connect(
        dbname='Adhan_db',
        user='postgres',
        password='postgres',
        host='localhost',
        port='5432'
    )
    cursor = conn.cursor()

    # For testing, we set a fixed current datetime: 2025-04-09 04:29:00
    now = datetime(2025, 4, 9, 4, 17, 0)
    CURRENT_DATE = now.date()

    print(f"Testing current datetime: {now}")
    print(f"Testing current date: {CURRENT_DATE}")

    # Fetch city_id from cities using a parameterized query
    querie1 = """
        SELECT city_id 
        FROM raw.cities
        WHERE french_name = %s
    """
    cursor.execute(querie1, (user_city,))
    city_id_result = cursor.fetchone()  # Returns (1,)
    if city_id_result:
        city_id = city_id_result[0]  # Extracts the integer 1 from the tuple
        print(city_id)  # This will print 1

    # Check if a result was returned for the city
    if city_id_result is None:
        print(f"No city found for name: {user_city}")
        cursor.close()
        conn.close()
        return

    # Fetch today’s prayer times for the selected city using a parameterized query
    querie2 = """
        SELECT gregorian_date, fajr, dhuhr, asr, maghrib, ishaa 
        FROM refined.prayer_times_details_sub
        WHERE DATE(gregorian_date) = %s AND city_id = %s
    """
    cursor.execute(querie2, (CURRENT_DATE, city_id))

    prayers = cursor.fetchall()
    print(prayers)

    # Check for alerts
    # Assume that "prayers" returns one row per day per city in the format:
    # (gregorian_date, fajr, dhuhr, asr, maghrib, ishaa)
    if prayers:
        for row in prayers:
            # row[0] is gregorian_date; the actual prayer times start at index 1
            prayer_names = ['fajr', 'dhuhr', 'asr', 'maghrib', 'ishaa']
            for idx, prayer_name in enumerate(prayer_names, start=1):
                prayer_time = row[idx]  # TIME object from DB
                # Create full datetime by combining the fixed current date with the prayer time
                prayer_datetime = datetime.combine(now.date(), prayer_time)
                time_diff = (prayer_datetime - now).total_seconds() / 60

                if 0 < time_diff <= 5:
                    print(f"⏰ ALERT: {prayer_name} prayer in less than 5 minutes!")
                elif 5 < time_diff <= 15:
                    print(f"⏳ REMINDER: {prayer_name} prayer in less than 15 minutes!")
    else:
        print("No prayer times found for today.")

    # Close connection
    cursor.close()
    conn.close()

if __name__ == '__main__':
    # Prompt user for a city name
    user_city = input("Enter the city name: ").strip()
    get_prayer_times_by_city(user_city)
