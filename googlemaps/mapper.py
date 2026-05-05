import requests
from fake_useragent import UserAgent
from shapely.geometry import shape, box, mapping
import folium
from folium.features import DivIcon
import json
import asyncio
from google_scraper import GoogleScraper

def get_location_data(query:str):
    ua = UserAgent()
    url = "https://nominatim.openstreetmap.org/search"
    headers = {"User-Agent": ua.random}
    params = {'q': query, 'format': 'json', 'polygon_geojson': 1, 'limit': 3}
    response = requests.get(url, params=params, headers=headers)
    try:
        return response.json()
    except:
        print("[WARNING] Couldn't parse location json...")
        return None

def extract_polygon(data):
    for place in data:
        if "geojson" not in place: continue
        if place["geojson"]["type"] != "Point":
            print(f"[INFO] Selecting {place['display_name']} as the location.")
            return place["geojson"]
    print("[ERROR] No polygon found for given query.")
    return None

async def main():
    query = "Warsaw"
    keyword = "mcdonalds"
    
    data = get_location_data(query)
    polygon_geojson = extract_polygon(data)

    if polygon_geojson:
        boundary = shape(polygon_geojson)
        print(f"[INFO] Boundary for {query} loaded! Starting async grid search...")

        scraper = GoogleScraper()
        initial_bounds = boundary.bounds
        
        results = await scraper.grid_search(
            keyword=keyword,
            initial_bounds=initial_bounds,
            target_count=100,
            max_depth=8,
            trust_threshold=15
        )

        print(f"[INFO] Search complete! Found {len(results)} unique results.")
        
        with open("leads.json", "w", encoding="utf-8") as f:
            json.dump(results, f, indent=4, ensure_ascii=False)

        centroid = boundary.centroid
        m = folium.Map(location=[centroid.y, centroid.x], zoom_start=12)

        folium.GeoJson(polygon_geojson, name="Boundary",
            style_function=lambda x: {'fillColor': 'blue', 'color': 'blue', 'weight': 2, 'fillOpacity': 0.1}).add_to(m)

        for _, res in enumerate(results):
            lat, lon = res.get('latitude'), res.get('longitude')
            if lat and lon:
                folium.Marker(
                    location=[lat, lon],
                    popup=f"<b>{res.get('name', 'N/A')}</b><br>{res.get('address', 'N/A')}",
                    tooltip=res.get('name', 'N/A')
                ).add_to(m)

        m.save("map.html")
        print("[INFO] Results saved to leads.json and map successfully saved to map.html!")
    else:
        print(f"[ERROR] No valid area for {query}")

if __name__ == "__main__":
    asyncio.run(main())
