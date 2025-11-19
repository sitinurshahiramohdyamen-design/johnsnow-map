import streamlit as st
import pandas as pd
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

st.title("John Snow Cholera Map")

death_file = st.file_uploader("Upload Death CSV", type=["csv"])
pump_file = st.file_uploader("Upload Pump CSV", type=["csv"])

if death_file:
    df_death = pd.read_csv(death_file)
    st.write("Death data:", df_death.head())
    
if pump_file:
    df_pump = pd.read_csv(pump_file)
    st.write("Pump data:", df_pump.head())

if death_file and pump_file:
    lat_col = [c for c in df_death.columns if c.lower().startswith("lat")][0]
    lon_col = [c for c in df_death.columns if c.lower().startswith("lon")][0]

    center_lat = df_death[lat_col].mean()
    center_lon = df_death[lon_col].mean()

    m = folium.Map(location=[center_lat, center_lon], zoom_start=16)

    # Plot deaths
    for i, r in df_death.iterrows():
        folium.CircleMarker(
            location=[r[lat_col], r[lon_col]],
            radius=4,
            color="red",
            fill=True
        ).add_to(m)

    # Plot pumps
    plat = [c for c in df_pump.columns if c.lower().startswith("lat")][0]
    plon = [c for c in df_pump.columns if c.lower().startswith("lon")][0]

    for i, r in df_pump.iterrows():
        folium.Marker(
            [r[plat], r[plon]],
            icon=folium.Icon(color="blue")
        ).add_to(m)

    st_folium(m, width=800, height=500)
