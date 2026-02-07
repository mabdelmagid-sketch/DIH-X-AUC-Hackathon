"""
Real-time context signals for LLM-based inventory arbitration.

Fetches weather, holidays, daylight, events, and calendar intelligence
so the LLM can decide per-item whether to use a waste-reducing or
stockout-reducing forecasting strategy.

All APIs used are FREE and require NO API keys unless noted.
"""
import calendar
import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Copenhagen coordinates
CPH_LAT = 55.68
CPH_LON = 12.57
CPH_TZ = "Europe/Copenhagen"

# Cache to avoid repeated API calls within the same hour
_cache: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL_SECONDS = 3600  # 1 hour


def _get_cached(key: str) -> Optional[dict]:
    if key in _cache:
        ts, data = _cache[key]
        if (datetime.now() - ts).total_seconds() < _CACHE_TTL_SECONDS:
            return data
    return None


def _set_cached(key: str, data: dict):
    _cache[key] = (datetime.now(), data)


# ---------------------------------------------------------------------------
# 1. WEATHER -- Open-Meteo Forecast API (free, no key)
# ---------------------------------------------------------------------------

async def fetch_weather_forecast(
    target_date: date,
    days_ahead: int = 3,
) -> dict:
    """Fetch weather forecast from Open-Meteo for Copenhagen."""
    cached = _get_cached(f"weather_{target_date}_{days_ahead}")
    if cached:
        return cached

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": CPH_LAT,
        "longitude": CPH_LON,
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min",
            "apparent_temperature_max", "apparent_temperature_min",
            "precipitation_sum", "precipitation_probability_max",
            "weather_code", "wind_gusts_10m_max",
            "sunrise", "sunset", "sunshine_duration",
            "uv_index_max",
        ]),
        "timezone": CPH_TZ,
        "forecast_days": min(days_ahead + 1, 16),
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        daily = data.get("daily", {})
        times = daily.get("time", [])

        # Find the index for target_date
        target_str = target_date.isoformat()
        idx = times.index(target_str) if target_str in times else 0

        result = {
            "temperature_max": daily.get("temperature_2m_max", [None])[idx],
            "temperature_min": daily.get("temperature_2m_min", [None])[idx],
            "feels_like_max": daily.get("apparent_temperature_max", [None])[idx],
            "feels_like_min": daily.get("apparent_temperature_min", [None])[idx],
            "precipitation_mm": daily.get("precipitation_sum", [None])[idx],
            "precipitation_probability": daily.get("precipitation_probability_max", [None])[idx],
            "weather_code": daily.get("weather_code", [None])[idx],
            "wind_gusts_kmh": daily.get("wind_gusts_10m_max", [None])[idx],
            "sunrise": daily.get("sunrise", [None])[idx],
            "sunset": daily.get("sunset", [None])[idx],
            "sunshine_hours": round(
                (daily.get("sunshine_duration", [0])[idx] or 0) / 3600, 1
            ),
            "uv_index_max": daily.get("uv_index_max", [None])[idx],
        }

        # Add human-readable weather description
        result["weather_description"] = _wmo_code_to_text(
            result.get("weather_code")
        )

        # Multi-day outlook summary
        outlook = []
        for i in range(min(len(times), days_ahead + 1)):
            outlook.append({
                "date": times[i],
                "temp_max": daily.get("temperature_2m_max", [None])[i],
                "precip_prob": daily.get("precipitation_probability_max", [None])[i],
                "code": daily.get("weather_code", [None])[i],
            })
        result["outlook"] = outlook

        _set_cached(f"weather_{target_date}_{days_ahead}", result)
        return result

    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return {"error": str(e)}


def _wmo_code_to_text(code: Optional[int]) -> str:
    """Convert WMO weather code to human-readable text."""
    if code is None:
        return "unknown"
    mapping = {
        0: "clear sky", 1: "mainly clear", 2: "partly cloudy",
        3: "overcast", 45: "fog", 48: "depositing rime fog",
        51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
        61: "slight rain", 63: "moderate rain", 65: "heavy rain",
        66: "light freezing rain", 67: "heavy freezing rain",
        71: "slight snow", 73: "moderate snow", 75: "heavy snow",
        77: "snow grains", 80: "slight rain showers",
        81: "moderate rain showers", 82: "violent rain showers",
        85: "slight snow showers", 86: "heavy snow showers",
        95: "thunderstorm", 96: "thunderstorm with slight hail",
        99: "thunderstorm with heavy hail",
    }
    return mapping.get(code, f"code_{code}")


