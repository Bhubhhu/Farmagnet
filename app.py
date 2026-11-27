import json, os, folium, streamlit as st
from streamlit_folium import st_folium
from agent import predict, live_weather, IRRIGATION, PEST

st.set_page_config(page_title="FarmAgent India", page_icon="🌾", layout="wide")

try: KEY = st.secrets["OWM_API_KEY"]
except Exception: KEY = os.getenv("OWM_API_KEY")

st.markdown("""<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:1.5rem; max-width:1250px}
.hero {background:linear-gradient(120deg,#2F7D4F,#6FA84A 60%,#E0A526); border-radius:20px; padding:24px 32px; color:#FFFBEA; margin-bottom:14px}
.hero h1 {margin:0; font-size:2.1rem; color:#FFFBEA} .hero p {margin:6px 0 0; font-size:1.05rem; opacity:.95}
.crumb {font-size:1.1rem; font-weight:700; color:#1F3D2B; margin:2px 0 8px}
.tiles {display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:10px 0 16px}
.tile {background:#FFFBEA; border:2px solid #CFE3B4; border-radius:14px; padding:10px 14px}
.tile b {display:block; font-size:1.35rem; color:#1F3D2B} .tile span {font-size:.8rem; color:#4C7A55; text-transform:uppercase; letter-spacing:.05em}
.card {border-radius:18px; padding:18px 22px; margin-bottom:14px; color:#FFFBEA; box-shadow:0 4px 14px rgba(31,61,43,.18)}
.card small {text-transform:uppercase; letter-spacing:.08em; opacity:.9; font-weight:600}
.card h2 {margin:2px 0 6px; font-size:1.7rem; color:#FFFBEA} .card p {margin:0 0 10px; font-size:1rem}
.bar {background:rgba(255,251,234,.3); border-radius:99px; height:9px} .bar i {display:block; height:9px; border-radius:99px; background:#FFFBEA}
.place {font-size:1.25rem; font-weight:700; color:#1F3D2B; margin-top:4px}
</style>""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>🌾 FarmAgent India</h1>
<p>Pick a state, then a district. FarmAgent reads the live weather there and tells you what to do about irrigation and pests today.</p></div>""", unsafe_allow_html=True)

HERE = os.path.dirname(__file__)
@st.cache_data
def load(name): return json.load(open(os.path.join(HERE, "data", name), encoding="utf-8"))

@st.cache_data(ttl=600, show_spinner="Reading live weather...")
def fetch(lat, lon): return live_weather(None, KEY, lat, lon)

def bounds(feats):
    pts = []
    def walk(c):
        if isinstance(c[0], (int, float)): pts.append(c)
        else:
            for x in c: walk(x)
    for f in feats: walk(f["geometry"]["coordinates"])
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [[min(ys), min(xs)], [max(ys), max(xs)]]

SEA = "<style>.leaflet-container{background:#CFE8F3}</style>"
PALETTE = ["#6FA84A", "#8FBF5A", "#E0A526", "#4FA3A5", "#D9843F", "#A8C65A"]
ss = st.session_state
ss.setdefault("state", None); ss.setdefault("district", None); ss.setdefault("w", None)

