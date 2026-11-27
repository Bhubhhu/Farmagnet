import json, math, os, folium, streamlit as st
from streamlit_folium import st_folium
from agent import predict, live_weather, IRRIGATION, PEST

st.set_page_config(page_title="FarmAgent India", page_icon="🌾", layout="wide", initial_sidebar_state="collapsed")

try: KEY = st.secrets["OWM_API_KEY"]
except Exception: KEY = os.getenv("OWM_API_KEY")

st.markdown("""<style>
#MainMenu, footer, header[data-testid="stHeader"] {visibility:hidden; height:0}
.block-container {padding:1rem 2rem 2rem; max-width:1400px}
:root {--lime:#B7F25C; --leaf:#3FBF6B; --sun:#FFC247; --clay:#FF7A59; --sky:#4CC9F0; --ink:#EAF7E1; --deep:#0B2A1E; --panel:#10372A}
.top {display:flex; align-items:center; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:14px}
.logo {font-size:1.7rem; font-weight:800; color:var(--ink)} .logo b {color:var(--lime)}
.steps {display:flex; gap:8px; flex-wrap:wrap}
.step {padding:7px 14px; border-radius:99px; font-size:.85rem; font-weight:600; border:1.5px solid #2B6A4C; color:#9FD3B0}
.step.on {background:var(--lime); border-color:var(--lime); color:var(--deep)} .step.done {border-color:var(--leaf); color:var(--leaf)}
.mapbar {display:flex; align-items:center; gap:10px; margin-bottom:6px; color:var(--ink); font-weight:700; font-size:1.05rem}
.chip {background:var(--panel); border:1.5px solid #2B6A4C; border-radius:99px; padding:3px 12px; font-size:.85rem; color:var(--lime)}
.panel {background:var(--panel); border:1.5px solid #2B6A4C; border-radius:22px; padding:20px 22px; color:var(--ink)}
.panel h3 {margin:0 0 4px; color:var(--ink); font-size:1.5rem} .muted {color:#9FD3B0; font-size:.95rem}
.conds {display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin:14px 0}
.cond {background:var(--deep); border-radius:14px; padding:9px 12px} .cond span {display:block; font-size:.72rem; color:#9FD3B0; text-transform:uppercase; letter-spacing:.06em}
.cond b {font-size:1.25rem; color:var(--ink)}
.verdict {display:flex; gap:16px; align-items:center; border-radius:20px; padding:16px 18px; margin-top:12px; color:#0B2A1E}
.verdict .ico {font-size:2.4rem} .verdict h4 {margin:0; font-size:1.35rem; color:#0B2A1E} .verdict small {font-weight:700; letter-spacing:.08em; text-transform:uppercase; opacity:.75}
.verdict p {margin:4px 0 0; font-size:.95rem; line-height:1.35}
.ring {--p:0; margin-left:auto; flex:none; width:62px; height:62px; border-radius:50%; display:grid; place-items:center; font-weight:800; color:#0B2A1E;
       background:conic-gradient(#0B2A1E calc(var(--p)*1%), rgba(11,42,30,.2) 0); position:relative}
.ring::before {content:""; position:absolute; inset:7px; border-radius:50%; background:inherit; background:var(--bg)}
.ring i {position:relative; font-style:normal; font-size:.85rem}
.todo {margin:10px 0 0; padding-left:18px; color:var(--ink)} .todo li {margin:3px 0}
div[data-testid="stButton"] button {background:var(--lime); color:var(--deep); border:0; border-radius:99px; font-weight:700}
div[data-testid="stButton"] button:hover {background:#D4FF8A; color:var(--deep)}
</style>""", unsafe_allow_html=True)

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

def view(feats):
    (s, w), (n, e) = bounds(feats)
    lat = (s + n) / 2
    z = min(math.log2(780 * math.cos(math.radians(lat)) / max(n - s, .1)), math.log2(900 / max(e - w, .1)))
    return [lat, (w + e) / 2], max(4, min(9, z))

SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
def base(**kw): return folium.Map(tiles=SAT, attr="Esri World Imagery", min_zoom=4, max_zoom=12, zoom_control=True, **kw)

ss = st.session_state
ss.setdefault("state", None); ss.setdefault("district", None); ss.setdefault("w", None); ss.setdefault("err", None)
stage = 1 if ss.state is None else 2 if ss.w is None else 3
cls = lambda n: "on" if stage == n else "done" if stage > n else ""
st.markdown(f'<div class="top"><div class="logo">🌾 Farm<b>Agent</b> India</div><div class="steps">'
            f'<span class="step {cls(1)}">1 · Pick a state</span><span class="step {cls(2)}">2 · Pick a district</span>'
            f'<span class="step {cls(3)}">3 · Read the advice</span></div></div>', unsafe_allow_html=True)

