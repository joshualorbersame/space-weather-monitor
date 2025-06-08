# kp_warner_streamlit.py

import streamlit as st
import requests
import datetime
import time
from PIL import Image
from io import BytesIO
from streamlit_autorefresh import st_autorefresh

# --------------------------------------------------------
# Seiten- & Refresh-Konfiguration
# --------------------------------------------------------
st.set_page_config(
    page_title="Live Space Weather Monitor – Hessen",
    layout="wide",
    page_icon="🛰"
)
REFRESH_INTERVAL_S      = 300     # Cache alle 300 s
AUTOREFRESH_INTERVAL_MS = 1000    # UI prüft jede Sekunde
st_autorefresh(interval=AUTOREFRESH_INTERVAL_MS, limit=None, key="auto_refresh")

# --------------------------------------------------------
# Endpunkte
# --------------------------------------------------------
KP3HR_URL   = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json"
MAG_URL     = "https://services.swpc.noaa.gov/products/solar-wind/mag-5-minute.json"
UV_API_URL  = "http://api.openweathermap.org/data/2.5/uvi"
UV_LAT, UV_LON = 50.7, 9.3  # Hessen

IMAGE_SOURCES = {
    "SDO – Intensity (Fleckenzahl)":   "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIF.jpg",
    "SDO – Magnetogramm (HMI B-Kanal)": "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIBC.jpg",
    "SOHO – Korona (LASCO C3)":         "https://soho.nascom.nasa.gov/data/LATEST/current_c3.gif",
}

# --------------------------------------------------------
# Hilfsfunktion zum Entfernen von Header
# --------------------------------------------------------
def _strip_header(rows):
    if rows and isinstance(rows[0], list) and all(isinstance(x, str) for x in rows[0]):
        return rows[1:]
    return rows

