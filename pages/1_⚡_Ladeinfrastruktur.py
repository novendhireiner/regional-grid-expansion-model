import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import osmnx as ox
from shapely.geometry import Point
import geopandas as gpd

# ---- Streamlit Konfiguration ----
st.set_page_config(layout="wide")

markdown = """
Berlin Ladeinfrastruktur
"""

st.sidebar.title("About")
st.sidebar.info(markdown)
logo = "data/ladestation.png"
st.sidebar.image(logo)

# ---- Daten einlesen ----
@st.cache_data
def load_data():
    file_path = 'data/Ladesaeulenregister_Berlin_01122024.csv'
    df = pd.read_csv(file_path, sep=';', encoding='utf-8')
    
    # Koordinaten korrigieren
    df['Breitengrad'] = df['Breitengrad'].str.replace(',', '.').astype(float)
    df['Längengrad'] = df['Längengrad'].str.replace(',', '.').astype(float)

    # Nur vollständige Daten verwenden
    valid_df = df.dropna(subset=['Breitengrad', 'Längengrad'])
    return valid_df

@st.cache_data
def load_bezirke():
    # Berliner Bezirksdaten aus GeoJSON laden
    url = 'https://raw.githubusercontent.com/funkeinteraktiv/Berlin-Geodaten/master/berlin_bezirke.geojson'
    gdf_bezirke = gpd.read_file(url)  # GeoJSON direkt als GeoDataFrame einlesen
    return gdf_bezirke

@st.cache_data
def load_osm_data():
    # Straßennetzwerk für Berlin von OpenStreetMap laden
    graph = ox.graph_from_place("Berlin, Germany", network_type="drive")
    nodes, edges = ox.graph_to_gdfs(graph)
    return nodes, edges

# Daten laden
valid_df = load_data()
gdf_bezirke = load_bezirke()
nodes, edges = load_osm_data()

# ---- GeoDataFrame für Ladestationen erstellen ----
valid_df['geometry'] = valid_df.apply(lambda x: Point(x['Längengrad'], x['Breitengrad']), axis=1)
gdf_ladesaeulen = gpd.GeoDataFrame(valid_df, geometry='geometry', crs="EPSG:4326")

# ---- Streamlit App ----
st.title("Analyse der Ladeinfrastruktur in Berlin")
st.markdown('''
Die Elektromobilität spielt eine zentrale Rolle in der nachhaltigen Stadtentwicklung Berlins. Eine gut ausgebaute Ladeinfrastruktur ist essenziell, um die Nutzung von Elektrofahrzeugen zu fördern und die Klimaziele der Stadt zu erreichen. Diese interaktive Anwendung bietet eine umfassende Analyse der aktuellen Ladeinfrastruktur in Berlin. Sie zeigt nicht nur bestehende Ladestationen, sondern berechnet auch potenzielle neue Standorte in der Nähe von Verkehrsknotenpunkten, um eine optimale Abdeckung zu gewährleisten.

Die Anwendung nutzt verschiedene Datensätze, darunter das Berliner Ladesäulenregister, geographische Bezirksdaten und OpenStreetMap-Verkehrsdaten. Durch interaktive Filtermöglichkeiten können Benutzer die Ladestationen nach Bezirken oder Ladeleistung selektieren und so gezielte Analysen durchführen.
''')

st.markdown('''
## Bedienungsanleitung
Um die gewünschten Informationen zu erhalten, folgen Sie diesen Schritten:

1. **Bezirk auswählen** aus dem Dropdown-Menü, um die Ladestationen in diesem Gebiet anzuzeigen. Alternativ können Sie alle Bezirke betrachten.

2. **Filteroptionen nutzen** für Schnellladestationen (mindestens 50 kW)

3. **Verkehrsnahe Ladestationen anzeigen**: Die App berechnet potenzielle Standorte für neue Ladestationen anhand von Verkehrsknotenpunkten. Sie können entscheiden, ob Sie diese zusätzlich zu den bestehenden Ladestationen auf der Karte sehen möchten.

4. **Karte erkunden**: Die interaktive Karte zeigt die Ladestationen in Berlin. Bestehende Ladestationen werden in Blau dargestellt, während neu berechnete Standorte rot markiert sind. Durch Anklicken erhalten Sie detaillierte Informationen zu Betreiber, Ladeleistung und Standort.

5. **Analyseergebnisse betrachten**: Unterhalb der Karte finden Sie eine Zusammenfassung mit der Anzahl der aktuell sichtbaren Ladestationen und weiteren relevanten Informationen.


''')

