### START app.py
import streamlit as st
import pandas as pd
import numpy as np
import io
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

st.set_page_config(page_title="John Snow Cholera Map", layout="wide")
st.title("John Snow Cholera Map")

# ---------- Helpers ----------
def read_table(uploaded):
    """Read uploaded CSV or Excel returning DataFrame."""
    if uploaded is None:
        return None
    name = uploaded.name.lower()
    try:
        if name.endswith(".csv"):
            return pd.read_csv(uploaded)
        if name.endswith((".xls", ".xlsx")):
            return pd.read_excel(uploaded)
        # try csv as fallback
        uploaded.seek(0)
        return pd.read_csv(io.StringIO(uploaded.getvalue().decode("utf-8")))
    except Exception as e:
        st.error(f"Failed to read {uploaded.name}: {e}")
        return None

def candidate_columns(df):
    """Return list of candidate names for lat and lon based on column names."""
    cols = list(df.columns)
    lower = [c.lower() for c in cols]
    lat_keywords = ["lat", "latitude", "y", "y_coord", "ycoord", "y coordinate", "y_coordinate", "xcoord_lat"]
    lon_keywords = ["lon", "lng", "long", "longitude", "x", "x_coord", "xcoord", "x coordinate", "x_coordinate"]
    lat_candidates = [cols[i] for i,c in enumerate(lower) if any(k in c for k in lat_keywords)]
    lon_candidates = [cols[i] for i,c in enumerate(lower) if any(k in c for k in lon_keywords)]
    # also include columns that contain 'coordinate' even if not x/y
    if not lat_candidates:
        lat_candidates = [cols[i] for i,c in enumerate(lower) if "coordinate" in c and ("y" in c or "lat" in c or "x" in c)]
    if not lon_candidates:
        lon_candidates = [cols[i] for i,c in enumerate(lower) if "coordinate" in c and ("x" in c or "lon" in c or "long" in c)]
    return lat_candidates, lon_candidates

