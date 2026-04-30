CONFIG = {
    "CLIENT_TARGET": 500,
    "TRUST_THRESHOLD": 50,
    "MAX_DEPTH": 4
}

KEYWORD = "Restaurants"

query = input("What are you looking for?\n")
query_map_url = f"https://nominatim.openstreetmap.org/ui/search.html?q={query}"