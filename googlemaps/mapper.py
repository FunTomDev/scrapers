import requests
import uuid # Used for mocking unique IDs
from fake_useragent import UserAgent
from shapely.geometry import shape, box, mapping
import folium
from folium.features import DivIcon
import json
import random
import asyncio
import aiohttp

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
        print("[WARNING] Couldn't parse location json...")
        data = None

    return data

def extract_polygon(data):
    for place in data:
        if "geojson" not in place:
            continue

        geometry_type = place["geojson"]["type"]

        if geometry_type != "Point":
            print(f"[INFO] Selecting {place['display_name']} as the location.")
            return place["geojson"]
        
    print("[ERROR] No polygon found for given query.")
    return None

async def fetch_locations_in_bounds(bounds):
    """
    Dummy ASYNC function. 
    REPLACE THIS with your actual API request using `aiohttp` or `httpx`.
    """
    await asyncio.sleep(0.2) 
    
    found_items = []
    for _ in range(random.randint(0, 20)):
        found_items.append({"id": str(uuid.uuid4()), "name": "Some Place"})
    return found_items

async def search_and_split(bounds, area_polygon, desired_amount, state, current_depth=0, max_depth=20):
    if state.get('stop', False):
        return 0

    ids_len = len(state['seen_ids'])
    if ids_len >= desired_amount:
        state['stop'] = True
        return 0
    if current_depth > max_depth:
        return 0

    minx, miny, maxx, maxy = bounds
    current_box = box(minx, miny, maxx, maxy)

    if not current_box.intersects(area_polygon):
        return 0

    state['drawn_squares'].append(current_box)

    results = await fetch_locations_in_bounds(bounds)

    added = 0
    for res in results:
        async with state['lock']:
            if state['stop']:
                break
            res_id = res['id']
            if res_id not in state['seen_ids']:
                state['seen_ids'].add(res_id)
                added += 1
                if len(state['seen_ids']) >= desired_amount:
                    state['stop'] = True
                    break

    if added == 0 and current_depth > 0:
        return 0

    if state['stop'] or current_depth == max_depth:
        return added

    midx = (minx + maxx) / 2.0
    midy = (miny + maxy) / 2.0

    quadrants = [
        (minx, midy, midx, maxy),
        (midx, midy, maxx, maxy),
        (minx, miny, midx, midy),
        (midx, miny, maxx, midy)
    ]

    tasks = [
        asyncio.create_task(
            search_and_split(
                quad,
                area_polygon,
                desired_amount,
                state,
                current_depth + 1,
                max_depth
            )
        )
        for quad in quadrants
    ]

    total_added = added
    try:
        for future in asyncio.as_completed(tasks):
            if state['stop']:
                break
            child_added = await future
            total_added += child_added
            if state['stop']:
                break
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return total_added


async def main():
    data = get_location_data(query)
    polygon = extract_polygon(data)

    if polygon:
        boundary = shape(polygon)
        print(f"[INFO] Boundary for {query} loaded successfully! Starting async split...")

        DESIRED_AMOUNT = 15000
        initial_bounds = boundary.bounds
        state = {
            'seen_ids': set(),
            'drawn_squares': [],
            'stop': False,
            'lock': asyncio.Lock()
        }

        await search_and_split(initial_bounds, boundary, DESIRED_AMOUNT, state, current_depth=0, max_depth=20)

        print(f"[INFO] Search complete! Found {len(state['seen_ids'])} unique results.")
        print(f"[INFO] Explored {len(state['drawn_squares'])} squares.")

        centroid = boundary.centroid
        center_lat = centroid.y
        center_lon = centroid.x

        m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

        folium.GeoJson(
            polygon,
            name="Boundary",
            style_function=lambda x: {
                'fillColor': 'blue',
                'color': 'blue',
                'weight': 2,
                'fillOpacity': 0.1
            }
        ).add_to(m)

        for i, sq in enumerate(state['drawn_squares']):
            folium.GeoJson(
                mapping(sq),
                name="Search Square",
                style_function=lambda x: {
                    'fillColor': 'red',
                    'color': 'red',
                    'weight': 1,
                    'fillOpacity': 0.1
                }
            ).add_to(m)

            center_lat = sq.centroid.y
            center_lon = sq.centroid.x
            
            folium.Marker(
                location=[center_lat, center_lon],
                icon=DivIcon(
                    icon_size=(150, 36),
                    icon_anchor=(7, 10),
                    html=f'<div style="font-size: 12pt; font-weight: bold; color: darkred;">{i}</div>'
                )
            ).add_to(m)

        folium.Marker([center_lat, center_lon], popup="Center").add_to(m)
        m.save("map.html")
        print("[INFO] Map successfully saved to the map.html file!")
    else:
        print(f"[ERROR] No valid area for {query}")

if __name__ == "__main__":
    asyncio.run(main())