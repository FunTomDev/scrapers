import requests
from fake_useragent import UserAgent

from shapely.geometry import shape, Polygon
import folium

import json

from config import *

def get_location_data(query:str):
    ua = UserAgent()
    url = "https://nominatim.openstreetmap.org/search"

    headers = {
        "User-Agent": ua.random,
    }

    params = {
        'q': query,
        'format': 'json',
        'polygon_geojson': 1,
        'limit': 3
    }

    response = requests.get(url, params=params, headers=headers)

    try:
        data = response.json()
    except:
        print("Couldn't parse location json...")
        data = None

    return data

def extract_polygon(data):
    for place in data:
        if "geojson" not in place:
            continue

        geometry_type = place["geojson"]["type"]

        if geometry_type is not "Point":
            print(f"Selecting {place["display_name"]} as the location.")
            return place["geojson"]
    print("[ERROR] No polygon found for given query.")

data = get_location_data(query)
polygon = extract_polygon(data)

if polygon:
    boundry = shape(polygon)
    print(f"[INFO] Boundry for {query} loaded successfully! Rendering map...")
    centroid = boundry.centroid
    center_lat = centroid.y
    center_lon = centroid.x

    m = folium.Map(location = [center_lat, center_lon], zoom_start=11)

    folium.GeoJson(
        polygon,
        name="Boundry",
        style_function=lambda x:{
            'fillColor': 'blue',
            'color': 'blue',
            'weight': 2,
            'fillOpacity': 0.3
        }
    ).add_to(m)

    folium.Marker([center_lat, center_lon], popup="Center").add_to(m)
    m.save("map.html")
    print("[INFO] Map successfully saved to the map.html file!")
else:
    print(f"[ERROR] No valid area for {query}")

#print(json.dumps(location["display_name"], indent=4, ensure_ascii=False))