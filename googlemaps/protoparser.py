import requests
import re
import json
import urllib.parse

def get_google_maps_cids(keyword, lat, lon, zoom=14):
    """
    Searches Google Maps for a keyword at a location and returns a list of CIDs (Place IDs).
    """
    
    # 1. Construct a "Human" URL
    # We use the standard /maps/search/ URL structure. 
    # Google's server will interpret this and generate the necessary protobufs internally.
    base_url = "https://www.google.com/maps/search/"
    query = urllib.parse.quote(keyword)
    coords = f"@{lat},{lon},{zoom}z"
    
    url = f"{base_url}{query}/{coords}?hl=en"
    
    print(f"[*] Fetching: {url}")

    # 2. Mimic a Real Browser
    # Google Maps returns different data (or blocks you) if the User-Agent isn't a browser.
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[!] Error fetching data: {e}")
        return []

    # 3. Extract the Data Payload
    # Google Maps embeds the data in a JavaScript variable called `window.APP_INITIALIZATION_STATE`
    # We use Regex to grab that array structure.
    # Look for the pattern: window.APP_INITIALIZATION_STATE=[ ... ];
    
    # This regex looks for the specific assignment and grabs the JSON array content
    with open("index.html", "w") as file:
        file.write(response.text)
    data_regex = re.search(r'window\.APP_INITIALIZATION_STATE\s*=\s*(\[\[.+?\]\]);', response.text)
    
    if not data_regex:
        print("[!] Could not find data in response. Google might have changed the format or blocked the request.")
        return []

    raw_json = data_regex.group(1)

    # 4. Parse the JSON
    # The JSON is very messy and nested. We need to find the specific pattern for Place IDs.
    # A Google Place ID usually looks like a hex string in the format: 0x...:0x...
    # Example: 0x471ecc669a869f01:0x72ce14347e090e84
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError:
        print("[!] Failed to decode JSON response.")
        return []

    # 5. Extract CIDs via Deep Search
    # Instead of hardcoding the path (e.g., data[0][1][...]), which changes often,
    # we recursively search the JSON tree for strings matching the CID hex pattern.
    
    cids = set()
    hex_pattern = re.compile(r'^(0x[0-9a-fA-F]+):(0x[0-9a-fA-F]+)$')

    def find_cids_recursive(obj):
        if isinstance(obj, list):
            for item in obj:
                find_cids_recursive(item)
        elif isinstance(obj, str):
            match = hex_pattern.match(obj)
            if match:
                # We found a Hex ID combo!
                # The CID is the *second* part converted to Decimal.
                # Format: 0x<CoordinatesHash>:0x<CID>
                cid_hex = match.group(2)
                cid_decimal = int(cid_hex, 16)
                cids.add(cid_decimal)
        elif isinstance(obj, dict):
            for value in obj.values():
                find_cids_recursive(value)

    find_cids_recursive(data)

    # 6. Formatting Results
    results = []
    for cid in cids:
        link = f"https://www.google.com/maps?cid={cid}"
        results.append(link)

    return results

# --- Usage Example ---

if __name__ == "__main__":
    # Example: Searching for "Pizza" in New York
    # Lat/Lon: 40.7128, -74.0060
    
    KEYWORD = "Pizza"
    LAT = 40.7128
    LON = -74.0060
    
    links = get_google_maps_cids(KEYWORD, LAT, LON)
    
    print(f"\n[*] Found {len(links)} unique places:")
    for link in links:
        print(link)