def pick_lat_lon(df):
    """Try to pick best lat & lon columns. Returns (lat_col, lon_col) or (None, None)."""
    lat_cands, lon_cands = candidate_columns(df)
    # try combinations
    for lat in lat_cands:
        for lon in lon_cands:
            try:
                lat_vals = pd.to_numeric(df[lat], errors="coerce")
                lon_vals = pd.to_numeric(df[lon], errors="coerce")
                lat_valid = lat_vals.dropna()
                lon_valid = lon_vals.dropna()
                if len(lat_valid) < 2 or len(lon_valid) < 2:
                    continue
                # check ranges
                if lat_valid.between(-90,90).all() and lon_valid.between(-180,180).all():
                    return lat, lon
                # sometimes X is latitude and Y is longitude (or swapped) — check swapped
                if lat_valid.between(-180,180).all() and lon_valid.between(-90,90).all():
                    # swapped, return swapped names but mark to swap later
                    return lat, lon
            except Exception:
                continue
    # fallback: try any numeric pair that fits ranges
    numeric_cols = []
    for c in df.columns:
        s = pd.to_numeric(df[c], errors="coerce")
        if s.dropna().shape[0] >= 2:
            numeric_cols.append(c)
    for i in range(len(numeric_cols)):
        for j in range(len(numeric_cols)):
            if i == j: continue
            a = pd.to_numeric(df[numeric_cols[i]], errors="coerce').dropna()
            b = pd.to_numeric(df[numeric_cols[j]], errors="coerce').dropna()
            if a.between(-90,90).all() and b.between(-180,180).all():
                return numeric_cols[i], numeric_cols[j]
    return None, None

def ensure_numeric(df, col):
    return pd.to_numeric(df[col], errors="coerce")

# ---------- UI ----------
st.sidebar.header("Upload your files")
death_file = st.sidebar.file_uploader("Upload Death CSV/Excel (required)", type=["csv","xls","xlsx"])
pump_file = st.sidebar.file_uploader("Upload Pump CSV/Excel (optional)", type=["csv","xls","xlsx"])
st.sidebar.markdown("If you don't have pumps file, leave blank. Use example button to test.")
if st.sidebar.button("Load example sample data"):
    # small example
    death_csv = """id,lat,lon,notes
1,51.5136,-0.1372,found near Broad St
2,51.5141,-0.1368,found near Broad St
3,51.5133,-0.1358,found near Broad St
"""
    pump_csv = """pump_id,lat,lon,name
1,51.5136,-0.1372,Broad St Pump
2,51.5140,-0.1360,Pump B
"""
    death_file = io.BytesIO(death_csv.encode())
    death_file.name = "example_death.csv"
    pump_file = io.BytesIO(pump_csv.encode())
    pump_file.name = "example_pump.csv"

df_death = read_table(death_file) if death_file else None
df_pump = read_table(pump_file) if pump_file else None

if df_death is None:
    st.warning("Please upload a Death CSV or Excel file on the left sidebar (required).")
    st.stop()

st.subheader("Death data preview")
st.dataframe(df_death.head())

if df_pump is not None:
    st.subheader("Pump data preview")
    st.dataframe(df_pump.head())

# ---------- Find lat/lon ----------
lat_col, lon_col = pick_lat_lon(df_death)
if lat_col is None or lon_col is None:
    st.error("Unable to detect lat/lon columns in death data. Common names: lat, latitude, x coordinate, y coordinate, lon, long, longitude. Please rename your columns or upload CSV with lat & lon.")
    st.stop()

# Convert to numeric
df_death[lat_col] = ensure_numeric(df_death, lat_col)
df_death[lon_col] = ensure_numeric(df_death, lon_col)

# If values clearly swapped (e.g., lat outside -90..90), try swap detection:
if not df_death[lat_col].between(-90,90).all() and df_death[lon_col].between(-90,90).all():
    # swap
    df_death["_tmp_lat"] = df_death[lat_col]
    df_death[lat_col] = df_death[lon_col]
    df_death[lon_col] = df_death["_tmp_lat"]
    df_death = df_death.drop(columns=["_tmp_lat"])
    st.info("Detected lat/lon were swapped; columns swapped automatically.")

center_lat = df_death[lat_col].mean()
center_lon = df_death[lon_col].mean()

# Prepare map
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, control_scale=True)
folium.TileLayer("OpenStreetMap", name="OSM").add_to(m)
folium.TileLayer("Stamen Terrain", name="Terrain").add_to(m)
folium.TileLayer("Stamen Toner", name="Toner").add_to(m)

# Deaths layer
fg_deaths = folium.FeatureGroup(name="Deaths (points)", show=True)
for _, r in df_death.dropna(subset=[lat_col, lon_col]).iterrows():
    popup = "<br>".join([f"<b>{c}</b>: {r[c]}" for c in df_death.columns if c not in (lat_col, lon_col)])
    folium.CircleMarker(location=[r[lat_col], r[lon_col]], radius=5, fill=True, fill_opacity=0.8, color="red", popup=folium.Popup(popup, max_width=300)).add_to(fg_deaths)
fg_deaths.add_to(m)

# Heatmap
coords = df_death.dropna(subset=[lat_col, lon_col])[[lat_col, lon_col]].values.tolist()
if len(coords) >= 2:
    HeatMap(coords, name="Heatmap (deaths)", radius=15, blur=10).add_to(m)

# Pumps
if df_pump is not None:
    # detect pump lat/lon similarly
    p_lat, p_lon = pick_lat_lon(df_pump)
    if p_lat is None or p_lon is None:
        st.warning("Pump file found but could not detect lat/lon columns in pump data. Pumps not shown.")
    else:
        df_pump[p_lat] = ensure_numeric(df_pump, p_lat)
        df_pump[p_lon] = ensure_numeric(df_pump, p_lon)
        fg_pumps = folium.FeatureGroup(name="Pumps", show=True)
        for _, r in df_pump.dropna(subset=[p_lat, p_lon]).iterrows():
            popup = "<br>".join([f"<b>{c}</b>: {r[c]}" for c in df_pump.columns if c not in (p_lat, p_lon)])
            folium.Marker(location=[r[p_lat], r[p_lon]], popup=folium.Popup(popup, max_width=300), icon=folium.Icon(color="blue", icon="tint", prefix="fa")).add_to(fg_pumps)
        fg_pumps.add_to(m)

folium.LayerControl().add_to(m)

st.subheader("Interactive map")
st.write("Gunakan zoom & pan. Toggle layers pada 'Layers'.")
st_folium(m, width=900, height=600)
### END app.py
