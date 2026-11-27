"""FarmAgent: fetch live weather (OpenWeatherMap) -> ML prediction -> weather-aware advice."""
import os, sys, joblib, requests, pandas as pd
from train import FEATS

MODELS = joblib.load(os.path.join(os.path.dirname(__file__), "model.joblib"))
OWM = "https://api.openweathermap.org/data/2.5"
_http = requests.Session()  # retries ride out the occasional TLS/connection reset
_http.mount("https://", requests.adapters.HTTPAdapter(max_retries=requests.adapters.Retry(total=3, backoff_factor=0.5, status_forcelist=(429, 500, 502, 503, 504))))

# Offline scenarios mirroring OWM readings, for demo without a key / without network.
SCENARIOS = {
    "hot_dry": dict(city="Hot & dry day", temp_c=36, humidity=28, wind_ms=5.5, pressure_hpa=1004, clouds=5, rain_24h_mm=0.0),
    "humid_rainy": dict(city="Humid & rainy day", temp_c=22, humidity=92, wind_ms=1.5, pressure_hpa=1010, clouds=95, rain_24h_mm=14.0),
}

def live_weather(city=None, key=None, lat=None, lon=None):
    """Current conditions + next-24h forecast rain (8 x 3h slots) from OpenWeatherMap free tier."""
    p = dict(appid=key, units="metric")
    p.update(lat=lat, lon=lon) if lat is not None else p.update(q=city)
    cur = _http.get(f"{OWM}/weather", params=p, timeout=15); cur.raise_for_status()
    fc = _http.get(f"{OWM}/forecast", params={**p, "cnt": 8}, timeout=15); fc.raise_for_status()
    c = cur.json()
    rain = sum(s.get("rain", {}).get("3h", 0) for s in fc.json()["list"])
    return dict(city=c["name"] or f"{c['coord']['lat']:.1f}, {c['coord']['lon']:.1f}", lat=c["coord"]["lat"], lon=c["coord"]["lon"], temp_c=c["main"]["temp"], humidity=c["main"]["humidity"], wind_ms=c["wind"]["speed"],
                pressure_hpa=c["main"]["pressure"], clouds=c["clouds"]["all"], rain_24h_mm=rain)

IRRIGATION = {
    "skip": "Do NOT irrigate today. Rain/low evaporation covers crop water demand.",
    "light": "Light irrigation (~3-4 mm): early morning drip or short cycle.",
    "heavy": "Irrigate heavily (~6+ mm). Do it before 9am or after 6pm to cut evaporation loss.",
}
PEST = {
    "fungal": "HIGH fungal risk (blight/mildew): humid + mild. Scout leaves, avoid overhead watering, consider a protectant fungicide after rain stops.",
    "mites_aphids": "Hot-dry pest risk (spider mites/aphids): scout leaf undersides, use a water spray or neem oil in the evening.",
    "low": "Low pest pressure from weather. Routine scouting only.",
}

def predict(w):
    X = pd.DataFrame([{f: w[f] for f in FEATS}])
    out = {}
    for t in ("irrigation", "pest"):
        m = MODELS[t]; pr = m.predict_proba(X)[0]; i = pr.argmax()
        out[t] = (m.classes_[i], pr[i])
    return out

def advise(w):
    out = predict(w)
    (ir, irp), (pe, pep) = out["irrigation"], out["pest"]
    # safety override: never spray in strong wind (drift) -- a rule on top of the model
    spray_note = " Wind is strong: postpone any spraying." if w["wind_ms"] > 8 else ""
    return (f"[{w['city']}] {w['temp_c']:.0f}C, RH {w['humidity']:.0f}%, wind {w['wind_ms']:.1f} m/s, rain next 24h {w['rain_24h_mm']:.1f} mm\n"
            f"  Irrigation ({irp:.0%}): {IRRIGATION[ir]}\n  Pest ({pep:.0%}): {PEST[pe]}{spray_note}")

if __name__ == "__main__":
    key, city = os.getenv("OWM_API_KEY"), (sys.argv[1] if len(sys.argv) > 1 else None)
    if key and city: print(advise(live_weather(city, key)))
    else:
        print("(offline demo scenarios; set OWM_API_KEY and pass a city for live data)\n")
        for s in SCENARIOS.values(): print(advise(s), "\n")