left, right = st.columns([3, 2], gap="large")
with left:
    if ss.state is None:
        st.markdown('<div class="crumb">🇮🇳 India: click a state</div>', unsafe_allow_html=True)
        m = folium.Map(location=[22.5, 80.5], zoom_start=4, tiles=None, zoom_control=True, min_zoom=4, max_zoom=7)
        m.get_root().header.add_child(folium.Element(SEA))
        states = load("states.geojson")
        names = sorted(f["properties"]["state"] for f in states["features"])
        folium.GeoJson(states, style_function=lambda f: dict(fillColor=PALETTE[names.index(f["properties"]["state"]) % len(PALETTE)],
                       color="#1F3D2B", weight=1.6, fillOpacity=.85),
                       highlight_function=lambda f: dict(fillColor="#C8553D", weight=3, fillOpacity=.95),
                       tooltip=folium.GeoJsonTooltip(["state"], labels=False)).add_to(m)
        m.fit_bounds([[6.5, 68], [37.5, 97.5]])
        hit = st_folium(m, height=600, use_container_width=True, returned_objects=["last_active_drawing"], key="india").get("last_active_drawing")
        if hit and hit.get("properties", {}).get("state"):
            ss.state, ss.district, ss.w = hit["properties"]["state"], None, None
            st.rerun()
    else:
        a, b = st.columns([1, 3])
        if a.button("← All India"): ss.state = ss.district = ss.w = None; st.rerun()
        b.markdown(f'<div class="crumb">India › {ss.state}: click a district</div>', unsafe_allow_html=True)
        feats = [f for f in load("districts.geojson")["features"] if f["properties"]["state"] == ss.state]
        m = folium.Map(tiles=None, zoom_control=True)
        m.get_root().header.add_child(folium.Element(SEA))
        sel = ss.district
        folium.GeoJson({"type": "FeatureCollection", "features": feats},
                       style_function=lambda f: dict(fillColor="#E0A526" if f["properties"]["district"] == sel else "#8FBF5A",
                                                     color="#1F3D2B", weight=1.2, fillOpacity=.9),
                       highlight_function=lambda f: dict(fillColor="#C8553D", weight=3, fillOpacity=.95),
                       tooltip=folium.GeoJsonTooltip(["district"], labels=False)).add_to(m)
        m.fit_bounds(bounds(feats))
        hit = st_folium(m, height=600, use_container_width=True, returned_objects=["last_active_drawing"], key=f"state-{ss.state}").get("last_active_drawing")
        p = (hit or {}).get("properties", {})
        if p.get("district") and p["district"] != ss.district:
            if not KEY: st.warning("Live weather isn't configured on this server.")
            else:
                try:
                    w = fetch(p["lat"], p["lon"]); w["city"] = f'{p["district"]}, {ss.state}'
                    ss.district, ss.w = p["district"], w; st.rerun()
                except Exception as e: st.error(f"Couldn't get weather for {p['district']} ({e}).")

with right:
    w = ss.w
    if not w:
        msg = "Click a state on the map." if ss.state is None else f"Click a district of {ss.state}."
        st.markdown(f'<div class="card" style="background:#2A7FA8"><small>Waiting</small><h2>👈 {msg}</h2><p>The prediction and advice appear here.</p></div>', unsafe_allow_html=True)
    else:
        r = predict(w)
        IC = {"skip": ("#2A7FA8", "🌧️ Skip irrigation"), "light": ("#C98A12", "💧 Light irrigation"), "heavy": ("#C8553D", "💦 Irrigate heavily")}
        PC = {"low": ("#2F7D4F", "✅ Low pest risk"), "fungal": ("#1B7F7A", "🍄 Fungal risk"), "mites_aphids": ("#B5651D", "🐛 Mites & aphids risk")}
        st.markdown(f'<div class="place">📍 {w["city"]}</div>', unsafe_allow_html=True)
        st.markdown('<div class="tiles">' + "".join(f'<div class="tile"><span>{n}</span><b>{v}</b></div>' for n, v in [
            ("Temp", f'{w["temp_c"]:.0f}°C'), ("Humidity", f'{w["humidity"]:.0f}%'), ("Wind", f'{w["wind_ms"]:.1f} m/s'),
            ("Rain 24h", f'{w["rain_24h_mm"]:.1f} mm'), ("Clouds", f'{w["clouds"]:.0f}%'), ("Pressure", f'{w["pressure_hpa"]:.0f} hPa')]) + "</div>", unsafe_allow_html=True)
        for kind, C, TXT in (("irrigation", IC, IRRIGATION), ("pest", PC, PEST)):
            lab, p = r[kind]; col, title = C[lab]
            st.markdown(f'<div class="card" style="background:{col}"><small>{kind} · {p:.0%} confident</small><h2>{title}</h2><p>{TXT[lab]}</p>'
                        f'<div class="bar"><i style="width:{p:.0%}"></i></div></div>', unsafe_allow_html=True)
        if w["wind_ms"] > 8: st.warning("Wind is strong: postpone any spraying.")
st.caption("Weather is read at a point inside each district. Boundaries are simplified and pre-2014/2019 (Telangana is inside Andhra Pradesh, Ladakh inside Jammu & Kashmir). Guidance only.")
