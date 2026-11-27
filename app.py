import os, streamlit as st
from agent import advise, live_weather, SCENARIOS

st.title("🌾 FarmAgent — Personal Farming Assistant")
mode = st.radio("Weather source", ["Live (OpenWeatherMap)", "Scenario: hot & dry", "Scenario: humid & rainy"], horizontal=True)
if mode.startswith("Live"):
    city = st.text_input("City", "Ludhiana")
    key = os.getenv("OWM_API_KEY") or st.text_input("OpenWeatherMap API key", type="password")
    if st.button("Get advice") and key:
        try: st.code(advise(live_weather(city, key)))
        except Exception as e: st.error(f"Weather lookup failed: {e}")
else:
    st.code(advise(SCENARIOS["hot_dry" if "dry" in mode else "humid_rainy"]))