# ---------------------------------------------------------------------------
# 2. AIR QUALITY & POLLEN -- Open-Meteo (free, no key)
# ---------------------------------------------------------------------------

async def fetch_air_quality(target_date: date) -> dict:
    """Fetch air quality and pollen data for Copenhagen."""
    cached = _get_cached(f"aqi_{target_date}")
    if cached:
        return cached

    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": CPH_LAT,
        "longitude": CPH_LON,
        "hourly": "european_aqi,pm10,pm2_5,birch_pollen,grass_pollen",
        "forecast_days": 1,
        "timezone": CPH_TZ,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        hourly = data.get("hourly", {})
        # Take midday reading (index 12) as representative
        idx = min(12, len(hourly.get("european_aqi", [])) - 1)

        result = {
            "european_aqi": hourly.get("european_aqi", [None])[idx],
            "pm10": hourly.get("pm10", [None])[idx],
            "pm2_5": hourly.get("pm2_5", [None])[idx],
            "birch_pollen": hourly.get("birch_pollen", [None])[idx],
            "grass_pollen": hourly.get("grass_pollen", [None])[idx],
        }

        _set_cached(f"aqi_{target_date}", result)
        return result

    except Exception as e:
        logger.warning(f"Air quality fetch failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# 3. SEVERE WEATHER -- MeteoAlarm Denmark feed (free, no key)
# ---------------------------------------------------------------------------

async def fetch_weather_alerts() -> list[dict]:
    """Fetch active severe weather alerts for Denmark from MeteoAlarm."""
    cached = _get_cached("meteoalarm")
    if cached:
        return cached.get("alerts", [])

    url = "https://feeds.meteoalarm.org/api/v1/warnings/feeds-denmark"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        alerts = []
        for entry in data if isinstance(data, list) else data.get("warnings", []):
            alerts.append({
                "event": entry.get("event", "unknown"),
                "severity": entry.get("severity", "unknown"),
                "description": entry.get("description", "")[:200],
            })

        _set_cached("meteoalarm", {"alerts": alerts})
        return alerts

    except Exception as e:
        logger.warning(f"MeteoAlarm fetch failed: {e}. Non-critical.")
        return []


# ---------------------------------------------------------------------------
# 4. HOLIDAYS -- Nager.Date (free, no key) + Python holidays lib
# ---------------------------------------------------------------------------

async def fetch_holiday_info(target_date: date) -> dict:
    """Get holiday context: is_holiday, next holiday, long weekends."""
    cached = _get_cached(f"holidays_{target_date.year}")
    if cached:
        return _process_holiday_data(cached, target_date)

    url = f"https://date.nager.at/api/v3/PublicHolidays/{target_date.year}/DK"
    lw_url = f"https://date.nager.at/api/v3/LongWeekend/{target_date.year}/DK"

    holidays_data = []
    long_weekends = []

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                holidays_data = resp.json()

            lw_resp = await client.get(lw_url)
            if lw_resp.status_code == 200:
                long_weekends = lw_resp.json()

    except Exception as e:
        logger.warning(f"Nager.Date fetch failed: {e}. Falling back to holidays lib.")

    # Fallback: use Python holidays library
    if not holidays_data:
        try:
            import holidays as holidays_lib
            dk = holidays_lib.Denmark(years=target_date.year)
            holidays_data = [
                {"date": d.isoformat(), "localName": n, "name": n}
                for d, n in sorted(dk.items())
            ]
        except ImportError:
            logger.warning("holidays library not installed")

    data = {"holidays": holidays_data, "long_weekends": long_weekends}
    _set_cached(f"holidays_{target_date.year}", data)
    return _process_holiday_data(data, target_date)


def _process_holiday_data(data: dict, target_date: date) -> dict:
    """Process raw holiday data into context signals."""
    holidays_list = data.get("holidays", [])
    long_weekends = data.get("long_weekends", [])

    target_str = target_date.isoformat()
    is_holiday = False
    holiday_name = ""
    next_holiday = None
    days_to_next = None

    for h in holidays_list:
        h_date = h.get("date", "")
        h_name = h.get("localName", h.get("name", ""))

        if h_date == target_str:
            is_holiday = True
            holiday_name = h_name

        if h_date > target_str and next_holiday is None:
            next_holiday = h_name
            days_to_next = (date.fromisoformat(h_date) - target_date).days

    # Check day before/after holiday
    tomorrow = (target_date + timedelta(days=1)).isoformat()
    yesterday = (target_date - timedelta(days=1)).isoformat()
    is_day_before = any(h.get("date") == tomorrow for h in holidays_list)
    is_day_after = any(h.get("date") == yesterday for h in holidays_list)

    # Long weekend detection
    is_long_weekend = False
    for lw in long_weekends:
        start = lw.get("startDate", "")
        end = lw.get("endDate", "")
        if start and end and start <= target_str <= end:
            is_long_weekend = True
            break

    # Check if approaching a long weekend (within 3 days)
    long_weekend_approaching = False
    for lw in long_weekends:
        start = lw.get("startDate", "")
        if start:
            days_until = (date.fromisoformat(start) - target_date).days
            if 0 < days_until <= 3:
                long_weekend_approaching = True
                break

    return {
        "is_holiday": is_holiday,
        "holiday_name": holiday_name,
        "is_day_before_holiday": is_day_before,
        "is_day_after_holiday": is_day_after,
        "next_holiday": next_holiday,
        "days_to_next_holiday": days_to_next,
        "is_long_weekend": is_long_weekend,
        "long_weekend_approaching": long_weekend_approaching,
    }


# ---------------------------------------------------------------------------
# 5. DAYLIGHT -- Python astral (offline, no API)
# ---------------------------------------------------------------------------

def get_daylight_info(target_date: date) -> dict:
    """Compute sunrise/sunset/daylight for Copenhagen using astral."""
    try:
        from astral import LocationInfo
        from astral.sun import sun

        cph = LocationInfo("Copenhagen", "Denmark", CPH_TZ, CPH_LAT, CPH_LON)
        s = sun(cph.observer, date=target_date, tzinfo=CPH_TZ)

        sunrise = s["sunrise"]
        sunset = s["sunset"]
        daylight = sunset - sunrise
        daylight_hours = round(daylight.total_seconds() / 3600, 1)

        # Compare to yesterday to see if days are getting longer
        yesterday = sun(cph.observer, date=target_date - timedelta(days=1), tzinfo=CPH_TZ)
        yesterday_daylight = (yesterday["sunset"] - yesterday["sunrise"]).total_seconds()
        gaining_daylight = daylight.total_seconds() > yesterday_daylight

        return {
            "sunrise": sunrise.strftime("%H:%M"),
            "sunset": sunset.strftime("%H:%M"),
            "daylight_hours": daylight_hours,
            "is_gaining_daylight": gaining_daylight,
        }

    except ImportError:
        logger.warning("astral library not installed. Skipping daylight signals.")
        return {}
    except Exception as e:
        logger.warning(f"Daylight calculation failed: {e}")
        return {}


# ---------------------------------------------------------------------------
# 6. BUSINESS DAYS & PAYDAY -- Python workalendar (offline)
# ---------------------------------------------------------------------------

def get_business_day_info(target_date: date) -> dict:
    """Compute business day signals and Danish payday proximity."""
    try:
        from workalendar.europe import Denmark
        cal = Denmark()
    except ImportError:
        logger.warning("workalendar not installed. Using basic weekday logic.")
        is_working = target_date.weekday() < 5
        return {
            "is_business_day": is_working,
            "days_since_payday": None,
            "days_to_payday": None,
            "is_payday_week": False,
        }

    is_working = cal.is_working_day(target_date)

    # Danish payday: last business day of the month
    last_day_of_month = calendar.monthrange(target_date.year, target_date.month)[1]
    payday = date(target_date.year, target_date.month, last_day_of_month)
    while not cal.is_working_day(payday):
        payday -= timedelta(days=1)

    if target_date <= payday:
        days_to_payday = (payday - target_date).days
        # Get last month's payday for days_since
        if target_date.month == 1:
            prev_last = calendar.monthrange(target_date.year - 1, 12)[1]
            prev_payday = date(target_date.year - 1, 12, prev_last)
        else:
            prev_last = calendar.monthrange(target_date.year, target_date.month - 1)[1]
            prev_payday = date(target_date.year, target_date.month - 1, prev_last)
        while not cal.is_working_day(prev_payday):
            prev_payday -= timedelta(days=1)
        days_since_payday = (target_date - prev_payday).days
    else:
        days_since_payday = (target_date - payday).days
        # Next month's payday
        if target_date.month == 12:
            next_last = calendar.monthrange(target_date.year + 1, 1)[1]
            next_payday = date(target_date.year + 1, 1, next_last)
        else:
            next_last = calendar.monthrange(target_date.year, target_date.month + 1)[1]
            next_payday = date(target_date.year, target_date.month + 1, next_last)
        while not cal.is_working_day(next_payday):
            next_payday -= timedelta(days=1)
        days_to_payday = (next_payday - target_date).days

    return {
        "is_business_day": is_working,
        "days_since_payday": days_since_payday,
        "days_to_payday": days_to_payday,
        "is_payday_week": days_to_payday <= 2 or days_since_payday <= 2,
    }


# ---------------------------------------------------------------------------
# 7. DANISH RETAIL CALENDAR -- Computed locally
# ---------------------------------------------------------------------------

def get_danish_retail_signals(target_date: date) -> dict:
    """Compute Danish-specific retail and cultural signals."""
    d = target_date

    # Easter calculation (Anonymous Gregorian algorithm)
    def _easter(year: int) -> date:
        a = year % 19
        b, c = divmod(year, 100)
        d_, e = divmod(b, 4)
        f = (b + 8) // 25
        g = (b - f + 1) // 3
        h = (19 * a + b - d_ - g + 15) % 30
        i, k = divmod(c, 4)
        l_ = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l_) // 451
        month = (h + l_ - 7 * m + 114) // 31
        day = ((h + l_ - 7 * m + 114) % 31) + 1
        return date(year, month, day)

    easter = _easter(d.year)
    fastelavn = easter - timedelta(days=49)  # 7 weeks before Easter

    # J-dag: first Friday in November
    nov1 = date(d.year, 11, 1)
    j_dag = nov1 + timedelta(days=(4 - nov1.weekday()) % 7)

    # Sankt Hans: June 23
    sankt_hans = date(d.year, 6, 23)

    days_to_christmas = (date(d.year, 12, 24) - d).days
    if days_to_christmas < 0:
        days_to_christmas = (date(d.year + 1, 12, 24) - d).days

    # School holidays (Copenhagen standard pattern)
    week_num = d.isocalendar()[1]
    is_school_holiday = (
        week_num == 42  # Autumn break
        or (d.month == 12 and d.day >= 23) or (d.month == 1 and d.day <= 4)  # Christmas
        or week_num in (7, 8)  # Winter break
        or (easter - timedelta(days=3) <= d <= easter + timedelta(days=5))  # Easter
        or (d.month in (7,) or (d.month == 6 and d.day >= 28) or (d.month == 8 and d.day <= 10))  # Summer
    )

    return {
        "is_fastelavn": d == fastelavn,
        "is_sankt_hans": d == sankt_hans,
        "is_j_dag": d == j_dag,
        "is_julefrokost_season": d.month in (11, 12) and d.day <= 23,
        "is_christmas_season": d.month == 12 and d.day <= 24,
        "days_to_christmas": days_to_christmas,
        "is_new_years_eve": d.month == 12 and d.day == 31,
        "is_grilling_season": d.month in (5, 6, 7, 8),
        "is_school_holiday": is_school_holiday,
        "is_black_friday": (
            d.month == 11 and d.weekday() == 4 and 22 <= d.day <= 28
        ),
        "season": {
            12: "winter", 1: "winter", 2: "winter",
            3: "spring", 4: "spring", 5: "spring",
            6: "summer", 7: "summer", 8: "summer",
            9: "autumn", 10: "autumn", 11: "autumn",
        }[d.month],
    }


