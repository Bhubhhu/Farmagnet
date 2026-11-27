"""Train supervised models: OWM-style weather features -> irrigation class & pest-risk class.
Training weather/ET0 comes from Open-Meteo archive (free, historical; OWM free tier has no history)."""
import time, joblib, requests, pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, mean_absolute_error, r2_score

# varied climates so the model sees hot-dry, humid, monsoon, temperate
CITIES = {"Delhi": (28.6, 77.2), "Mumbai": (19.1, 72.9), "Ludhiana": (30.9, 75.9), "Bengaluru": (13.0, 77.6),
          "Nairobi": (-1.3, 36.8), "Iowa": (42.0, -93.6), "Seville": (37.4, -6.0), "Sydney": (-33.9, 151.2)}
FEATS = ["temp_c", "humidity", "wind_ms", "pressure_hpa", "clouds", "rain_24h_mm"]
DAILY = "temperature_2m_mean,relative_humidity_2m_mean,wind_speed_10m_mean,surface_pressure_mean,cloud_cover_mean,precipitation_sum,et0_fao_evapotranspiration"

def fetch():
    frames = []
    for name, (lat, lon) in CITIES.items():
        for attempt in range(5):  # API occasionally resets the connection
            try:
                r = requests.get("https://archive-api.open-meteo.com/v1/archive", timeout=60, params=dict(
                    latitude=lat, longitude=lon, start_date="2019-01-01", end_date="2024-12-31",
                    daily=DAILY, wind_speed_unit="ms", timezone="auto"))
                r.raise_for_status(); break
            except requests.RequestException:
                if attempt == 4: raise
                time.sleep(3 * (attempt + 1))
        d = pd.DataFrame(r.json()["daily"]).drop(columns="time")
        d.columns = ["temp_c", "humidity", "wind_ms", "pressure_hpa", "clouds", "rain_24h_mm", "et0"]
        frames.append(d.dropna())
    return pd.concat(frames, ignore_index=True)

def irrigation_label(r):  # FAO-56 water balance: crop need (Kc~1) minus 80% effective rain
    deficit = r.et0 - 0.8 * r.rain_24h_mm
    return "skip" if deficit < 1.5 else "light" if deficit < 4 else "heavy"

def pest_label(r):  # standard agronomy thresholds: leaf wetness favours fungi; hot+dry favours mites/aphids
    if r.humidity >= 80 and 12 <= r.temp_c <= 28: return "fungal"
    if r.temp_c >= 30 and r.humidity <= 45: return "mites_aphids"
    return "low"

if __name__ == "__main__":
    df = fetch()
    df["irrigation"] = df.apply(irrigation_label, axis=1)
    df["pest"] = df.apply(pest_label, axis=1)
    print(len(df), "rows\n", df.irrigation.value_counts().to_dict(), df.pest.value_counts().to_dict())
    models = {}
    for target in ("irrigation", "pest"):
        Xtr, Xte, ytr, yte = train_test_split(df[FEATS], df[target], test_size=0.2, random_state=0, stratify=df[target])
        m = RandomForestClassifier(n_estimators=150, min_samples_leaf=3, n_jobs=-1, random_state=0).fit(Xtr, ytr)
        print(f"\n== {target} ==\n", classification_report(yte, m.predict(Xte), digits=3))
        models[target] = m
    # Regression: predict reference evapotranspiration (mm/day) = how much water the air pulls from a crop today.
    Xtr, Xte, ytr, yte = train_test_split(df[FEATS], df["et0"], test_size=0.2, random_state=0)
    reg = RandomForestRegressor(n_estimators=80, min_samples_leaf=8, n_jobs=-1, random_state=0).fit(Xtr, ytr)
    pred = reg.predict(Xte); mae = mean_absolute_error(yte, pred)
    print(f"\n== ET0 regression ==\n MAE {mae:.2f} mm/day, R2 {r2_score(yte, pred):.3f}")
    models["et0"], models["et0_mae"] = reg, float(mae)
    joblib.dump(models, "model.joblib", compress=3)
