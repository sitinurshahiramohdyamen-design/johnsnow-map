# app.py
import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from io import BytesIO

st.set_page_config(page_title="John Snow Cholera Map", layout="wide")
st.title("John Snow Cholera Map")

# --- Helpers ---
def find_latlon_cols(df):
    """
    Return (lat_col, lon_col) or (None, None).
    Heuristics:
    - Look for common names (lat, latitude, y, Y coordinate, etc)
    - Look for common lon names (lon, lng, long, x, X coordinate)
    - If ambiguous or swapped, use numeric ranges to guess:
        lat in [-90, 90], lon in [-180, 180]
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

    # pick first candidate if exists
    lat = lat_candidates[0] if lat_candidates else None
    lon = lon_candidates[0] if lon_candidates else None

    # If both found, but values look swapped (e.g., X coordinate contains typical lat values),
    # use numeric heuristics to detect correct assignment
    if lat and lon:
        try:
            # try convert to numeric (coerce)
            lat_vals = pd.to_numeric(df[lat], errors="coerce").dropna()
            lon_vals = pd.to_numeric(df[lon], errors="coerce").dropna()
            if not lat_vals.empty and not lon_vals.empty:
                lat_mean = lat_vals.abs().mean()
                lon_mean = lon_vals.abs().mean()
                # lat should be <= 90 normally; lon can be <= 180
                lat_in_lat_range = lat_vals.between(-90, 90).mean()  # fraction of values in lat range
                lon_in_lon_range = lon_vals.between(-180, 180).mean()
                lat_in_lon_range = lat_vals.between(-180, 180).mean()
                lon_in_lat_range = lon_vals.between(-90, 90).mean()
                # if both columns fall mostly into lat range but one is named X coordinate,
                # choose based on fraction heuristics
                if (lat_in_lat_range < 0.6 and lon_in_lat_range > 0.6) or (lat_in_lat_range < lon_in_lat_range and lon_in_lat_range > 0.6):
                    # likely swapped
                    return lon, lat
                # otherwise keep as detected
        except Exception:
            pass

    return lat, lon


def safe_read_csv(uploaded):
    """
    Read uploaded CSV/Excel file robustly.
    `uploaded` is a Streamlit UploadedFile.
    """
    try:
        uploaded.seek(0)
    except Exception:
        pass
    # try CSV first
    try:
        # accept different encodings; keep it simple
        return pd.read_csv(uploaded)
    except Exception:
        try:
            uploaded.seek(0)
            return pd.read_excel(uploaded)
        except Exception as e:
            # raise to the caller for display
            raise


# --- UI ---
st.sidebar.header("Upload your files")
death_file = st.sidebar.file_uploader("Upload Death CSV (required)", type=["csv", "xlsx", "xls"])
pump_file = st.sidebar.file_uploader("Upload Pump CSV (optional)", type=["csv", "xlsx", "xls"])
use_example = st.sidebar.button("Load example sample")

if use_example:
    # small example (London-ish coordinates)
    df_death = pd.DataFrame({
        "id":[1,2,3,4,5],
        "lat":[51.5136,51.5141,51.5133,51.5126,51.5139],
        "lon":[-0.1372,-0.1368,-0.1358,-0.1390,-0.1370],
        "notes":["d","d","d","d","d"]
    })
    df_pump = pd.DataFrame({
        "pump_id":[1,2,3],
        "lat":[51.5136,51.5140,51.5125],
        "lon":[-0.1372,-0.1360,-0.1385],
        "name":["Pump A","Broad St Pump","Pump C"]
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

# center map (mean)
center_lat = float(df_death[d_lat].mean())
center_lon = float(df_death[d_lon].mean())

# --- Diagnostics (show to user so we can verify coordinate columns) ---
st.sidebar.markdown("### Diagnostics — coordinate check")
st.sidebar.write(f"Detected death lat column: **{d_lat}**")
st.sidebar.write(f"Detected death lon column: **{d_lon}**")

# compute simple stats
dlat_vals = pd.to_numeric(df_death[d_lat], errors="coerce")
dlon_vals = pd.to_numeric(df_death[d_lon], errors="coerce")
st.sidebar.write("Death coords summary (min / mean / max):")
st.sidebar.write({
    d_lat: (float(dlat_vals.min()), float(dlat_vals.mean()), float(dlat_vals.max())),
    d_lon: (float(dlon_vals.min()), float(dlon_vals.mean()), float(dlon_vals.max())),
})

# fractions inside expected ranges
frac_lat_ok = dlat_vals.between(-90,90).mean()
frac_lon_ok = dlon_vals.between(-180,180).mean()
st.sidebar.write(f"Fraction {d_lat} in [-90,90]: **{frac_lat_ok:.2f}**")
st.sidebar.write(f"Fraction {d_lon} in [-180,180]: **{frac_lon_ok:.2f}**")

# Auto-suggest swap if suspicious
suspect_swap = (frac_lat_ok < 0.6 and frac_lon_ok < 0.6) or (dlat_vals.abs().mean() > dlon_vals.abs().mean() and dlon_vals.between(-90,90).mean() > 0.6)
if suspect_swap:
    st.sidebar.warning("Coordinates look suspicious (possible lat/lon swapped). Consider flipping.")

flip_coords = st.sidebar.checkbox("Flip coordinates (use lon as lat, lat as lon)", value=False)
if flip_coords:
    # swap names for plotting only (do NOT modify original DF on disk)
    d_lat, d_lon = d_lon, d_lat
    st.sidebar.success(f"Swapped. Now treating {d_lat} as lat and {d_lon} as lon.")


# build folium map
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, control_scale=True)

# Add a single stable base map (OpenStreetMap), and optionally add Stamen with attribution
folium.TileLayer(tiles="OpenStreetMap", name="OpenStreetMap").add_to(m)

# Add Stamen Terrain as optional layer with proper attribution to avoid ValueError
try:
    folium.TileLayer(
        tiles="Stamen Terrain",
        name="Stamen Terrain",
        attr="Map tiles by Stamen Design, under CC BY 3.0. Data by OpenStreetMap contributors"
    ).add_to(m)
except ValueError:
    # fallback already have OSM
    pass

# deaths layer (points)
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

# heatmap (if enough points)
if len(df_death) >= 2:
    # folium HeatMap expects list of [lat, lon]
    heat_data = df_death[[d_lat, d_lon]].values.tolist()
    HeatMap(heat_data, name="Heatmap (deaths)", radius=15, blur=10).add_to(m)

# pumps layer (optional)
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

folium.LayerControl().add_to(m)

# display map
st.subheader("Map preview")
st.write("Toggle layers using the 'Layers' control on the map.")
st_data = st_folium(m, width=1000, height=650)

# show tables
with st.expander("Preview death data"):
    st.dataframe(df_death)

if df_pump is not None:
    with st.expander("Preview pump data"):
        st.dataframe(df_pump)

st.caption("If your CSV lacks coordinate columns, you'll need to add lat/lon (or X coordinate / Y coordinate) before uploading.")