# ---------------------------------------------------------------------------
# 8. CALENDAR BASICS -- Computed locally
# ---------------------------------------------------------------------------

def get_calendar_signals(target_date: date) -> dict:
    """Basic calendar signals."""
    d = target_date
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday",
                 "Friday", "Saturday", "Sunday"]
    last_day = calendar.monthrange(d.year, d.month)[1]

    return {
        "date": d.isoformat(),
        "day_of_week": day_names[d.weekday()],
        "day_of_week_num": d.isoweekday(),
        "is_weekend": d.weekday() >= 5,
        "is_friday": d.weekday() == 4,
        "is_monday": d.weekday() == 0,
        "week_number": d.isocalendar()[1],
        "month": d.month,
        "day_of_month": d.day,
        "is_month_start": d.day <= 3,
        "is_month_end": d.day >= last_day - 2,
    }


# ---------------------------------------------------------------------------
# ORCHESTRATOR -- Combines all signals into one JSON response
# ---------------------------------------------------------------------------

async def get_all_context_signals(
    target_date: Optional[date] = None,
    days_ahead: int = 3,
) -> dict:
    """
    Master function: fetches all context signals for the LLM.

    Returns a single dict the LLM uses to decide per-item whether to
    apply waste-reducing or stockout-reducing forecasting.
    """
    if target_date is None:
        target_date = date.today()

    # Parallel-safe: fire off async calls, compute sync ones immediately
    weather = await fetch_weather_forecast(target_date, days_ahead)
    air_quality = await fetch_air_quality(target_date)
    holiday_info = await fetch_holiday_info(target_date)
    alerts = await fetch_weather_alerts()

    daylight = get_daylight_info(target_date)
    business = get_business_day_info(target_date)
    danish_retail = get_danish_retail_signals(target_date)
    cal = get_calendar_signals(target_date)

    # Build the unified context
    signals = {
        **cal,
        "weather": weather,
        "air_quality": air_quality,
        "severe_weather_alerts": alerts,
        "holidays": holiday_info,
        **daylight,
        **business,
        "danish_retail": danish_retail,
    }

    # Add a pre-computed recommendation bias
    signals["recommendation_bias"] = _compute_bias(signals)

    return signals


