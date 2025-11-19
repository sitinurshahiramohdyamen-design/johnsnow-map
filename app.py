import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from branca.element import Template, MacroElement

st.set_page_config(page_title="John Snow Cholera Map", layout="wide")
st.title("John Snow Cholera Map")
st.markdown("Layer boleh toggle atas peta. Kalau tiada paparan, cuba refresh atau tukar browser.")

# Fungsi auto-detect lat/lon/X/Y coordinate
def find_latlon_cols(df):
    cols_lower = [c.lower().replace(" ", "") for c in df.columns]
    lat = None
    lon = None
    for orig, c in zip(df.columns, cols_lower):
        if c in ("lat", "latitude", "y", "ycoord", "ycoordinate"):
            lat = orig
        if c in ("lon", "lng", "long", "longitude", "x", "xcoord", "xcoordinate"):
            lon = orig
    return lat, lon

# Sidebar upload file
st.sidebar.header("UPLOAD FILE")
death_file = st.sidebar.file_uploader("Upload Death CSV (wajib)", type=["csv", "xlsx"])
pump_file = st.sidebar.file_uploader("Upload Pump CSV (opsyenal)", type=["csv", "xlsx"])

# Baca fail death
if death_file is not None:
    if death_file.name.endswith(".csv"):
        df_death = pd.read_csv(death_file)
    else:
        df_death = pd.read_excel(death_file)
else:
    st.info("Sila upload Death CSV di sidebar.")
    st.stop()

# Baca fail pump (kalau ada)
if pump_file is not None:
    if pump_file.name.endswith(".csv"):
        df_pump = pd.read_csv(pump_file)
    else:
        df_pump = pd.read_excel(pump_file)
else:
    df_pump = None

# Detect kolum lat/lon
d_lat, d_lon = find_latlon_cols(df_death)
if not d_lat or not d_lon:
    st.error(f"Tak jumpa latitude/longitude. Kolum: {', '.join(df_death.columns)}")
    st.stop()

# Convert ke numeric dan buang NA
df_death[d_lat] = pd.to_numeric(df_death[d_lat], errors="coerce")
df_death[d_lon] = pd.to_numeric(df_death[d_lon], errors="coerce")
df_death = df_death.dropna(subset=[d_lat, d_lon])

if df_pump is not None:
    p_lat, p_lon = find_latlon_cols(df_pump)
    if p_lat and p_lon:
        df_pump[p_lat] = pd.to_numeric(df_pump[p_lat], errors="coerce")
        df_pump[p_lon] = pd.to_numeric(df_pump[p_lon], errors="coerce")
        df_pump = df_pump.dropna(subset=[p_lat, p_lon])

# Center map ikut mean death
center_lat = float(df_death[d_lat].mean())
center_lon = float(df_death[d_lon].mean())

# Folium Map dengan HTTPS Tiles dan Attribution
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, tiles=None)
folium.TileLayer(
    tiles="https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
    name="Positron (light)", attr="© CartoDB © OpenStreetMap contributors", show=True
).add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    name="OpenStreetMap", attr="© OpenStreetMap contributors", show=False
).add_to(m)
folium.TileLayer(
    tiles="https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
    name="Stamen Terrain", attr="Map tiles by Stamen Design — © OpenStreetMap contributors",
    show=False
).add_to(m)

# Death points
fg_death = folium.FeatureGroup(name="Deaths (points)", show=True)
for _, r in df_death.iterrows():
    popup = "<br>".join([f"<b>{col}</b>: {r[col]}" for col in df_death.columns if col not in (d_lat, d_lon)])
    folium.CircleMarker(
        location=[r[d_lat], r[d_lon]], radius=5, color="red", fill=True,
        popup=folium.Popup(popup, max_width=300)
    ).add_to(fg_death)
fg_death.add_to(m)

# Heatmap
if len(df_death) > 1:
    HeatMap(df_death[[d_lat, d_lon]].values.tolist(), name="Heatmap (deaths)", radius=10, blur=6).add_to(m)

# Pumps
if df_pump is not None and p_lat and p_lon:
    fg_pump = folium.FeatureGroup(name="Pumps", show=True)
    for _, r in df_pump.iterrows():
        popup = "<br>".join([f"<b>{col}</b>: {r[col]}" for col in df_pump.columns if col not in (p_lat, p_lon)])
        folium.Marker(
            location=[r[p_lat], r[p_lon]],
            popup=folium.Popup(popup, max_width=300),
            icon=folium.Icon(color="blue", icon="tint", prefix="fa")
        ).add_to(fg_pump)
    fg_pump.add_to(m)

folium.LayerControl(position="topright", collapsed=False).add_to(m)

legend_html = """
{% macro html(this, kwargs) %}
<div style="
    position: absolute; 
    z-index:9999; 
    background-color: white;
    padding: 10px;
    border-radius: 6px;
    box-shadow: 0 0 6px rgba(0,0,0,0.3);
    font-size:12px;
    right: 30px; top: 90px;">
<b>Legend</b><br>
<span style="background:#ff0000;border-radius:50%;display:inline-block;width:12px;height:12px;margin-right:6px;"></span> Death points<br>
<span style="color:blue; margin-left:2px;">●</span> Pump (blue marker)<br>
</div>
{% endmacro %}
"""
macro = MacroElement()
macro._template = Template(legend_html)
m.get_root().add_child(macro)

# Fit map ke semua death
bounds = [
    [df_death[d_lat].min(), df_death[d_lon].min()],
    [df_death[d_lat].max(), df_death[d_lon].max()]
]
m.fit_bounds(bounds, padding=(30, 30))

# Output peta
st.subheader("Map preview")
st_data = st_folium(m, width=1000, height=650)
with st.expander("Preview death data"):
    st.dataframe(df_death)
if df_pump is not None:
    with st.expander("Preview pump data"):
        st.dataframe(df_pump)
