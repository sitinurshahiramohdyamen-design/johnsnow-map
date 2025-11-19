# app.py
import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

st.set_page_config(page_title="John Snow Cholera Map", layout="wide")
st.title("John Snow Cholera Map")

# --- Helpers ---
def find_latlon_cols(df):
    """Return (lat_col, lon_col) or (None, None)"""
    cols = [c.lower().strip() for c in df.columns]
    # common exact names or startswith
    lat_candidates = []
    lon_candidates = []
    for orig, c in zip(df.columns, cols):
        if c in ("lat", "latitude", "y", "y_coord", "ycoord", "y coordinate", "y_coordinate"):
            lat_candidates.append(orig)
        if c in ("lon", "lng", "long", "longitude", "x", "x_coord", "xcoord", "x coordinate", "x_coordinate"):
            lon_candidates.append(orig)
    # fallback: contains
    if not lat_candidates:
        lat_candidates = [orig for orig, c in zip(df.columns, cols) if "lat" in c or "y coordinate" in c]
    if not lon_candidates:
        lon_candidates = [orig for orig, c in zip(df.columns, cols) if "lon" in c or "lng" in c or "long" in c or "x coordinate" in c]
    lat = lat_candidates[0] if lat_candidates else None
    lon = lon_candidates[0] if lon_candidates else None
    return lat, lon

def safe_read_csv(uploaded):
    try:
        return pd.read_csv(uploaded)
    except Exception:
        # try reading as excel if csv fails
        try:
            uploaded.seek(0)
            return pd.read_excel(uploaded)
        except Exception as e:
            raise

def to_numeric_series_safe(s):
    """Convert series to numeric safely, return numeric series with NaNs dropped."""
    return pd.to_numeric(s, errors="coerce").dropna()

# --- UI ---
st.sidebar.header("Upload your files")
death_file = st.sidebar.file_uploader("Upload Death CSV (required)", type=["csv", "xlsx", "xls"])
pump_file = st.sidebar.file_uploader("Upload Pump CSV (optional)", type=["csv", "xlsx", "xls"])
use_example = st.sidebar.button("Load example sample")

if use_example:
    # small example
    df_death = pd.DataFrame({
        "id":[1,2,3,4,5],
        "X coordinate":[51.5136,51.5141,51.5133,51.5126,51.5139],
        "Y coordinate":[-0.1372,-0.1368,-0.1358,-0.1390,-0.1370],
        "notes":["d","d","d","d","d"]
    })
    df_pump = pd.DataFrame({
        "pump_id":[1,2,3],
        "X coordinate":[51.5136,51.5140,51.5125],
        "Y coordinate":[-0.1372,-0.1360,-0.1385],
        "name":["Pump A","Broad St Pump","Pump C"]
    })
else:
    df_death = None
    df_pump = None
    if death_file:
        try:
            df_death = safe_read_csv(death_file)
        except Exception as e:
            st.sidebar.error(f"Cannot read death file: {e}")
    if pump_file:
        try:
            df_pump = safe_read_csv(pump_file)
        except Exception as e:
            st.sidebar.error(f"Cannot read pump file: {e}")

# require death file
if df_death is None:
    st.info("Please upload the Death CSV on the left sidebar (or click 'Load example sample').")
    st.stop()

# detect lat/lon
d_lat, d_lon = find_latlon_cols(df_death)
if not d_lat or not d_lon:
    st.error(
        "Death CSV: Could not find latitude/longitude columns.\n"
        "Make sure columns are named like: lat/latitude/X coordinate/Y coordinate/longitude.\n\n"
        "Detected columns: " + ", ".join(df_death.columns.astype(str))
    )
    st.stop()

# convert numeric coords
df_death[d_lat] = pd.to_numeric(df_death[d_lat], errors="coerce")
df_death[d_lon] = pd.to_numeric(df_death[d_lon], errors="coerce")
df_death = df_death.dropna(subset=[d_lat, d_lon])
if df_death.empty:
    st.error("After converting coordinates to numbers, no valid death points remain.")
    st.stop()

# handle pumps if present
if df_pump is not None:
    p_lat, p_lon = find_latlon_cols(df_pump)
    if not p_lat or not p_lon:
        st.sidebar.warning("Pump CSV uploaded but lat/lon columns not found — pumps will be ignored.")
        df_pump = None
    else:
        df_pump[p_lat] = pd.to_numeric(df_pump[p_lat], errors="coerce")
        df_pump[p_lon] = pd.to_numeric(df_pump[p_lon], errors="coerce")
        df_pump = df_pump.dropna(subset=[p_lat, p_lon])
        if df_pump.empty:
            df_pump = None

# center map
center_lat = float(df_death[d_lat].mean())
center_lon = float(df_death[d_lon].mean())

# build map
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, control_scale=True)
folium.TileLayer("OpenStreetMap", name="OSM").add_to(m)
folium.TileLayer("Stamen Toner", name="Toner").add_to(m)
folium.TileLayer("Stamen Terrain", name="Terrain").add_to(m)

# deaths layer
fg_deaths = folium.FeatureGroup(name="Deaths (points)", show=True)
for _, r in df_death.iterrows():
    popup_items = []
    for c in df_death.columns:
        if c in (d_lat, d_lon):
            continue
        val = r.get(c, "")
        popup_items.append(f"<b>{c}</b>: {val}")
    popup_html = "<br>".join(popup_items)
    folium.CircleMarker(
        location=[r[d_lat], r[d_lon]],
        radius=5,
        fill=True,
        fill_opacity=0.8,
        color="red",
        popup=folium.Popup(popup_html, max_width=300)
    ).add_to(fg_deaths)
fg_deaths.add_to(m)

# heatmap
if len(df_death) >= 2:
    heat_data = df_death[[d_lat, d_lon]].values.tolist()
    HeatMap(heat_data, name="Heatmap (deaths)", radius=15, blur=10).add_to(m)

# pumps layer
if df_pump is not None:
    fg_pumps = folium.FeatureGroup(name="Pumps", show=True)
    for _, r in df_pump.iterrows():
        popup_items = []
        for c in df_pump.columns:
            if c in (p_lat, p_lon):
                continue
            popup_items.append(f"<b>{c}</b>: {r.get(c,'')}")
        popup_html = "<br>".join(popup_items)
        folium.Marker(
            location=[r[p_lat], r[p_lon]],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color="blue", icon="tint", prefix="fa")
        ).add_to(fg_pumps)
    fg_pumps.add_to(m)

folium.LayerControl().add_to(m)

# display
st.subheader("Map preview")
st.write("Toggle layers using 'Layers' on the map.")
st_data = st_folium(m, width=1000, height=650)

# show tables
with st.expander("Preview death data"):
    st.dataframe(df_death)

if df_pump is not None:
    with st.expander("Preview pump data"):
        st.dataframe(df_pump)

st.caption("If your CSV lacks coordinate columns, you'll need to add lat/lon (or X coordinate / Y coordinate) before uploading.")

