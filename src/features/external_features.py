"""External features: weather (Open-Meteo API) and Danish holidays."""

import os
import logging
from pathlib import Path

import pandas as pd
import numpy as np
import requests
import holidays as holidays_lib

logger = logging.getLogger(__name__)

# Cache directory for weather data
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "cache"


def fetch_weather_data(start_date: str, end_date: str,
                       latitude: float = 55.68, longitude: float = 12.57,
                       use_cache: bool = True) -> pd.DataFrame:
    """Fetch daily weather data from Open-Meteo Archive API.

    Args:
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        latitude: Latitude (default: Copenhagen).
        longitude: Longitude (default: Copenhagen).
        use_cache: Whether to cache/use cached data.

    Returns:
        DataFrame with columns: date, temperature_max, temperature_min,
        precipitation_mm, is_rainy
    """
    cache_file = CACHE_DIR / f"weather_{start_date}_{end_date}.csv"

    if use_cache and cache_file.exists():
        logger.info(f"Loading cached weather data from {cache_file}")
        df = pd.read_csv(cache_file, parse_dates=["date"])
        return df

    logger.info(f"Fetching weather data from Open-Meteo: {start_date} to {end_date}")

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "Europe/Copenhagen",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        daily = data.get("daily", {})
        df = pd.DataFrame({
            "date": pd.to_datetime(daily["time"]),
            "temperature_max": daily.get("temperature_2m_max"),
            "temperature_min": daily.get("temperature_2m_min"),
            "precipitation_mm": daily.get("precipitation_sum"),
        })

        df["is_rainy"] = (df["precipitation_mm"] > 1.0).astype(int)

        # Cache the result
        if use_cache:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            df.to_csv(cache_file, index=False)
            logger.info(f"Cached weather data to {cache_file}")

        return df

    except requests.RequestException as e:
        logger.warning(f"Failed to fetch weather data: {e}. Returning empty DataFrame.")
        return pd.DataFrame(columns=["date", "temperature_max", "temperature_min",
                                      "precipitation_mm", "is_rainy"])


def add_weather_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Add weather features to the DataFrame.

    Args:
        df: DataFrame with a date column.
        date_col: Name of the date column.

    Returns:
        DataFrame with weather columns merged in.
    """
    dates = pd.to_datetime(df[date_col])
    start_date = dates.min().strftime("%Y-%m-%d")
    end_date = dates.max().strftime("%Y-%m-%d")

    weather = fetch_weather_data(start_date, end_date)

    if weather.empty:
        df["temperature_max"] = np.nan
        df["temperature_min"] = np.nan
        df["precipitation_mm"] = np.nan
        df["is_rainy"] = 0
        return df

    weather["date"] = pd.to_datetime(weather["date"]).dt.date
    df["_merge_date"] = pd.to_datetime(df[date_col]).dt.date

    df = df.merge(weather, left_on="_merge_date", right_on="date",
                  how="left", suffixes=("", "_weather"))
    df = df.drop(columns=["_merge_date", "date_weather"], errors="ignore")

    logger.info("Added weather features")
    return df


def get_danish_holidays(start_year: int, end_year: int) -> pd.DataFrame:
    """Get Danish holidays for a range of years.

    Args:
        start_year: First year.
        end_year: Last year (inclusive).

    Returns:
        DataFrame with columns: date, holiday_name
    """
    dk_holidays = {}
    for year in range(start_year, end_year + 1):
        dk_holidays.update(holidays_lib.Denmark(years=year))

    df = pd.DataFrame(
        [(date, name) for date, name in sorted(dk_holidays.items())],
        columns=["date", "holiday_name"]
    )
    df["date"] = pd.to_datetime(df["date"])
    return df


def add_holiday_features(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Add Danish holiday features to the DataFrame.

    Args:
        df: DataFrame with a date column.
        date_col: Name of the date column.

    Returns:
        DataFrame with holiday columns added.
    """
    dates = pd.to_datetime(df[date_col])
    start_year = dates.min().year
    end_year = dates.max().year

    holidays_df = get_danish_holidays(start_year, end_year)
    holiday_dates = set(holidays_df["date"].dt.date)

    df_dates = dates.dt.date

    df["is_holiday"] = df_dates.isin(holiday_dates).astype(int)
    df["is_day_before_holiday"] = df_dates.map(
        lambda d: (pd.Timestamp(d) + pd.Timedelta(days=1)).date() in holiday_dates
    ).astype(int)
    df["is_day_after_holiday"] = df_dates.map(
        lambda d: (pd.Timestamp(d) - pd.Timedelta(days=1)).date() in holiday_dates
    ).astype(int)

    # Map holiday names
    holiday_map = dict(zip(holidays_df["date"].dt.date, holidays_df["holiday_name"]))
    df["holiday_name"] = df_dates.map(lambda d: holiday_map.get(d, ""))

    logger.info(f"Added holiday features ({len(holiday_dates)} holidays found)")
    return df
