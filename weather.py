"""Current conditions from Open-Meteo. No API key."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

# (lo, hi, summary, severity). Severity is how strongly the sky should show.
_CODES = (
    (0, 0, "晴", 0.08),
    (1, 1, "少云", 0.18),
    (2, 2, "多云", 0.28),
    (3, 3, "阴", 0.36),
    (45, 48, "雾", 0.42),
    (51, 57, "毛毛雨", 0.5),
    (61, 67, "雨", 0.62),
    (71, 77, "雪", 0.55),
    (80, 82, "阵雨", 0.7),
    (85, 86, "阵雪", 0.58),
    (95, 99, "雷雨", 0.9),
)


def describe(code: int, temp_c: float | None, precip_mm: float) -> dict:
    summary, severity = "多云", 0.3
    for lo, hi, name, level in _CODES:
        if lo <= code <= hi:
            summary, severity = name, level
            break
    precip = precip_mm > 0 or code >= 51
    if precip:
        severity = max(severity, 0.45)
    return {
        "summary": summary,
        "severity": round(min(severity, 1.0), 4),
        "precip": precip,
        "temp_c": temp_c,
    }


PRESETS = {
    "晴": (0.08, False),
    "多云": (0.28, False),
    "阴": (0.36, False),
    "雾": (0.42, False),
    "雨": (0.62, True),
    "雪": (0.55, True),
}


_CLEAR = frozenset({"晴", "少云"})
_STATUS = {
    "多云": "⛅",
    "阴": "☁️",
    "雾": "🌫️",
    "毛毛雨": "🌧️",
    "小雨": "🌧️",
    "雨": "🌧️",
    "阵雨": "🌧️",
    "雷雨": "⛈️",
    "雪": "❄️",
    "阵雪": "❄️",
}


def status_mark(summary: str, chapter: str) -> str:
    if summary in _CLEAR:
        return "🌙" if chapter == "night" else "☀️"
    return _STATUS.get(summary, "🪟")


def preset(summary: str) -> dict:
    severity, precip = PRESETS[summary]
    return {
        "summary": summary,
        "severity": severity,
        "precip": precip,
        "temp_c": None,
        "ok": True,
        "city": "",
        "chosen": True,
    }


def fetch_weather(lat: float, lon: float, city: str = "", *, opener=urllib.request.urlopen) -> dict:
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,weather_code,precipitation&timezone=auto"
    )
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with opener(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode())
        current = payload["current"]
        sky = describe(
            int(current["weather_code"]),
            float(current["temperature_2m"]),
            float(current.get("precipitation") or 0),
        )
        sky["ok"] = True
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        # 天气只是配方的一层。取不到时用中性的多云，仍然出图。
        print(f"天气没有取到：{exc}", file=sys.stderr)
        sky = {"summary": "多云", "severity": 0.3, "precip": False, "temp_c": None, "ok": False}
    sky["city"] = city
    return sky
