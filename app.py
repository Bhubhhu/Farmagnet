import os, folium, streamlit as st
from streamlit_folium import st_folium
from agent import predict, live_weather, SCENARIOS, IRRIGATION, PEST

st.set_page_config(page_title="FarmAgent", page_icon="🌾", layout="wide")

try: KEY = st.secrets["OWM_API_KEY"]
except Exception: KEY = os.getenv("OWM_API_KEY")

st.markdown("""<style>
#MainMenu, footer {visibility:hidden}
.block-container {padding-top:1.5rem; max-width:1250px}
.hero {background:linear-gradient(120deg,#2F7D4F,#6FA84A 60%,#E0A526); border-radius:20px; padding:26px 32px; color:#FFFBEA; margin-bottom:18px}
.hero h1 {margin:0; font-size:2.2rem; color:#FFFBEA} .hero p {margin:6px 0 0; font-size:1.05rem; opacity:.95}
.tiles {display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:10px 0 16px}
.tile {background:#FFFBEA; border:2px solid #CFE3B4; border-radius:14px; padding:10px 14px}
.tile b {display:block; font-size:1.35rem; color:#1F3D2B} .tile span {font-size:.8rem; color:#4C7A55; text-transform:uppercase; letter-spacing:.05em}
.card {border-radius:18px; padding:18px 22px; margin-bottom:14px; color:#FFFBEA; box-shadow:0 4px 14px rgba(31,61,43,.18)}
.card small {text-transform:uppercase; letter-spacing:.08em; opacity:.9; font-weight:600}
.card h2 {margin:2px 0 6px; font-size:1.7rem; color:#FFFBEA} .card p {margin:0 0 10px; font-size:1rem}
.bar {background:rgba(255,251,234,.3); border-radius:99px; height:9px} .bar i {display:block; height:9px; border-radius:99px; background:#FFFBEA}
.place {font-size:1.25rem; font-weight:700; color:#1F3D2B; margin-top:4px}
div[data-testid="stPills"] button {border-radius:99px; border:2px solid #6FA84A; background:#FFFBEA}
div[data-testid="stPills"] button[aria-checked="true"], div[data-testid="stPills"] button[kind="pillsActive"] {background:#2F7D4F; color:#FFFBEA}
</style>""", unsafe_allow_html=True)

st.markdown("""<div class="hero"><h1>🌾 FarmAgent</h1>
<p>Click anywhere on the map. FarmAgent reads the live weather there and tells you what to do with water and pests today.</p></div>""", unsafe_allow_html=True)

@st.cache_data(ttl=600, show_spinner=False)
def fetch(city=None, lat=None, lon=None): return live_weather(city, KEY, lat, lon)

QUICK = {"Ludhiana": "Ludhiana", "Mumbai": "Mumbai", "Nairobi": "Nairobi", "Seattle": "Seattle", "Kochi": "Kochi",
         "🔥 Hot & dry scenario": "hot_dry", "🌧️ Humid & rainy scenario": "humid_rainy"}
st.session_state.setdefault("w", None); st.session_state.setdefault("seen", None)

pick = st.pills("Quick picks", list(QUICK), label_visibility="collapsed")
left, right = st.columns([3, 2], gap="large")
with left:
    w = st.session_state.w
    m = folium.Map(location=[w["lat"], w["lon"]] if w and "lat" in w else [22, 20], zoom_start=6 if w and "lat" in w else 2,
                   tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attr="Esri World Imagery")
    if w and "lat" in w:
        folium.Marker([w["lat"], w["lon"]], tooltip=w["city"], icon=folium.Icon(color="green", icon="leaf")).add_to(m)
    click = st_folium(m, height=520, use_container_width=True, returned_objects=["last_clicked"]).get("last_clicked")

# Process one new input per run: quick pick or map click.
try:
    if pick and pick != st.session_state.seen:
        st.session_state.seen = pick
        v = QUICK[pick]
        st.session_state.w = SCENARIOS[v] if v in SCENARIOS else fetch(city=v)
        st.rerun()
    elif click and click != st.session_state.get("last_click"):
        st.session_state.last_click = click
        if not KEY: st.warning("Live weather isn't configured on this server. Use a scenario quick pick.")
        else:
            st.session_state.w = fetch(lat=round(click["lat"], 2), lon=round(click["lng"], 2)); st.rerun()
except Exception as e:
    st.error(f"Couldn't get weather for that spot ({e}). Try another place.")

with right:
    w = st.session_state.w
    if not w:
        st.markdown('<div class="card" style="background:#2A7FA8"><small>Waiting</small><h2>👈 Pick a place</h2><p>Click the map or choose a quick pick to get advice for today.</p></div>', unsafe_allow_html=True)
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
st.caption("Models trained on Open-Meteo history; labels from FAO-56 water balance and agronomy thresholds. Guidance only.")