# Bezirksauswahl hinzufügen
selected_bezirk = st.selectbox(
    "Wählen Sie einen Bezirk aus:",
    ["Alle"] + list(gdf_bezirke['name'].unique())
)

# Filtere nach Bezirk, falls ausgewählt
if selected_bezirk != "Alle":
    bezirk_polygon = gdf_bezirke.loc[gdf_bezirke['name'] == selected_bezirk, 'geometry'].values[0]
    gdf_ladesaeulen = gdf_ladesaeulen[gdf_ladesaeulen.within(bezirk_polygon)]
    nodes = nodes[nodes.within(bezirk_polygon)]
    edges = edges[edges.within(bezirk_polygon)]

# ---- Ladeleistungsfilter hinzufügen ----
filter_by_power = st.checkbox("Nur Ladestationen mit mindestens 50 kW anzeigen", value=False)

if filter_by_power:
    gdf_ladesaeulen = gdf_ladesaeulen[gdf_ladesaeulen['Nennleistung Ladeeinrichtung [kW]'] > 50]

# ---- Pufferzone um Verkehrsknotenpunkte erstellen ----
buffer = nodes.buffer(0.005)  # 0.005° ≈ 500m
nearby_ladesaeulen = gdf_ladesaeulen[gdf_ladesaeulen.intersects(buffer.unary_union)]

# Multiselect-Optionen
options = st.multiselect(
    "Wählen Sie die anzuzeigenden Daten aus:",
    ["Bestehende Ladestationen", "Neue berechnete Ladestationen (Verkehrsknotenpunkte)"],
    default=["Bestehende Ladestationen"]
)

# ---- Karte erstellen ----
map_berlin = folium.Map(location=[52.5200, 13.4050], zoom_start=11)

# Bestehende Ladestationen (blau)
if "Bestehende Ladestationen" in options:
    for _, row in gdf_ladesaeulen.iterrows():
        folium.Marker(
            location=[row['Breitengrad'], row['Längengrad']],
            popup=(
                f"Betreiber: {row['Betreiber']}<br>"
                f"Leistung: {row['Nennleistung Ladeeinrichtung [kW]']} kW<br>"
                f"Adresse: {row['Straße']} {row['Hausnummer']}"
            ),
            icon=folium.Icon(color="blue", icon="bolt", prefix="fa")
        ).add_to(map_berlin)

# Neue berechnete Ladestationen in der Nähe von Verkehrsknotenpunkten (rot)
if "Neue berechnete Ladestationen (Verkehrsknotenpunkte)" in options:
    for _, row in nearby_ladesaeulen.iterrows():
        folium.CircleMarker(
            location=[row['Breitengrad'], row['Längengrad']],
            radius=6,
            color="red",
            fill=True,
            fill_opacity=0.8,
            popup=f"Neue Station in Nähe zu Verkehrsknoten: {row['Straße']}"
        ).add_to(map_berlin)

# Karte anzeigen
st_folium(map_berlin, width=1800, height=1000)

# ---- Analyseergebnisse ----
st.subheader("Analyseergebnisse")
st.markdown(
    f"""
    - **Ausgewählter Bezirk:** {selected_bezirk if selected_bezirk != "Alle" else "Alle Bezirke"}  
    - **Anzahl der bestehenden Ladestationen:** {len(gdf_ladesaeulen)}  
    - **Anzahl der berechneten Ladestationen in der Nähe von Verkehrsknotenpunkten:** {len(nearby_ladesaeulen)}  
    """
)