left, right = st.columns([5, 3], gap="large")
with left:
    if ss.state is None:
        st.markdown('<div class="mapbar">🛰️ India <span class="chip">click a state</span></div>', unsafe_allow_html=True)
        m = base(location=[22.5, 81], zoom_start=4.75, zoom_snap=0.25, min_lat=0, max_lat=42, min_lon=60, max_lon=105, max_bounds=True)
        folium.GeoJson(load("states.geojson"),
                       style_function=lambda f: dict(fillColor="#B7F25C", fillOpacity=.06, color="#FFFFFF", weight=1.6),
                       highlight_function=lambda f: dict(fillColor="#B7F25C", fillOpacity=.45, color="#B7F25C", weight=3),
                       tooltip=folium.GeoJsonTooltip(["state"], labels=False)).add_to(m)
        hit = st_folium(m, height=640, use_container_width=True, returned_objects=["last_active_drawing"], key="india").get("last_active_drawing")
        if hit and hit.get("properties", {}).get("state"):
            ss.state, ss.district, ss.w, ss.err = hit["properties"]["state"], None, None, None
            st.rerun()
    else:
        feats = [f for f in load("districts.geojson")["features"] if f["properties"]["state"] == ss.state]
        a, b = st.columns([1, 4])
        if a.button("← All India"): ss.state = ss.district = ss.w = ss.err = None; st.rerun()
        b.markdown(f'<div class="mapbar">🛰️ {ss.state} <span class="chip">{len(feats)} districts · click one</span></div>', unsafe_allow_html=True)
        loc, z = view(feats)
        m = base(location=loc, zoom_start=z, zoom_snap=0.25); sel = ss.district
        folium.GeoJson({"type": "FeatureCollection", "features": feats},
                       style_function=lambda f: dict(fillColor="#FFC247" if f["properties"]["district"] == sel else "#B7F25C",
                                                     fillOpacity=.5 if f["properties"]["district"] == sel else .06, color="#FFFFFF", weight=1.4),
                       highlight_function=lambda f: dict(fillColor="#B7F25C", fillOpacity=.45, color="#B7F25C", weight=3),
                       tooltip=folium.GeoJsonTooltip(["district"], labels=False)).add_to(m)
        hit = st_folium(m, height=640, use_container_width=True, returned_objects=["last_active_drawing"], key=f"state-{ss.state}").get("last_active_drawing")
        p = (hit or {}).get("properties", {})
        if p.get("district") and p["district"] != ss.district:
            if not KEY:
                ss.err = "The server has no OpenWeatherMap key. Add OWM_API_KEY under the app's Secrets and reboot."
            else:
                try:
                    w = fetch(p["lat"], p["lon"]); w["city"] = p["district"]
                    ss.district, ss.w, ss.err = p["district"], w, None
                except Exception as e:
                    ss.district, ss.w, ss.err = p["district"], None, f"Weather lookup for {p['district']} failed: {e}"
            st.rerun()

TODO = {
    "skip": ["Hold all irrigation today", "Dip-check soil at 5 cm before the next cycle", "Keep field drains clear"],
    "light": ["Run a short drip or sprinkler cycle", "Water early morning to cut evaporation", "Recheck soil moisture tomorrow"],
    "heavy": ["Irrigate deeply before 9am or after 6pm", "Mulch to slow water loss", "Prioritise young or flowering crops first"],
    "fungal": ["Scout leaves for spots and mould", "Avoid overhead watering", "Protectant fungicide once the rain stops"],
    "mites_aphids": ["Check leaf undersides for mites and aphids", "Spray water or neem oil in the evening", "Avoid water stress on stressed plants"],
    "low": ["Routine scouting only", "Keep a weekly walk-through", "Log anything unusual"],
}
IC = {"skip": ("#4CC9F0", "🌧️", "Skip irrigation"), "light": ("#FFC247", "💧", "Light irrigation"), "heavy": ("#FF7A59", "💦", "Irrigate heavily")}
PC = {"low": ("#7EE08F", "✅", "Low pest risk"), "fungal": ("#4CC9F0", "🍄", "Fungal risk"), "mites_aphids": ("#FFC247", "🐛", "Mites & aphids risk")}

def verdict(kind, lab, p, col, ico, title, text):
    items = "".join(f"<li>{t}</li>" for t in TODO[lab])
    return (f'<div class="verdict" style="background:{col}"><div class="ico">{ico}</div><div><small>{kind}</small><h4>{title}</h4><p>{text}</p></div>'
            f'<div class="ring" style="--p:{p*100:.0f}; --bg:{col}"><i>{p:.0%}</i></div></div><ul class="todo">{items}</ul>')

with right:
    w = ss.w
    if ss.err:
        st.markdown(f'<div class="panel" style="border-color:#FF7A59"><h3>⚠️ No advice yet</h3><div class="muted">{ss.err}</div></div>', unsafe_allow_html=True)
    elif not w:
        msg = "Click any state on the satellite map." if ss.state is None else f"Click a district of {ss.state}."
        st.markdown(f'<div class="panel"><h3>👈 {msg}</h3><div class="muted">FarmAgent reads live weather for the district and an ML model decides today\'s irrigation and pest advice.</div></div>', unsafe_allow_html=True)
    else:
        r = predict(w)
        conds = "".join(f'<div class="cond"><span>{n}</span><b>{v}</b></div>' for n, v in [
            ("Temp", f'{w["temp_c"]:.0f}°C'), ("Humidity", f'{w["humidity"]:.0f}%'), ("Wind", f'{w["wind_ms"]:.1f} m/s'),
            ("Rain 24h", f'{w["rain_24h_mm"]:.1f} mm'), ("Clouds", f'{w["clouds"]:.0f}%'), ("Pressure", f'{w["pressure_hpa"]:.0f} hPa')])
        (il, ip), (pl, pp) = r["irrigation"], r["pest"]
        html = (f'<div class="panel"><div class="muted">📍 {ss.state} · live now</div><h3>{w["city"]}</h3><div class="conds">{conds}</div>'
                + verdict("Irrigation", il, ip, *IC[il], IRRIGATION[il]) + verdict("Pest watch", pl, pp, *PC[pl], PEST[pl]) + "</div>")
        st.markdown(html, unsafe_allow_html=True)
        if w["wind_ms"] > 8: st.warning("Wind is strong: postpone any spraying.")
st.caption("Weather is read at one point inside each district. Boundaries are simplified and older (Telangana sits inside Andhra Pradesh, Ladakh inside Jammu & Kashmir). Guidance only, not agronomist advice.")
