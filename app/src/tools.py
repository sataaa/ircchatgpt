import base64
import requests
import logging
from ddgs import DDGS

logger = logging.getLogger(__name__)


def search_web(query: str) -> str:
    try:
        results = list(DDGS().text(query, max_results=3))
        if not results:
            return "No results found."
        return " | ".join(f"{r['title']}: {r['body']}" for r in results)
    except Exception as e:
        logger.warning("search_web error: %s", e)
        return f"Search failed: {e}"


_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Icy fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Light showers", 81: "Showers", 82: "Heavy showers",
    85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm w/ hail", 99: "Thunderstorm w/ heavy hail",
}


def get_weather(city: str) -> str:
    try:
        geo = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params={"name": city, "count": 1},
            timeout=10,
        ).json()
        if not geo.get("results"):
            return f"City not found: {city}"
        loc = geo["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        place = f"{loc['name']}, {loc.get('country', '')}"

        wx = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "wind_speed_unit": "kmh",
            },
            timeout=10,
        ).json()
        cur = wx["current"]
        desc = _WMO_CODES.get(cur["weather_code"], f"Code {cur['weather_code']}")
        return (
            f"{place}: {desc}, {cur['temperature_2m']}°C "
            f"(feels like {cur['apparent_temperature']}°C), "
            f"humidity {cur['relative_humidity_2m']}%, wind {cur['wind_speed_10m']} km/h"
        )
    except Exception as e:
        logger.warning("get_weather error: %s", e)
        return f"Weather lookup failed: {e}"


def generate_image(api_key: str, imgbb_api_key: str, prompt: str) -> str:
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt=prompt,
        )
        image_bytes = response.generated_images[0].image.image_bytes
        encoded = base64.b64encode(image_bytes).decode("utf-8")
        upload = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": imgbb_api_key, "image": encoded},
            timeout=15,
        )
        upload.raise_for_status()
        return upload.json()["data"]["image"]["url"]
    except Exception as e:
        logger.warning("generate_image error: %s", e)
        return f"Image generation failed: {e}"
