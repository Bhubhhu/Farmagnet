import json, math, os, plotly.graph_objects as go, streamlit as st
from agent import analyse, live_weather, CROPS

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
.ring::before {content:""; position:absolute; inset:7px; border-radius:50%; background:var(--bg)}
.ring i {position:relative; font-style:normal; font-size:.85rem}
.todo {margin:10px 0 0; padding-left:18px; color:var(--ink)} .todo li {margin:3px 0}
.hint {background:#0B2A1E; border-radius:12px; padding:9px 12px; margin-top:12px; color:var(--lime); font-size:.9rem}
.bars {margin:6px 0 14px} .bar-row {display:flex; align-items:center; gap:10px; margin:5px 0; font-size:.9rem}
.bar-row b {width:120px; font-weight:600} .track {flex:1; background:var(--deep); border-radius:99px; height:12px} .track i {display:block; height:12px; border-radius:99px; background:var(--lime)}
.ind {display:flex; gap:12px; align-items:flex-start; padding:10px 0; border-bottom:1px solid #1d4f39} .ind:last-child {border:0}
.dot {flex:none; width:12px; height:12px; border-radius:50%; margin-top:6px} .ind b {color:var(--ink)} .ind small {display:block; color:#9FD3B0; font-size:.85rem}
.ind .v {margin-left:auto; font-weight:800; color:var(--ink); white-space:nowrap}
.sub {font-size:.9rem; opacity:.85; margin-top:2px}
div[data-testid="stButton"] button {background:var(--lime); color:var(--deep); border:0; border-radius:99px; font-weight:700}
div[data-testid="stButton"] button:hover {background:#D4FF8A; color:var(--deep)}
</style>""", unsafe_allow_html=True)

HERE = os.path.dirname(__file__)
@st.cache_data
def load(name):
    gj = json.load(open(os.path.join(HERE, "data", name), encoding="utf-8"))
    for f in gj["features"]:
        p = f["properties"]; p["id"] = f'{p["state"]}|{p.get("district", "")}'
    return gj

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
    return min(ys), min(xs), max(ys), max(xs)

def view(feats):
    s, w, n, e = bounds(feats); lat = (s + n) / 2
    z = min(math.log2(560 * math.cos(math.radians(lat)) / max(n - s, .1)), math.log2(430 / max(e - w, .1))) - 1  # sized for a phone-width map; maplibre tiles are 512px
    return dict(lat=lat, lon=(w + e) / 2), max(2.5, min(8.5, z))

SAT = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

def map_figure(gj, selected, center, zoom):
    feats = gj["features"]; ids = [f["properties"]["id"] for f in feats]
    names = [f["properties"].get("district") or f["properties"]["state"] for f in feats]
    fig = go.Figure(go.Choroplethmap(
        geojson=gj, locations=ids, featureidkey="properties.id", z=[1 if i == selected else 0 for i in ids], showscale=False,
        colorscale=[[0, "#B7F25C"], [1, "#FFC247"]], text=names, hovertemplate="<b>%{text}</b><extra></extra>",
        marker=dict(opacity=.3, line=dict(color="#FFFFFF", width=1.3)),
        selected=dict(marker=dict(opacity=.3)), unselected=dict(marker=dict(opacity=.3))))
    fig.update_layout(height=640, margin=dict(l=0, r=0, t=0, b=0), paper_bgcolor="rgba(0,0,0,0)", dragmode="pan",
                      hoverlabel=dict(bgcolor="#10372A", font=dict(color="#EAF7E1", size=15)),
                      map=dict(style="white-bg", center=center, zoom=zoom,
                               layers=[dict(below="traces", sourcetype="raster", source=[SAT], sourceattribution="Esri World Imagery")]))
    return fig

def clicked(event, feats):
    """Feature the user clicked, or None. Uses the point index, which is stable across reruns."""
    pts = (event.selection.points if event and event.selection else None) or []
    return feats[pts[-1]["point_index"]]["properties"] if pts else None

def get_weather(lat, lon, label, scope):
    if not KEY:
        ss.err = "The server has no OpenWeatherMap key. Add OWM_API_KEY under the app's Secrets and reboot."; return
    try:
        w = dict(fetch(lat, lon)); w["city"] = label; ss.w, ss.scope, ss.err = w, scope, None
    except Exception as e:
        ss.w, ss.err = None, f"Weather lookup for {label} failed: {e}"

ss = st.session_state
for k, v in dict(state=None, district=None, w=None, err=None, scope=None).items(): ss.setdefault(k, v)
stage = 1 if ss.state is None else 2 if ss.district is None else 3
cls = lambda n: "on" if stage == n else "done" if stage > n else ""
st.markdown(f'<div class="top"><div class="logo">🌾 Farm<b>Agent</b> India</div><div class="steps">'
            f'<span class="step {cls(1)}">1 · Pick a state</span><span class="step {cls(2)}">2 · Pick a district</span>'
            f'<span class="step {cls(3)}">3 · District advice</span></div></div>', unsafe_allow_html=True)

CFG = dict(scrollZoom=True, displayModeBar=False)
left, right = st.columns([5, 3], gap="large")
with left:
    if ss.state is None:
        st.markdown('<div class="mapbar">🛰️ India <span class="chip">click a state</span></div>', unsafe_allow_html=True)
        gj = load("states.geojson")
        ev = st.plotly_chart(map_figure(gj, None, dict(lat=22.5, lon=81), 3.6), key="india", on_select="rerun",
                             selection_mode="points", config=CFG, use_container_width=True)
        p = clicked(ev, gj["features"])
        if p:
            ss.state, ss.district = p["state"], None
            get_weather(p["lat"], p["lon"], p["state"], "state"); st.rerun()
    else:
        gj = load("districts.geojson"); feats = [f for f in gj["features"] if f["properties"]["state"] == ss.state]
        sub = dict(type="FeatureCollection", features=feats)
        a, b = st.columns([1, 4])
        if a.button("← All India"):
            for k in ("state", "district", "w", "err", "scope"): ss[k] = None
            st.rerun()
        b.markdown(f'<div class="mapbar">🛰️ {ss.state} <span class="chip">{len(feats)} districts · click one</span></div>', unsafe_allow_html=True)
        center, zoom = view(feats)
        sel = f"{ss.state}|{ss.district}" if ss.district else None
        ev = st.plotly_chart(map_figure(sub, sel, center, zoom), key=f"state-{ss.state}", on_select="rerun",
                             selection_mode="points", config=CFG, use_container_width=True)
        p = clicked(ev, feats)
        if p and p["district"] != ss.district:
            ss.district = p["district"]
            get_weather(p["lat"], p["lon"], p["district"], "district"); st.rerun()
        if st.query_params.get("debug"): st.caption(f"debug: selection={ev.selection.points if ev and ev.selection else None}")

IC = {"skip": ("#4CC9F0", "🌧️"), "light": ("#FFC247", "💧"), "heavy": ("#FF7A59", "💦")}
PC = {"low": ("#7EE08F", "✅", "Low pest risk"), "fungal": ("#4CC9F0", "🍄", "Fungal risk"), "mites_aphids": ("#FFC247", "🐛", "Mites & aphids risk")}
DOT = ["#7EE08F", "#FFC247", "#FF7A59"]
NICE = {"skip": "Skip", "light": "Light", "heavy": "Heavy", "low": "Low", "fungal": "Fungal", "mites_aphids": "Mites & aphids"}

def card(kind, col, ico, title, sub, p, steps):
    items = "".join(f"<li>{t}</li>" for t in steps)
    return (f'<div class="verdict" style="background:{col}"><div class="ico">{ico}</div><div><small>{kind}</small><h4>{title}</h4><div class="sub">{sub}</div></div>'
            f'<div class="ring" style="--p:{p*100:.0f}; --bg:{col}" title="Model probability for this class"><i>{p:.0%}</i></div></div><ul class="todo">{items}</ul>')

def bars(probs):
    return '<div class="bars">' + "".join(f'<div class="bar-row"><b>{NICE[k]}</b><div class="track"><i style="width:{v*100:.0f}%"></i></div><span>{v:.0%}</span></div>'
                                          for k, v in sorted(probs.items(), key=lambda kv: -kv[1])) + "</div>"

with right:
    crop = st.selectbox("🌱 Your crop", list(CROPS), key="crop", help="Sets the crop water factor (Kc) and the diseases and pests to watch for.")
    w = ss.w
    if ss.err:
        st.markdown(f'<div class="panel" style="border-color:#FF7A59"><h3>⚠️ No advice yet</h3><div class="muted">{ss.err}</div></div>', unsafe_allow_html=True)
    elif not w:
        st.markdown('<div class="panel"><h3>👈 Click any state on the satellite map.</h3><div class="muted">FarmAgent reads live weather for the place you pick, a trained model predicts water demand and pest risk, and rules turn that into a plan for your crop.</div></div>', unsafe_allow_html=True)
    else:
        a = analyse(w, crop)
        state_level = ss.scope == "state"
        head = f'{ss.state} · state overview' if state_level else f'{ss.state} · district'
        hint = '<div class="hint">👆 State overview. Click a district on the map for local advice.</div>' if state_level else ""
        conds = "".join(f'<div class="cond"><span>{n}</span><b>{v}</b></div>' for n, v in [
            ("Temp", f'{w["temp_c"]:.0f}°C'), ("Humidity", f'{w["humidity"]:.0f}%'), ("Wind", f'{w["wind_ms"]:.1f} m/s'),
            ("Rain 24h", f'{w["rain_24h_mm"]:.1f} mm'), ("Clouds", f'{w["clouds"]:.0f}%'), ("Pressure", f'{w["pressure_hpa"]:.0f} hPa')])
        st.markdown(f'<div class="panel"><div class="muted">📍 {head} · live now · {crop}</div><h3>{w["city"]}</h3>{hint}<div class="conds">{conds}</div></div>', unsafe_allow_html=True)
        t1, t2, t3, t4 = st.tabs(["✅ What to do", "🔬 Why (analysis)", "🤖 Model prediction", "ℹ️ About"])
        with t1:
            icol, iico = IC[a["irr"]]
            if a["irr"] == "skip": ititle, isub = "Skip irrigation today", f'Crop need {a["etc"]:.1f} mm · rain credit {a["credit"]:.1f} mm'
            else: ititle, isub = f'Apply about {a["net"]:.0f} mm today', f'≈ {a["litres"]:,.0f} litres per acre · {crop}'
            pcol, pico, ptitle = PC[a["pest"]]
            st.markdown(card("Irrigation plan", icol, iico, ititle, isub, a["irr_probs"][a["irr"]], a["water_steps"])
                        + card("Pest plan", pcol, pico, ptitle, f'Watch for: {a["threat"]}', a["pest_probs"][a["pest"]], a["pest_steps"]), unsafe_allow_html=True)
            if w["wind_ms"] > 8: st.warning("Wind is strong: postpone any spraying.")
            st.caption("The ring shows how sure the trained model is about this class.")
        with t2:
            rows = "".join(f'<div class="ind"><span class="dot" style="background:{DOT[lv]}"></span><div><b>{n}</b><small>{note}</small></div><span class="v">{v}</span></div>'
                           for n, v, note, lv in a["indicators"])
            sp = {"good": 0, "ok": 1, "no": 2}[a["spray"][0]]
            rows += f'<div class="ind"><span class="dot" style="background:{DOT[sp]}"></span><div><b>Spray window</b><small>{a["spray"][1]}</small></div><span class="v">{w["wind_ms"]:.1f} m/s</span></div>'
            st.markdown(f'<div class="panel">{rows}</div>', unsafe_allow_html=True)
            st.caption("Green is fine, amber is worth watching, red needs action.")
        with t3:
            st.markdown(f'<div class="panel"><b>Water demand (regression)</b><div class="muted">Predicted evaporation demand today: <b style="color:#EAF7E1">{a["et0"]:.1f} mm/day</b> (typical error ±{a["mae"]:.1f} mm).</div>'
                        f'<br><b>Irrigation class (generic crop)</b>{bars(a["irr_probs"])}<b>Pest class</b>{bars(a["pest_probs"])}</div>', unsafe_allow_html=True)
        with t4:
            st.markdown("""<div class="panel"><b>What you are looking at</b><ul class="todo">
<li><b>Prediction:</b> three trained Random Forest models read the live weather. One regression predicts water demand (ET0, R² 0.92), two classifiers label irrigation need and pest risk.</li>
<li><b>Analysis:</b> physics formulas on the same weather: vapour-pressure deficit, dew-point gap, heat stress and the spray window.</li>
<li><b>Prescription:</b> rules turn the predictions into amounts and timing: crop need = Kc × ET0, minus 80% of forecast rain.</li></ul>
<b>Data</b><div class="muted">Live weather: OpenWeatherMap. Training: 6 years of Open-Meteo daily weather for 8 climates. Boundaries: public GADM-based India map.</div><br>
<b>Limits</b><div class="muted">Training labels come from agronomy formulas, not field trials. Weather is read at one point per place. Crop factors are mid-season values; young crops need less. Treat this as guidance and confirm with your local agriculture office.</div></div>""", unsafe_allow_html=True)
st.caption("Weather is read at one point inside each state or district. Boundaries are simplified and older (Telangana sits inside Andhra Pradesh, Ladakh inside Jammu & Kashmir). Guidance only, not agronomist advice.")
