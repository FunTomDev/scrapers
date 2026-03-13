import requests
import json
import re
from fake_useragent import UserAgent

class MapsHttpScraper:
    def __init__(self):
        self.ua = UserAgent()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.ua.random,
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/"
        })

    def search_box(self, query, lat, lon, zoom_side_length):
        delta = 0.01 
        
        lat_min = lat - delta
        lat_max = lat + delta
        lon_min = lon - delta
        lon_max = lon + delta

        pb_template = (
            f"!1m14!1s{query}"  # Search Query
            f"!4m8!1m3!1d{delta*10000}!2d{lon}!3d{lat}!3m2!1i1024!2i768!4f13.1" # Viewport context
            # Actual coordinate bounds usually go here in deeper nested messages
        )
        
        # 3. THE URL
        # We use the /search endpoint which returns JSON/HTML hybrid
        url = "https://www.google.com/search"
        params = {
            "tbm": "map",
            "authuser": "0",
            "hl": "en",
            "gl": "pl",
            "pb": pb_template, 
            "q": query
        }

        # 4. THE REQUEST
        response = self.session.get(url, params=params)
        
        return self.parse_response(response.text)

    def parse_response(self, text):
        # Google returns a "Security Prefix" to stop JSON hijacking: )]}'
        # We must strip it.
        try:
            # 5. LOCATE THE JSON BLOB
            # The data is usually embedded inside a script tag or pure text depending on the endpoint.
            # Look for the start of the big array.
            start = text.find('data:')
            # This part requires heavy regex work because Google obfuscates it.
            # A cleaner way is to look for the "window.APP_INITIALIZATION_STATE" if scraping the web interface
            # OR just strip the header if hitting the RPC endpoint.
            
            # Rough Example of parsing the specific "search" array
            # You are looking for a massive array that contains names like "Pizza Hut"
            # It usually lives at index [0][1] of the main object.
            
            print(text)
            return "Raw Data (Needs Parsing Logic)"
        except Exception as e:
            return []

# Usage
scraper = MapsHttpScraper()
data = scraper.search_box("Plumber", 52.2297, 21.0122, 0.01)
print(data)