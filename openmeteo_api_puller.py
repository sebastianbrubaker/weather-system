"""
Docstring for api_data_puller

"""

# Database and data manipulation
import sqlite3
import os
import pandas as pd
from datetime import datetime

# OpenMeteo API
import openmeteo_requests
import requests_cache
from retry_requests import retry


# --- Globals ---
LOCATIONS = {
    'Victoria': (48.4284, -123.3656), 'Oak Bay': (48.4237, -123.3172),
    'Esquimalt': (48.4291, -123.4128), 'Saanich': (48.4590, -123.3722),
    'Royal Oak': (48.5025, -123.3830), 'View Royal': (48.4524, -123.4348),
    'Colwood': (48.4237, -123.5177), 'Langford': (48.4500, -123.5051),
    'Brentwood Bay': (48.5701, -123.4614), 'Central Saanich': (48.5920, -123.4150),
    'Metchosin': (48.3793, -123.5315), 'Sidney': (48.6493, -123.3978),
    'Sooke': (48.3815, -123.7110)
}

os.makedirs('data', exist_ok=True)
DB_PATH = 'data/weather.db'


# --- API call and data formatting ---
 
def openmeteo_api_daily(locations: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """
    Docstring for api_call
    
    :return: Description
    :rtype: DataFrame
    """
    # Default to global
    if locations is None:
        locations = LOCATIONS

    # Setup caching & retry
    cach_path = 'data/api_cache'
    cache_session = requests_cache.CachedSession(cach_path, expire_after=3600) # Fresh for an hour
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Weather API params
    url = 'https://api.open-meteo.com/v1/forecast'
    params = {
        'daily': [
            'weather_code', 'temperature_2m_max', 'temperature_2m_min',
            'rain_sum', 'snowfall_sum', 'showers_sum', 'precipitation_sum',
            'precipitation_probability_max'
        ],
        'timezone': 'America/Los_Angeles',
        'past_days': 1,
        'forecast_days': 16,
    }

    collection_date = datetime.now()

    df_list = []

    # Loop through each area
    for area_name, (lat, lon) in locations.items():
        params['latitude'] = lat
        params['longitude'] = lon

        print(f'Fetching daily data for {area_name}...')
        try:
            responses = openmeteo.weather_api(url, params=params)
            daily = responses[0].Daily()
        except Exception as e:
            print(f'API pull failed for {area_name}: {e}')
            continue

        # Build dataframe
        df = pd.DataFrame({
            'date': pd.date_range(
                start=pd.to_datetime(daily.Time(), unit='s', utc=True),
                end=pd.to_datetime(daily.TimeEnd(), unit='s', utc=True),
                freq=pd.Timedelta(seconds=daily.Interval()),
                inclusive='left'
            ).tz_localize(None).strftime('%Y-%m-%d'),
            'area': area_name,
            'weather_code': daily.Variables(0).ValuesAsNumpy(),
            'high_temp': daily.Variables(1).ValuesAsNumpy(),
            'low_temp': daily.Variables(2).ValuesAsNumpy(),
            'rain_mm': daily.Variables(3).ValuesAsNumpy(),
            'snow_mm': daily.Variables(4).ValuesAsNumpy(),
            'showers_mm': daily.Variables(5).ValuesAsNumpy(),
            'precipitation_mm': daily.Variables(6).ValuesAsNumpy(),
            'precipitation_percent': daily.Variables(7).ValuesAsNumpy(),
            'lat': lat,
            'lon': lon,
            'collection_date': collection_date.strftime('%Y-%m-%d'),
        })

        df_list.append(df)

        print(f'✓ Completed {area_name}')
    
    return pd.concat(df_list, ignore_index=True)


def openmeteo_api_hourly(locations: dict[str, tuple[float, float]]) -> pd.DataFrame:
    """
    Docstring for api_call
    
    :return: Description
    :rtype: DataFrame
    """
    # Default to global
    if locations is None:
        locations = LOCATIONS

    # Setup caching & retry
    cach_path = 'data/api_cache'
    cache_session = requests_cache.CachedSession(cach_path, expire_after=3600) # Fresh for an hour
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # Weather API params
    url = 'https://api.open-meteo.com/v1/forecast'
    params = {
        'hourly': ['temperature_2m', 'dew_point_2m'],
        'timezone': 'America/Los_Angeles',
        'past_days': 1,
        'forecast_days': 16,
    }

    collection_date = datetime.now()

    df_list = []

    # Loop through each area
    for area_name, (lat, lon) in locations.items():
        params['latitude'] = lat
        params['longitude'] = lon

        print(f'Fetching hourly data for {area_name}...')
        try:
            responses = openmeteo.weather_api(url, params=params)
            hourly = responses[0].Hourly() 
        except Exception as e:
            print(f'API pull failed for {area_name}: {e}')
            continue

        # Build dataframe
        df = pd.DataFrame({
            'date': pd.date_range(
                start=pd.to_datetime(hourly.Time(), unit='s', utc=True),
                end=pd.to_datetime(hourly.TimeEnd(), unit='s', utc=True),
                freq=pd.Timedelta(seconds=hourly.Interval()),
                inclusive='left'
            ).tz_localize(None).strftime('%Y-%m-%d-%H'),
            'area': area_name,
            'temperature_2m': hourly.Variables(0).ValuesAsNumpy(),
            'dewpoint_2m': hourly.Variables(1).ValuesAsNumpy(),
            'lat': lat,
            'lon': lon,
            'collection_date': collection_date.strftime('%Y-%m-%d-%H'),
        })

        df_list.append(df)

        print(f'✓ Completed {area_name}')
    
    return pd.concat(df_list, ignore_index=True)


# --- Database Operations ---

def df_to_db(df: pd.DataFrame, table: str, db_path: str = DB_PATH) -> None:
    """
    Docstring for df_to_db
    
    :param df: Description
    :type df: pd.DataFrame
    :param table: Description
    :type table: str
    :param db_path: Description
    :type db_path: str
    """
    if table not in {'openmeteo_daily', 'openmeteo_hourly'}:
        raise ValueError(f'Unknown table: {table}')

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # --- Table creation ---
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS openmeteo_daily (
                date TEXT,
                area TEXT,
                lat REAL,
                lon REAL,
                weather_code INTEGER,
                high_temp REAL,
                low_temp REAL,
                rain_mm REAL,
                snow_mm REAL,
                showers_mm REAL,
                precipitation_mm REAL,
                precipitation_percent REAL,
                collection_date TEXT,
                PRIMARY KEY (date, area)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS openmeteo_hourly (
                date TEXT,
                area TEXT,
                lat REAL,
                lon REAL,
                temperature_2m REAL,
                dewpoint_2m REAL,
                collection_date TEXT,
                PRIMARY KEY (date, area)
            )
        """)

        # --- Table-specific inserts ---
        if table == 'openmeteo_daily':
            insert_query = """
                INSERT INTO openmeteo_daily (
                    date, area, lat, lon,
                    weather_code, high_temp, low_temp,
                    rain_mm, snow_mm, showers_mm,
                    precipitation_mm, precipitation_percent,
                    collection_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, area) DO UPDATE SET
                    lat=excluded.lat,
                    lon=excluded.lon,
                    weather_code=excluded.weather_code,
                    high_temp=excluded.high_temp,
                    low_temp=excluded.low_temp,
                    rain_mm=excluded.rain_mm,
                    snow_mm=excluded.snow_mm,
                    showers_mm=excluded.showers_mm,
                    precipitation_mm=excluded.precipitation_mm,
                    precipitation_percent=excluded.precipitation_percent,
                    collection_date=excluded.collection_date;
            """

            cols = [
                'date', 'area', 'lat', 'lon',
                'weather_code', 'high_temp', 'low_temp',
                'rain_mm', 'snow_mm', 'showers_mm',
                'precipitation_mm', 'precipitation_percent',
                'collection_date',
            ]

        else:  # openmeteo_hourly
            insert_query = """
                INSERT INTO openmeteo_hourly (
                    date, area, lat, lon,
                    temperature_2m, dewpoint_2m,
                    collection_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, area) DO UPDATE SET
                    lat=excluded.lat,
                    lon=excluded.lon,
                    temperature_2m=excluded.temperature_2m,
                    dewpoint_2m=excluded.dewpoint_2m,
                    collection_date=excluded.collection_date;
            """

            cols = [
                'date', 'area', 'lat', 'lon',
                'temperature_2m', 'dewpoint_2m',
                'collection_date',
            ]

        cursor.executemany(
            insert_query,
            df[cols].itertuples(index=False, name=None)
        )

        conn.commit()
        print(f'Successfully inserted {len(df)} rows into {table}.')

    except sqlite3.Error as e:
        print(f'Database operation failed: {e}')

    finally:
        conn.close()


def main():
    try:
        df_daily = openmeteo_api_daily(locations=LOCATIONS)
        df_to_db(df_daily, table='openmeteo_daily')

        df_hourly = openmeteo_api_hourly(locations=LOCATIONS)
        df_to_db(df_hourly, table='openmeteo_hourly')

    except Exception as e:
        print(e)

if __name__ == '__main__': main()