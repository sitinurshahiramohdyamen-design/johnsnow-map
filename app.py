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
    """
    Return (lat_col, lon_col) or (None, None).
    Heuristics:
    - Look for common names (lat, latitude, y, Y coordinate, etc)
    - Look for common lon names (lon, lng, long, x, X coordinate)
    - If ambiguous, use numeric heuristics to detect swapped columns
    """
    cols_lower = [c.lower().strip() for c in df.columns]
    lat_candidates = []
    lon_candidates = []
    for orig, c in zip(df.columns, cols_lower):
        if c in ("lat", "latitude", "y", "y_coord", "ycoord", "y coordinate", "y_coordinate"):
            lat_candidates.append(orig)
        if c in ("lon", "lng", "long", "longitude", "x", "x_coord", "xcoord", "x coordinate", "x_coordinate"):
            lon_candidates.append(orig)

    # fallback: contains keyword
    if not lat_candidates:
        lat_candidates = [orig for orig, c in zip(df.columns, cols_lower) if "lat" in c or "y coordinate" in c]
    if not lon_candidates:
        lon_candidates = [orig for orig, c in zip(df.columns, cols_lower) if "lon" in c or "lng" in c or "long" in c or "x coordinate" in c]

    lat = lat_candidates[0] if lat_candidates else None
    lon = lon_candidates[0] if lon_candidates else None

    # If both found, try detect swapped by numeric ranges
    if lat and lon:
        try:
            lat_vals = pd.to_numeric(df[lat], errors="coerce").dropna()
            lon_vals = pd.to_numeric(df[lon], errors="coerce").dropna()
            if not lat_vals.empty and not lon_vals.empty:
                lat_in_lat_range = lat_vals.between(-90, 90).mean()
                lon_in_lon_range = lon_vals.between(-180, 180).mean()
                lat_in_lon_range = lat_vals.between(-180, 180).mean()
                lon_in_lat_range = lon_vals.between(-90, 90).mean()
                # if detected lat mostly outside lat range but detected lon mostly inside lat range -> swapped
                if (lat_in_lat_range < 0.6 and lon_in_lat_range > 0.6) or (lat_in_lat_range < lon_in_lat_range and lon_in_lat_range > 0.6):
                    return lon, lat
        except Exception:
            pass

    return lat, lon


def safe_read_csv(uploaded):
    """
    Read uploaded CSV/Excel file robustly.
    """
    try:
        uploaded.seek(0)
    except Exception:
        pass
    try:
        return pd.read_csv(uploaded)
    except Exception:
        try:
            uploaded.seek(0)
            return pd.read_excel(uploaded)
        except Exception as e:
            raise


# --- UI inputs ---
st.sidebar.header("Upload your files")
death_file = st.sidebar.file_uploader("Upload Death CSV (required)", type=["csv", "xlsx", "xls"])
pump_file = st.sidebar.file_uploader("Upload Pump CSV (optional)", type=["csv", "xlsx", "xls"])
use_example = st.sidebar.button("Load example sample")

# example dataset (London-like) if user wants quick preview
if use_example:
    df_death = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "lat": [51.5136, 51.5141, 51.5133, 51.5126, 51.5139],
        "lon": [-0.1372, -0.1368, -0.1358, -0.1390, -0.1370],
        "notes": ["d", "d", "d", "d", "d"],
    })
    df_pump = pd.DataFrame({
        "pump_id": [1, 2, 3],
        "lat": [51.5136, 51.5140, 51.5125],
        "lon": [-0.1372, -0.1360, -0.1385],
        "name": ["Pump A", "Broad St Pump", "Pump C"],
    })
else:
    df_death = None
    df_pump = None
    if death_file is not None:
        try:
            df_death = safe_read_csv(death_file)
        except Exception as e:
            st.sidebar.error(f"Cannot read death file: {e}")
    if pump_file is not None:
        try:
            df_pump = safe_read_csv(pump_file)
        except Exception as e:
            st.sidebar.error(f"Cannot read pump file: {e}")

# require death file
if df_death is None:
    st.info("Please upload the Death CSV on the left sidebar (or click 'Load example sample').")
    st.stop()

# detect lat/lon for deaths
d_lat, d_lon = find_latlon_cols(df_death)
if not d_lat or not d_lon:
    st.error(
        "Death CSV: Could not find latitude/longitude columns.\n"
        "Make sure columns are named like: lat/latitude/X coordinate/Y coordinate/longitude.\n\n"
        "Detected columns: " + ", ".join(df_death.columns.astype(str))
    )
    st.stop()

