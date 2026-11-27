"""FarmAgent: fetch live weather (OpenWeatherMap) -> ML prediction -> weather-aware advice."""
import math, os, sys, joblib, requests, pandas as pd
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

# crop: (Kc mid-season from FAO-56, main disease when humid, main pests when hot-dry). General guidance, not a local extension bulletin.
CROPS = {
    "General crop": (1.00, "fungal leaf diseases", "mites and aphids"),
    "Wheat": (1.15, "yellow rust and powdery mildew", "aphids"),
    "Rice": (1.20, "blast and sheath blight", "thrips and planthoppers"),
    "Maize": (1.20, "leaf blights", "spider mites and aphids"),
    "Cotton": (1.15, "boll rot and leaf spots", "whitefly, jassids and spider mites"),
    "Sugarcane": (1.25, "red rot and leaf spots", "pyrilla and mites"),
    "Tomato": (1.15, "early and late blight", "spider mites and whitefly"),
    "Potato": (1.15, "late blight", "aphids and mites"),
    "Mustard": (1.15, "Alternaria blight and white rust", "mustard aphid"),
}

def _level(v, lo, hi):  # 0 good, 1 watch, 2 alert for a low/high threshold pair
    return 0 if v < lo else 1 if v < hi else 2

def analyse(w, crop="General crop"):
    """Everything the UI shows: ML prediction, physics-based indicators, and a rule-based prescription on top."""
    kc, wet, dry = CROPS[crop]
    X = pd.DataFrame([{f: w[f] for f in FEATS}])
    t, rh, wind, rain = w["temp_c"], w["humidity"], w["wind_ms"], w["rain_24h_mm"]
    # ML predictions (supervised): ET0 regression + irrigation/pest classifiers with class probabilities
    et0 = max(0.0, float(MODELS["et0"].predict(X)[0])); mae = MODELS["et0_mae"]
    probs = {k: dict(zip(MODELS[k].classes_, MODELS[k].predict_proba(X)[0])) for k in ("irrigation", "pest")}
    pest = max(probs["pest"], key=probs["pest"].get)
    # water balance (FAO-56): crop need = Kc x ET0, minus 80% of forecast rain
    etc, credit = kc * et0, 0.8 * rain
    net = max(0.0, etc - credit)
    irr = "skip" if net < 1.5 else "light" if net < 4 else "heavy"
    # physics indicators
    es = 0.6108 * math.exp(17.27 * t / (t + 237.3)); vpd = es * (1 - rh / 100)
    g = math.log(max(rh, 1) / 100) + 17.27 * t / (237.3 + t); dew = 237.3 * g / (17.27 - g); spread = t - dew
    spray = ("good", "Good spray window: calm air.") if wind < 3 else ("ok", "Spray with coarse droplets; drift risk is moderate.") if wind <= 8 else ("no", "Too windy to spray; wait for calmer air.")
    if rain >= 2: spray = ("no", f"{rain:.0f} mm rain is forecast and would wash sprays off; wait for a dry spell.")
    ind = [
        ("Evaporative demand (ET0)", f"{et0:.1f} mm/day", f"model estimate, typical error ±{mae:.1f}", _level(et0, 3, 5)),
        (f"{crop} water need", f"{etc:.1f} mm/day", f"ET0 × crop factor {kc:.2f}", 0),
        ("Rain credit", f"{credit:.1f} mm", f"80% of the {rain:.1f} mm forecast for 24 h counts as usable", 0 if credit >= 1 else 1),
        ("Air dryness (VPD)", f"{vpd:.1f} kPa", "humid air, fungus-friendly" if vpd < 0.4 else "comfortable for crops" if vpd < 1.2 else "dry air, plants lose water fast" if vpd < 2 else "very dry air, plants under stress",
         1 if vpd < 0.4 else 0 if vpd < 1.2 else 1 if vpd < 2 else 2),
        ("Leaf wetness", f"{spread:.1f} °C gap", "dew point is close to air temperature: leaves stay wet" if spread < 2 else "some dew likely overnight" if spread < 5 else "leaves dry out quickly", 2 if spread < 2 else 1 if spread < 5 else 0),
        ("Heat stress", f"{t:.0f} °C", "hot: crop stress likely" if t >= 35 else "warm" if t >= 30 else "comfortable", _level(t, 30, 35)),
    ]
    # prescription
    litres = net * 4046.86  # 1 mm over 1 acre
    when = "5-8 am (cooler, less evaporation)" if t >= 25 else "mid-morning"
    water = {
        "skip": [(f"No irrigation today: the forecast rain credit of {credit:.1f} mm covers the crop's {etc:.1f} mm need." if credit >= etc else f"No irrigation today: the crop needs only {etc:.1f} mm and the air is not pulling much water."),
                 "Check soil by hand at 5 cm depth; irrigate only if it crumbles dry." if rain < 2 else "Keep field drains clear so rain does not waterlog roots.",
                 "Re-check tomorrow morning" + (" and again after the rain." if rain >= 5 else ".")],
        "light": [f"Apply about {net:.1f} mm (≈ {litres:,.0f} L per acre).", f"Best time: {when}; avoid 11 am to 4 pm.",
                  "Drip or furrow wastes less water than sprinklers" + (" (wind will blow sprinkler water away)." if wind > 5 else "."), "Re-check soil moisture tomorrow."],
        "heavy": [f"Apply about {net:.1f} mm (≈ {litres:,.0f} L per acre)" + (f", in 2 passes of {net/2:.1f} mm a few hours apart to avoid runoff." if net > 6 else "."),
                  f"Best time: {when}; avoid 11 am to 4 pm.", "Mulch or keep crop residue on the soil to cut evaporation.", "Water young and flowering plants first; they suffer most from stress."],
    }[irr]
    if pest == "fungal":
        threat = wet
        steps = [f"Scout for {wet} within 24 h: check lower and inner leaves for spots, mould or water-soaked patches; repeat in 3 days.",
                 "Water by drip or furrow, in the morning only; wet leaves overnight raise disease risk.",
                 f"If symptoms appear, apply a protectant fungicide per the local label. {spray[1]}", "Open up airflow: remove weeds and badly infected lower leaves."]
    elif pest == "mites_aphids":
        threat = dry
        steps = [f"Scout for {dry}: tap a leaf over white paper, look under leaves and at growing tips.",
                 "Hot, dry air multiplies them fast. Keep plants watered; stressed plants get hit hardest.",
                 f"If you find colonies, spray neem oil (about 5 ml per litre) or a water jet in the evening. {spray[1]}", "Avoid broad-spectrum insecticides; they kill natural predators."]
    else:
        threat = "no weather-driven threat"
        steps = ["Weather does not favour pests today.", "Do your routine weekly field walk.", f"Weather only: still watch for {wet} if humid weather returns."]
    return dict(crop=crop, kc=kc, et0=et0, mae=mae, etc=etc, credit=credit, net=net, litres=litres, irr=irr, irr_probs=probs["irrigation"], pest=pest,
                pest_probs=probs["pest"], vpd=vpd, spread=spread, indicators=ind, spray=spray, water_steps=water, pest_steps=steps, threat=threat)

def advise(w, crop="General crop"):
    a = analyse(w, crop)
    return (f"[{w['city']}] {w['temp_c']:.0f}C, RH {w['humidity']:.0f}%, wind {w['wind_ms']:.1f} m/s, rain next 24h {w['rain_24h_mm']:.1f} mm  (crop: {crop})\n"
            f"  Irrigation ({a['irr_probs'][a['irr']]:.0%} model): {IRRIGATION[a['irr']]}\n   - " + "\n   - ".join(a["water_steps"]) +
            f"\n  Pest ({a['pest_probs'][a['pest']]:.0%}): {PEST[a['pest']]}\n   - " + "\n   - ".join(a["pest_steps"]))

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    key, city = os.getenv("OWM_API_KEY"), (sys.argv[1] if len(sys.argv) > 1 else None)
    if key and city: print(advise(live_weather(city, key)))
    else:
        print("(offline demo scenarios; set OWM_API_KEY and pass a city for live data)\n")
        for s in SCENARIOS.values(): print(advise(s), "\n")
