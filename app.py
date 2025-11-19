import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium
from branca.element import Template, MacroElement

st.set_page_config(page_title="John Snow Cholera Map", layout="wide")

st.title("John Snow Cholera Map")
st.markdown("Layer boleh toggle atas peta. Kalau tiada paparan, cuba refresh atau tukar browser.")

# ========== Demo Data (Ganti dengan Upload/CSV anda) ==========
df_death = pd.DataFrame({
    "id": [1,2,3,4,5],
    "lat": [51.5136,51.5141,51.5133,51.5126,51.5139],
    "lon": [-0.1372,-0.1368,-0.1358,-0.1390,-0.1370],
    "notes": ["d","d","d","d","d"]
})
df_pump = pd.DataFrame({
    "pump_id":[1,2,3],
    "lat":[51.5136,51.5140,51.5125],
    "lon":[-0.1372,-0.1360,-0.1385],
    "name":["Pump A","Broad St Pump","Pump C"]
})

center_lat = df_death['lat'].mean()
center_lon = df_death['lon'].mean()

# ========== Folium Map Setup - with HTTPS Tiles & Attribution ==========
m = folium.Map(location=[center_lat, center_lon], zoom_start=16, tiles=None)
folium.TileLayer(
    tiles="https://cartodb-basemaps-a.global.ssl.fastly.net/light_all/{z}/{x}/{y}.png",
    name="Positron (light)",
    attr="© CartoDB © OpenStreetMap contributors",
    show=True
).add_to(m)
folium.TileLayer(
    tiles="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    name="OpenStreetMap",
    attr="© OpenStreetMap contributors",
    show=False
).add_to(m)
folium.TileLayer(
    tiles="https://stamen-tiles.a.ssl.fastly.net/terrain/{z}/{x}/{y}.jpg",
    name="Stamen Terrain",
    attr="Map tiles by Stamen Design — © OpenStreetMap contributors",
    show=False
).add_to(m)

# ========== Death Points ==========
fg_death = folium.FeatureGroup(name="Deaths (points)", show=True)
for _, r in df_death.iterrows():
    folium.CircleMarker(
        location=[r["lat"], r["lon"]],
        radius=5, color="red", fill=True, popup=f"ID: {r['id']}<br>Notes: {r['notes']}"
    ).add_to(fg_death)
fg_death.add_to(m)

# ========== Heatmap (deaths) ==========
if len(df_death) > 1:
    HeatMap(df_death[["lat", "lon"]].values.tolist(), name="Heatmap (deaths)", radius=10).add_to(m)

# ========== Pump Points ==========
fg_pump = folium.FeatureGroup(name="Pumps", show=True)
for _, r in df_pump.iterrows():
    folium.Marker(
        location=[r["lat"], r["lon"]],
        popup=r["name"], icon=folium.Icon(color="blue", icon="tint", prefix="fa")
    ).add_to(fg_pump)
fg_pump.add_to(m)

# ========== Layer Control ==========
folium.LayerControl(position="topright", collapsed=False).add_to(m)

# ========== Legend Custom ==========
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

# ========== Auto-Fit to Data ==========
bounds = [
    [df_death["lat"].min(), df_death["lon"].min()],
    [df_death["lat"].max(), df_death["lon"].max()]
]
m.fit_bounds(bounds, padding=(30, 30))

# ========== Show Map ==========
st_data = st_folium(m, width=1000, height=650)

with st.expander("Preview death data"):
    st.dataframe(df_death)
with st.expander("Preview pump data"):
    st.dataframe(df_pump)