# diagnostics and flip option (so user can verify)
st.sidebar.markdown("### Diagnostics — coordinate check")
st.sidebar.write(f"Detected death lat column: **{d_lat}**")
st.sidebar.write(f"Detected death lon column: **{d_lon}**")

# compute stats for diagnostics
dlat_vals = pd.to_numeric(df_death[d_lat], errors="coerce")
dlon_vals = pd.to_numeric(df_death[d_lon], errors="coerce")
try:
    st.sidebar.write("Death coords summary (min / mean / max):")
    st.sidebar.write({
        d_lat: (float(dlat_vals.min()), float(dlat_vals.mean()), float(dlat_vals.max())),
        d_lon: (float(dlon_vals.min()), float(dlon_vals.mean()), float(dlon_vals.max())),
    })
except Exception:
    pass

# fraction inside reasonable ranges
frac_lat_ok = dlat_vals.between(-90, 90).mean()
frac_lon_ok = dlon_vals.between(-180, 180).mean()
st.sidebar.write(f"Fraction {d_lat} in [-90,90]: **{frac_lat_ok:.2f}**")
st.sidebar.write(f"Fraction {d_lon} in [-180,180]: **{frac_lon_ok:.2f}**")

# auto-suggest swap
suspect_swap = (frac_lat_ok < 0.6 and frac_lon_ok < 0.6) or (dlat_vals.abs().mean() > dlon_vals.abs().mean() and dlon_vals.between(-90,90).mean() > 0.6)
if suspect_swap:
    st.sidebar.warning("Coordinates look suspicious (possible lat/lon swapped). Consider flipping.")

flip_coords = st.sidebar.checkbox("Flip coordinates (use lon as lat, lat as lon)", value=False)
if flip_coords:
    d_lat, d_lon = d_lon, d_lat
    st.sidebar.success(f"Swapped temporarily for display. Now treating **{d_lat}** as latitude and **{d_lon}** as longitude.")

# convert coords to numeric and drop invalid
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

# center (mean)
center_lat = float(df_death[d_lat].mean())
center_lon = float(df_death[d_lon].mean())

# Build folium map with explicit base layers (tiles=None so we control default)
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, control_scale=True, tiles=None)

# ===== HTTPS-safe basemaps (fixes Streamlit tile-blocking) =====
folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    attr="© OpenStreetMap contributors",
    name="OpenStreetMap",
    show=True
).add_to(m)

folium.TileLayer(
    tiles="https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
    name="Positron (light)",
    attr="© CartoDB © OpenStreetMap contributors",
    show=False
).add_to(m)

folium.TileLayer(
    tiles="https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
    name="Stamen Terrain",
    attr="Map tiles by Stamen Design — © OpenStreetMap contributors",
    show=False
).add_to(m)
# ===============================================================

# --- overlays: deaths (points) ---
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

# heatmap overlay (if enough points)
if len(df_death) >= 2:
    heat_data = df_death[[d_lat, d_lon]].values.tolist()
    HeatMap(heat_data, name="Heatmap (deaths)", radius=12, blur=8).add_to(m)

# pumps overlay
if df_pump is not None:
    p_lat, p_lon = find_latlon_cols(df_pump)
    if p_lat and p_lon:
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

# add layer control (shows base layers as radio buttons and overlays as checkboxes)
folium.LayerControl(position="topright", collapsed=False).add_to(m)

# fit map to bounds of data (safe-guard)
try:
    bounds = [
        [float(df_death[d_lat].min()), float(df_death[d_lon].min())],
        [float(df_death[d_lat].max()), float(df_death[d_lon].max())],
    ]
    m.fit_bounds(bounds)
except Exception:
    pass

# display map
st.subheader("Map preview")
st.write("Toggle layers using the 'Layers' control on the map.")
st_data = st_folium(m, width=1000, height=650)

# show preview tables
with st.expander("Preview death data"):
    st.dataframe(df_death.reset_index(drop=True))

if df_pump is not None:
    with st.expander("Preview pump data"):
        st.dataframe(df_pump.reset_index(drop=True))

st.caption("If your CSV lacks coordinate columns, add lat/lon (or X coordinate / Y coordinate) before uploading. Use the Diagnostics sidebar to verify and flip coordinates if needed.")