def _compute_bias(signals: dict) -> dict:
    """
    Pre-compute a recommendation bias based on all signals.

    Returns a dict with 'bias' (waste_reduce | stockout_reduce | neutral)
    and 'reasoning' (short explanation for the LLM).
    """
    reasons_waste = []
    reasons_stockout = []

    # Weekend / Friday => higher demand expected
    if signals.get("is_friday") or signals.get("is_weekend"):
        reasons_stockout.append("weekend/Friday = higher foot traffic")

    # Monday => typically lower demand
    if signals.get("is_monday"):
        reasons_waste.append("Monday = historically lowest demand day")

    # Holiday proximity
    holidays = signals.get("holidays", {})
    if holidays.get("is_day_before_holiday") or holidays.get("long_weekend_approaching"):
        reasons_stockout.append("pre-holiday/long-weekend shopping surge")
    if holidays.get("is_holiday"):
        reasons_waste.append("holiday = stores may be closed or low traffic")
    if holidays.get("is_day_after_holiday"):
        reasons_waste.append("post-holiday = demand dip")

    # Weather
    weather = signals.get("weather", {})
    precip_prob = weather.get("precipitation_probability")
    if precip_prob and precip_prob > 60:
        reasons_waste.append(f"rain likely ({precip_prob}%) = less foot traffic")
    temp_max = weather.get("temperature_max")
    if temp_max is not None and temp_max > 22:
        reasons_stockout.append(f"warm ({temp_max}C) = more outdoor activity, beverage demand")

    # Severe weather
    if signals.get("severe_weather_alerts"):
        reasons_waste.append("active severe weather warning")

    # Payday proximity
    if signals.get("is_payday_week"):
        reasons_stockout.append("payday week = higher discretionary spending")

    # Danish retail events
    retail = signals.get("danish_retail", {})
    if retail.get("is_grilling_season"):
        reasons_stockout.append("grilling season = outdoor food demand")
    if retail.get("is_julefrokost_season"):
        reasons_stockout.append("Julefrokost season = office party supplies")
    if retail.get("is_christmas_season"):
        reasons_stockout.append("Christmas season = elevated demand")
    if retail.get("is_school_holiday"):
        reasons_stockout.append("school holiday = families at home, snack demand")

    # Decide bias
    score = len(reasons_stockout) - len(reasons_waste)
    if score >= 2:
        bias = "stockout_reduce"
    elif score <= -1:
        bias = "waste_reduce"
    else:
        bias = "neutral"

    all_reasons = []
    if reasons_stockout:
        all_reasons.append("Stockout risks: " + "; ".join(reasons_stockout))
    if reasons_waste:
        all_reasons.append("Waste risks: " + "; ".join(reasons_waste))

    return {
        "bias": bias,
        "reasoning": " | ".join(all_reasons) if all_reasons else "No strong signals either way.",
        "stockout_signals": len(reasons_stockout),
        "waste_signals": len(reasons_waste),
    }
