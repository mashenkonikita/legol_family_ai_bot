import os
import requests

YANDEX_API_KEY = os.getenv('YANDEX_WEATHER_API_KEY')

def get_lipetsk_weather_data():
    url = "https://api.weather.yandex.ru/v2/forecast"
    headers = {"X-Yandex-Weather-Key": YANDEX_API_KEY}
    params = {
        "lat": "52.6031",
        "lon": "39.5708",
        "lang": "ru_RU",
        "limit": 1,
        "hours": False
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        fact = resp.json().get("fact", {})
        temp = fact.get("temp", "?")
        feels_like = fact.get("feels_like", "?")
        condition = fact.get("condition", "?")
        return temp, feels_like, condition
    except Exception as e:
        return "?", "?", f"Ошибка: {e}"
