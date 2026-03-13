import requests
import uuid # Used for mocking unique IDs
from fake_useragent import UserAgent
from shapely.geometry import shape, box, mapping
import folium
import json

from config import *  # Restored your config

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

        if geometry_type != "Point":
            print(f"[INFO] Selecting {place['display_name']} as the location.")
            return place["geojson"]
    print("[ERROR] No polygon found for given query.")
    return None

# --- MOCK FETCHING LOGIC ---
def mock_fetch_locations_in_bounds(bounds):
    """
    Dummy function. Replace this with your actual API request.
    Returns a list of dicts with unique IDs to simulate finding places.
    """
    import random
    found_items =[]
    # Simulate finding between 0 and 20 items in a square
    for _ in range(random.randint(0, 20)):
        found_items.append({"id": str(uuid.uuid4()), "name": "Some Place"})
    return found_items

# --- SPLITTING ALGORITHM ---
global_unique_results = set()
drawn_squares =[]

def search_and_split(bounds, area_polygon, desired_amount, current_depth=0, max_depth=50):
    global global_unique_results, drawn_squares
    
    # 1. STOP CONDITION: Did we reach the user's desired amount of results?
    if len(global_unique_results) >= desired_amount:
        return
        
    # 2. STOP CONDITION: Did we hit the maximum allowed split depth?
    if current_depth >= max_depth:
        return
        
    minx, miny, maxx, maxy = bounds
    current_box = box(minx, miny, maxx, maxy)
    
    # 3. OPTIMIZATION: Discard immediately if the box is outside the searched area
    if not current_box.intersects(area_polygon):
        return

    # Add to our list of drawn squares for the Folium map
    drawn_squares.append(current_box)

    # 4. Fetch results for this specific square
    results = mock_fetch_locations_in_bounds(bounds)
    
    # 5. Remove duplicates and count NEW results
    new_results_count = 0
    for res in results:
        res_id = res['id']
        if res_id not in global_unique_results:
            global_unique_results.add(res_id)
            new_results_count += 1
            
    # 6. Check if we should split:
    # If we got NO new results from this square, splitting it further is useless.
    if new_results_count == 0 and current_depth > 0:
        return

    # If we still need more results to satisfy the user, split into 4
    if len(global_unique_results) < desired_amount:
        midx = (minx + maxx) / 2.0
        midy = (miny + maxy) / 2.0

        q1 = (minx, midy, midx, maxy)  # Top-Left
        q2 = (midx, midy, maxx, maxy)  # Top-Right
        q3 = (minx, miny, midx, midy)  # Bottom-Left
        q4 = (midx, miny, maxx, maxy)  # Bottom-Right

        for q in [q1, q2, q3, q4]:
            search_and_split(q, area_polygon, desired_amount, current_depth + 1, max_depth)


# --- MAIN EXECUTION ---
data = get_location_data(query) # Using your 'query' from config
polygon = extract_polygon(data)

if polygon:
    boundary = shape(polygon)
    print(f"[INFO] Boundary for {query} loaded successfully! Starting targeted split...")
    
    # User's desired threshold
    DESIRED_AMOUNT = 30000
    
    # Start the recursive search
    initial_bounds = boundary.bounds
    search_and_split(initial_bounds, boundary, desired_amount=DESIRED_AMOUNT, current_depth=0, max_depth=50)
    
    print(f"[INFO] Search complete! Found {len(global_unique_results)} unique results.")
    print(f"[INFO] Explored {len(drawn_squares)} squares.")

    # Render Map
    centroid = boundary.centroid
    center_lat = centroid.y
    center_lon = centroid.x

    m = folium.Map(location=[center_lat, center_lon], zoom_start=11)

    # Draw the main boundary
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

    # Draw the searched squares
    for sq in drawn_squares:
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

    folium.Marker([center_lat, center_lon], popup="Center").add_to(m)
    m.save("map.html")
    print("[INFO] Map successfully saved to the map.html file!")
else:
    print(f"[ERROR] No valid area for {query}")