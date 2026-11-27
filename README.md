# FarmAgent — Personal Farming Assistant
Weather-aware irrigation/pest advice. `agent.py` pulls live weather from OpenWeatherMap, two Random Forest classifiers
(supervised) predict irrigation need (skip/light/heavy) and pest risk (low/fungal/mites_aphids), advice text follows.

## Run
    pip install -r requirements.txt
    python train.py                                   # builds model.joblib (Open-Meteo history, 8 climates, 2019-24)
    python agent.py                                   # demo: 2 offline scenarios -> 2 different recommendations
    set OWM_API_KEY=xxxx && python agent.py Ludhiana  # live (PowerShell: $env:OWM_API_KEY="xxxx")
    streamlit run app.py

## Deploy (Hugging Face Spaces, Docker SDK)
Create a Space (SDK: Docker), push this folder, add secret `OWM_API_KEY`. Port 7860 is set in the Dockerfile.

## Honest limits
- OWM free tier has no history, so training weather comes from Open-Meteo; features are OWM-compatible.
- Labels are NOT field observations: irrigation = FAO-56 ET0 water balance; pest = agronomy threshold rules.
  Pest accuracy (~99.9%) is high because the model re-learns those thresholds; irrigation (~91%) is the real test.
- Daily-mean training vs instantaneous live readings is an approximation. Advice is guidance, not agronomist sign-off.