# --------------------------------------------------------
# Datenabruf
# --------------------------------------------------------
@st.cache_data(ttl=REFRESH_INTERVAL_S)
def fetch_kp3hr():
    resp = requests.get(KP3HR_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    # List-of-Lists mit Header?
    if isinstance(data, list) and data and isinstance(data[0], list):
        header = data[0]
        rows   = _strip_header(data)
        time_idx = next(i for i,h in enumerate(header) if "time_tag" in h.lower())
        kp_idx   = next(i for i,h in enumerate(header) if h.lower().startswith("kp"))
        last = rows[-1]
        time_tag, kp_val = last[time_idx], last[kp_idx]
    # oder List-of-Dicts?
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        last     = data[-1]
        time_tag = last.get("time_tag")
        kp_val   = last.get("kp_index", last.get("kp", 0.0))
    else:
        st.error("Unbekanntes Format für Kp-3hr-Daten")
        return 0.0, datetime.datetime.utcnow()
    dt = datetime.datetime.fromisoformat(time_tag.replace("Z", "+00:00"))
    ts = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return float(kp_val), ts

@st.cache_data(ttl=REFRESH_INTERVAL_S)
def fetch_bz():
    resp = requests.get(MAG_URL, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list) and data and isinstance(data[0], list):
        header = data[0]
        rows   = _strip_header(data)
        ti  = header.index("time_tag")
        bzi = header.index("bz_gse") if "bz_gse" in header else header.index("bz_gsm")
        last        = rows[-1]
        time_tag, bz_val = last[ti], last[bzi]
    else:
        st.error("Unbekanntes Format für Magnetometer-Daten")
        return 0.0, datetime.datetime.utcnow()
    dt = datetime.datetime.fromisoformat(time_tag.replace("Z", "+00:00"))
    ts = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return float(bz_val), ts

@st.cache_data(ttl=3600)
def fetch_uv():
    # Kein API-Schlüssel = überspringen
    try:
        key = st.secrets["OWM_UV_KEY"]
    except Exception:
        return None, None
    params = {"lat": UV_LAT, "lon": UV_LON, "appid": key}
    resp = requests.get(UV_API_URL, params=params, timeout=10)
    resp.raise_for_status()
    data     = resp.json()
    time_tag = data.get("date_iso")
    uv_val   = data.get("value")
    dt = datetime.datetime.fromisoformat(time_tag.replace("Z", "+00:00"))
    ts = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return float(uv_val), ts

@st.cache_data(ttl=REFRESH_INTERVAL_S)
def load_image(url: str):
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    lm = resp.headers.get("Last-Modified")
    if lm:
        try:
            dt = datetime.datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z")
            ts = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except:
            ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    img = Image.open(BytesIO(resp.content))
    w,h = img.size
    img = img.resize((600, int(h * 600 / w)), Image.LANCZOS)
    return img, ts

# --------------------------------------------------------
# Interpretations-Logik
# --------------------------------------------------------
def interpret_kp(kp):
    if kp < 4:    return "Ruhe – keine Störung", "🟢", "green"
    if kp < 6:    return "Erhöhte Aktivität (4–5)", "🟡", "gold"
    return "Starker Sturm (G3+)", "🔴", "red"

def interpret_bz(bz):
    if bz > 0:    return "Magnetfeld geschlossen", "🟢", "green"
    if bz >= -5:  return "Magnetfeld offen",     "🟡", "gold"
    return "Magnetfeld stark offen",             "🟠", "orange"

def interpret_uv(uv):
    if uv is None: return "UV-Daten nicht verfügbar", "❔", "grey"
    if uv <= 2:    return "UV niedrig",  "🟢", "green"
    if uv <= 5:    return "UV moderat",  "🟡", "gold"
    if uv <= 7:    return "UV hoch",     "🟠", "orange"
    return "UV sehr hoch",                "🔴", "red"

def combine_status(cols):
    order  = ["grey","green","gold","orange","red"]
    emojis = {"grey":"❔","green":"🟢","gold":"🟡","orange":"🟠","red":"🔴"}
    texts  = {
        "grey":   "Teilweise unvollständig",
        "green":  "Alles im grünen Bereich",
        "gold":   "Erhöhte Vorsicht",
        "orange": "Hohe Vorsicht",
        "red":    "Kritischer Zustand!"
    }
    worst = max(cols, key=lambda c: order.index(c))
    return emojis[worst], texts[worst], worst

# --------------------------------------------------------
# UI-Aufbau
# --------------------------------------------------------
st.title("🛰 Live Space Weather Monitor – Hessen (Germany)")

# Metriken abrufen
kp_val, kp_ts = fetch_kp3hr()
bz_val, bz_ts = fetch_bz()
uv_val, uv_ts = fetch_uv()

# interpretieren
kp_txt, kp_emo, kp_col = interpret_kp(kp_val)
bz_txt, bz_emo, bz_col = interpret_bz(bz_val)
uv_txt, uv_emo, uv_col = interpret_uv(uv_val)
comb_emo, comb_txt, comb_col = combine_status([kp_col, bz_col, uv_col])

# Anzeige
c1,c2,c3,c4 = st.columns(4)
with c1:
    st.markdown(f"<h3 style='color:{kp_col};'>{kp_emo} Kp = {kp_val:.1f} · {kp_txt}</h3>", unsafe_allow_html=True)
    st.write(f"Stand: {kp_ts:%Y-%m-%d %H:%M} UTC")
with c2:
    st.markdown(f"<h3 style='color:{bz_col};'>{bz_emo} Bz = {bz_val:.1f} nT · {bz_txt}</h3>", unsafe_allow_html=True)
    st.write(f"Stand: {bz_ts:%Y-%m-%d %H:%M} UTC")
with c3:
    st.markdown(f"<h3 style='color:{uv_col};'>{uv_emo} UV = {uv_val if uv_val is not None else '–'} · {uv_txt}</h3>", unsafe_allow_html=True)
    if uv_ts:
        st.write(f"Stand: {uv_ts:%Y-%m-%d %H:%M} UTC")
with c4:
    st.markdown(f"<h3 style='color:{comb_col};'>{comb_emo} Systemstatus</h3>", unsafe_allow_html=True)
    st.write(comb_txt)

# Manuell aktualisieren & Countdown
if st.button("🔄 Manuell aktualisieren"):
    st.experimental_rerun()
next_fetch = ((int(time.time()) // REFRESH_INTERVAL_S) + 1) * REFRESH_INTERVAL_S
st.markdown(f"⏳ Nächster Fetch in **{max(int(next_fetch - time.time()), 0)} Sek.**")

st.markdown("---")

# Live-Bilder
cols = st.columns(len(IMAGE_SOURCES))
for (label, url), col in zip(IMAGE_SOURCES.items(), cols):
    with col:
        st.markdown(f"**{label}**")
        if url.lower().endswith(".gif"):
            st.image(url, use_container_width=True, caption=f"{label} (animiert)")
        else:
            img, ts = load_image(url)
            st.image(img, use_container_width=True)
            st.caption(f"{label} {ts}")

st.markdown("---")
st.write("*Datenquellen: NOAA SWPC (3-Std-Kp & 5-Min-Mag), OpenWeatherMap (UV optional), SDO & SOHO*")