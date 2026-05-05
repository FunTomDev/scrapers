import asyncio
import aiohttp
import json
import re
import urllib.parse
import random
import logging
from shapely.geometry import Point, box

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ProtoBuilder:
    def __init__(self):
        self.nodes =[]

    def add_message(self, field_id, builder):
        self.nodes.append(f"!{field_id}m{len(builder.nodes)}")
        self.nodes.extend(builder.nodes)
        return self

    def add_string(self, field_id, value):
        encoded = urllib.parse.quote(str(value).replace('*', '*2A').replace('!', '*21'), safe='')
        self.nodes.append(f"!{field_id}s{encoded}")
        return self

    def add_double(self, field_id, value):
        self.nodes.append(f"!{field_id}d{value}")
        return self

    def add_int(self, field_id, value):
        self.nodes.append(f"!{field_id}i{value}")
        return self
    
    def add_long(self, field_id, value):
        self.nodes.append(f"!{field_id}j{int(value)}")
        return self
    
    def add_float(self, field_id, value):
        self.nodes.append(f"!{field_id}f{value}")
        return self

    def add_bool(self, field_id, value):
        self.nodes.append(f"!{field_id}b{'1' if value else '0'}")
        return self

    def build(self):
        return "".join(self.nodes)

class GoogleScraper:
    def __init__(self):
        # 1. Desktop UAs ONLY to prevent Google from serving the Mobile "Lite" site
        self.desktop_uas =[
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:125.0) Gecko/20100101 Firefox/125.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0"
        ]

        self.session_ua = random.choice(self.desktop_uas)

        self.base_headers = {
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.google.com/maps",
            "X-Goog-AuthUser": "0",
        }

    async def _fetch_with_retry(self, session, url, max_retries=3):
        """Centralized fetch method with Exponential Backoff and dynamic User-Agent."""

        for attempt in range(max_retries):
            headers = self.base_headers.copy()
            headers["User-Agent"] =  random.choice(self.desktop_uas)
            
            try:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 429:
                        wait_time = (2 ** attempt) + random.uniform(0, 1)
                        logging.warning(f"429 Too Many Requests. Retrying in {wait_time:.2f}s...")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    if response.status == 200:
                        return await response.text()
                        
            except Exception as e:
                logging.debug(f"Request failed: {url[:80]}... - {e}")
                await asyncio.sleep((2 ** attempt))
                
        logging.error(f"Failed to fetch {url} after {max_retries} attempts.")
        return None

    def _generate_pb(self, keyword, lat, lon, zoom=14, offset=0):
        delta = 0.01 / (2 ** (zoom - 14))
        center = ProtoBuilder()
        center.add_double(1, delta)
        center.add_double(2, lon)
        center.add_double(3, lat)
        screen = ProtoBuilder()
        screen.add_int(1, 1024)
        screen.add_int(2, 768)
        viewport = ProtoBuilder()
        viewport.add_message(1, center)
        viewport.add_message(3, screen)
        viewport.add_float(4, float(zoom))
        inner = ProtoBuilder()
        inner.add_string(1, keyword)
        inner.add_message(4, viewport)
        if offset > 0:
            inner.add_int(8, offset)
        return inner.build()

    
    def get_rich_details_url(self, full_id, lat, lon, zoom=14.0, place_name="", session_token=""):
        """Get url for business details exactly mirroring Google's native preview payload."""
        
        lat = lat or 0.0
        lon = lon or 0.0
        
        try:
            cid_hex = full_id.split(':')[-1]
            cid_decimal = str(int(cid_hex, 16))
            query_val = cid_decimal
        except Exception:
            query_val = urllib.parse.quote(full_id)
            
        # Initialize root builder
        root = ProtoBuilder()
        
        # --- BLOCK 1: Build the !1m14 Context Block ---
        m1 = ProtoBuilder()
        m1.add_string(1, full_id)
        
        m3 = ProtoBuilder()
        
        # Viewport delta & center (!1m3)
        m3_1 = ProtoBuilder()
        m3_1.add_double(1, 19551.814223056626)  # Or calculate via your delta formula
        m3_1.add_double(2, lon)
        m3_1.add_double(3, lat)
        m3.add_message(1, m3_1)
        
        # Pitch/Heading (!2m3)
        m3_2 = ProtoBuilder()
        m3_2.add_float(1, 0.0)
        m3_2.add_float(2, 0.0)
        m3_2.add_float(3, 0.0)
        m3.add_message(2, m3_2)
        
        # Screen dimensions (!3m2)
        m3_3 = ProtoBuilder()
        m3_3.add_int(1, 1024)
        m3_3.add_int(2, 768)
        m3.add_message(3, m3_3)
        
        m3.add_float(4, float(zoom))
        
        # This will perfectly compile to !1m14... !3m12...
        m1.add_message(3, m3)
        root.add_message(1, m1)
        
        # --- BLOCK 2: Build the !12m4 Block ---
        m12 = ProtoBuilder()
        m12_2 = ProtoBuilder()
        m12_2.add_int(1, 360)
        m12_2.add_int(2, 120)
        m12_2.add_int(4, 8)
        m12.add_message(2, m12_2)
        root.add_message(12, m12)
        
        # Generate the dynamic prefix
        pb_prefix = root.build()
        
        # --- BLOCK 3: Static Data Requests ---
        # Hardcoded at the root level so it doesn't corrupt ProtoBuilder's node counts
        pb_static = (
            f"!13m57!2m2!1i203!2i100!3m2!2i4!5b1!6m6!1m2!1i86!2i86!1m2!1i408!2i240"
            f"!7m33!1m3!1e1!2b0!3e3!1m3!1e2!2b1!3e2!1m3!1e2!2b0!3e3!1m3!1e8!2b0!3e3!1m3!1e10!2b0!3e3!1m3!1e10!2b1!3e2!1m3!1e10!2b0!3e4!1m3!1e9!2b1!3e2!2b1!9b0"
            f"!15m8!1m7!1m2!1m1!1e2!2m2!1i195!2i195!3i20"
        )
        
        # --- BLOCK 4: Dynamic Session Token ---
        pb_token = ""
        if session_token:
            # Note: !7e81 uses an enum 'e' which isn't in ProtoBuilder, so we append raw
            pb_token = f"!14m3!1s{session_token}!7e81"
            
        # --- BLOCK 5: The Massive Payload Tail ---
        pb_tail = (
            f"!15i10112"
            f"!15m108!1m26!13m9!2b1!3b1!4b1!6i1!8b1!9b1!14b1!20b1!25b1!18m15!3b1!4b1!5b1!6b1!13b1!14b1!17b1!21b1!22b1!30b1!32b1!33m1!1b1!34b1!36e2!10m1!8e3!11m1!3e1!17b1!20m2!1e3!1e6!24b1!25b1!26b1!27b1!29b1!30m1!2b1!36b1!37b1!39m3!2m2!2i1!3i1!43b1!52b1!54m1!1b1!55b1!56m1!1b1!61m2!1m1!1e1!65m5!3m4!1m3!1m2!1i224!2i298!72m22!1m8!2b1!5b1!7b1!12m4!1b1!2b1!4m1!1e1!4b1!8m10!1m6!4m1!1e1!4m1!1e3!4m1!1e4!3sother_user_google_review_posts__and__hotel_and_vr_partner_review_posts!6m1!1e1!9b1!89b1!90m2!1m1!1e2!98m3!1b1!2b1!3b1!103b1!113b1!114m3!1b1!2m1!1b1!117b1!122m1!1b1!126b1!127b1!128m1!1b0"
            f"!21m0!22m1!1e81!30m8!3b1!6m2!1b1!2b1!7m2!1e3!2b1!9b1!34m5!7b1!10b1!14b1!15m1!1b0!37i778"
        )
        
        # Assemble and encode
        pb = pb_prefix + pb_static + pb_token + pb_tail
        pb_encoded = pb.replace("!", "%21")
        
        return f"https://www.google.com/maps/preview/place?authuser=0&hl=en&q={query_val}&pb={pb_encoded}"

    def _get_search_url(self, keyword, lat, lon, zoom=14, offset=0):
        """Generate search url for given location"""

        pb = self._generate_pb(keyword, lat, lon, zoom, offset)
        query = urllib.parse.quote(keyword)
        return f"https://www.google.com/search?tbm=map&authuser=0&pb={pb}&q={query}"

    def _extract_ids_from_search(self, data):
        """Extract ids from given Google Maps search"""

        results = []
        seen_ids = set()
        
        id_pattern = re.compile(r'^0x[0-9a-fA-F]+:0x[0-9a-fA-F]+$')

        def find_ids(obj, depth=0):
            if depth > 20: return
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, str) and id_pattern.match(item):
                        if item not in seen_ids:
                            results.append({"id": item})
                            seen_ids.add(item)
                    else:
                        find_ids(item, depth + 1)
            elif isinstance(obj, dict):
                for value in obj.values():
                    find_ids(value, depth + 1)

        find_ids(data)
        return results

    def _extract_details_from_cid(self, data):
        """Get given CID business details"""

        details = {
            "id": None,
            "cid": None,
            "url": None,
            "name": None,
            "address": None,
            "latitude": None,
            "longitude": None,
            "type": None,
            "phone": None,
            "website": None,
            "rating": None,
            "reviews_count": None,
            "opening_hours": None
        }
        
        # The primary Place object is ALWAYS at index 6 in the root response array.
        if not (isinstance(data, list) and len(data) > 6 and isinstance(data[6], list)):
            return details
            
        entity = data[6]

        # 1. ID & CID
        if len(entity) > 10 and isinstance(entity[10], str):
            details["id"] = entity[10]
            
            try:
                details["cid"] = int(details["id"].split(':')[1], 16)
                details["url"] = f"https://www.google.com/maps?cid={details['cid']}"
            except Exception: pass

        # 2. Name
        if len(entity) > 11 and isinstance(entity[11], str):
            details["name"] = entity[11]
        
        # print(entity[10], entity[4])

        # 3. Address
        if len(entity) > 18 and isinstance(entity[18], str):
            addr_parts = entity[18].split(",")
            details["address"] = ", ".join(addr_parts[1:]).strip() if len(addr_parts) > 1 else entity[18].strip()

        # 4. Coordinates
        if len(entity) > 9 and isinstance(entity[9], list) and len(entity[9]) >= 4:
            if type(entity[9][2]) in (int, float): details["latitude"] = float(entity[9][2])
            if type(entity[9][3]) in (int, float): details["longitude"] = float(entity[9][3])

        # 5. Type (Category)
        if len(entity) > 13 and isinstance(entity[13], list) and len(entity[13]) > 0:
            if isinstance(entity[13][0], str): details["type"] = entity[13][0]

        # 6. Phone (Regex scan just the top level of the entity)
        phone_pattern = re.compile(r'^\+?[0-9\s\-()]{8,20}$')
        for item in entity:
            if isinstance(item, str) and phone_pattern.match(item):
                if 7 <= sum(c.isdigit() for c in item) <= 15:
                    details["phone"] = item
                    break

        # 7. Website
        if len(entity) > 7 and isinstance(entity[7], list) and len(entity[7]) > 0:
            if isinstance(entity[7][0], str) and entity[7][0].startswith("http"):
                details["website"] = entity[7][0]

        # 8. Rating & Reviews Block (Index 4) - Using the safe heuristic
        if len(entity) > 4 and isinstance(entity[4], list):
            for i, item in enumerate(entity[4]):
                if type(item) in (float, int) and 1.0 <= item <= 5.0:
                    details["rating"] = float(item)
                    for offset in (1, 2):
                        if i + offset < len(entity[4]) and type(entity[4][i + offset]) is int:
                            details["reviews_count"] = entity[4][i + offset]
                            break
                    break

        # 9. Opening Hours (Index 34)
        if len(entity) > 34 and isinstance(entity[34], list):
            days = []
            for item in entity[34]:
                if (isinstance(item, list) and len(item) >= 4 and isinstance(item[0], str) and 
                    isinstance(item[2], list) and isinstance(item[3], list)):
                    hours_str = str(item[3][0][0]) if len(item[3]) > 0 and isinstance(item[3][0], list) and len(item[3][0]) > 0 else ""
                    days.append((item[0], hours_str))
            if len(days) >= 7:
                details["opening_hours"] = {d[0]: d[1] for d in days[:7]}

        return details

    async def get_details_by_id(self, session, full_id, name="", lat=None, lon=None, zoom=14.0, session_token=""):
        """Get details of business by its FID"""

        url = self.get_rich_details_url(full_id, lat, lon, zoom, session_token=session_token)
        print(url)
        text = await self._fetch_with_retry(session, url)
        if not text:
            return None
            
        if text.startswith(")]}'"):
            text = text[4:]
        
        with open("check.json", 'w') as f:
            f.write(text)

        try:
            data = json.loads(text)
            
            details = self._extract_details_from_cid(data)
            
            if details and details.get("name"):
                return details
            
        except json.JSONDecodeError:
            return None
                
        return None

    def _extract_session_token(self, data):
        """
        Extracts the dynamic session token using exact positional mapping.
        Falls back to a relaxed regex if the array structure changes.
        """
        # 1. PRIMARY METHOD: Positional Extraction (Fastest & Most Accurate)
        try:
            # Navigating to data[0][1][0][8] based on known search payload structure
            if isinstance(data, list) and len(data) > 0:
                block_0 = data[0]
                if isinstance(block_0, list) and len(block_0) > 1:
                    block_1 = block_0[1]
                    if isinstance(block_1, list) and len(block_1) > 0:
                        target_array = block_1[0]
                        # Ensure the array is long enough and grab index 8
                        if isinstance(target_array, list) and len(target_array) > 8:
                            token = target_array[8]
                            if isinstance(token, str) and not token.startswith("0x"):
                                return token
        except Exception as e:
            logging.debug(f"Positional token extraction failed/shifted: {e}")

        # 2. FALLBACK METHOD: Relaxed Regex Scan
        # Accepts 20-28 characters of Base64URL to account for variable padding
        token_pattern = re.compile(r'^[A-Za-z0-9_-]{20,28}$')
        
        def find_token(obj, depth=0):
            if depth > 15: return None
            
            if isinstance(obj, list):
                for item in obj:
                    res = find_token(item, depth + 1)
                    if res: return res
            elif isinstance(obj, str):
                # Ignore hex IDs and timestamps (pure digits)
                if token_pattern.match(obj) and not obj.startswith('0x') and not obj.isdigit():
                    return obj
            return None
            
        return find_token(data)
    
    async def search(self, session, query, lat, lon, seen_ids, zoom=14, max_results=20):
        """Search for results in given location dictated by latitude and longitude"""

        all_results = []
        offset = 0
        
        while len(all_results) < max_results:
            url = self._get_search_url(query, lat, lon, zoom, offset)
            text = await self._fetch_with_retry(session, url)
            
            if not text:
                break
                
            if text.startswith(")]}'"):
                text = text[4:]

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                break

            session_token = self._extract_session_token(data)
            
            if session_token:
                print(f"Successfully extracted session token: {session_token}")
            else:
                logging.warning("Could not find session token in search data. Details payload may be degraded.")

            id_items = self._extract_ids_from_search(data)
            if not id_items:
                break
            
            tasks =[]
            for id_item in id_items:
                item_id = id_item["id"]
                if item_id not in seen_ids and item_id not in [r.get("id") for r in all_results]:
                    tasks.append(self.get_details_by_id(session, item_id, query, lat, lon, zoom, session_token))
            
            if not tasks:
                break
                
            fetched_details = await asyncio.gather(*tasks)
            
            new_items_count = 0
            for details in fetched_details:
                if details and details.get("name"):
                    all_results.append(details)
                    new_items_count += 1
                    
                    if len(all_results) >= max_results:
                        break
            
            if new_items_count == 0:
                break
                
            offset += 20
            if offset > 400:
                break
                
        return all_results[:max_results]

    def filter_results_by_box(self, scraped_results, current_box):
        """Check if returned search items are inside the searched box"""
        valid_results =[]
        for item in scraped_results:
            lat, lon = item.get('latitude'), item.get('longitude')
            if lat and lon:
                if current_box.contains(Point(lon, lat)):
                    valid_results.append(item)
            else:
                valid_results.append(item)
        return valid_results

    def split_box(self, parent_box):
        """Split search box for depth"""

        minx, miny, maxx, maxy = parent_box.bounds
        midx = (minx + maxx) / 2.0
        midy = (miny + maxy) / 2.0
        return[
            box(minx, midy, midx, maxy),
            box(midx, midy, maxx, maxy),
            box(minx, miny, midx, midy),
            box(midx, miny, maxx, midy)
        ]

    async def grid_search(self, keyword, initial_bounds, target_count=100, max_depth=5, trust_threshold=15):
        """Run google search in bounds"""

        state = {
            "seen_ids": set(),
            "results": [],
            "explored_boxes":[],
            "lock": asyncio.Lock()
        }
        starting_box = box(*initial_bounds)

        google_cookies = {
            "CONSENT": "YES+cb.20230501-14-p0.en+FX+414",
            "SOCS": "CAISHAgCEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmVuIAEaBgiAo_CmBg"
        }
        
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar, headers=self.base_headers, cookies=google_cookies) as session:   

            logging.info("Warming up session cookies...")
            try:
                await session.get("https://www.google.com/?hl=en", headers=self.base_headers)
            except Exception as e:
                logging.debug(f"Warmup ping failed: {e}")

            await self._recursive_grid_scrape(
                session, keyword, starting_box, state, 0, max_depth, target_count, trust_threshold
            )
            
        return state["results"]

    async def _recursive_grid_scrape(self, session, keyword, current_box, state, depth, max_depth, target_count, trust_threshold):
        if len(state["seen_ids"]) >= target_count:
            return
            
        state["explored_boxes"].append(current_box)
        center_lat, center_lon = current_box.centroid.y, current_box.centroid.x
        width = current_box.bounds[2] - current_box.bounds[0]
        
        zoom = 12 if width > 0.05 else (13 if width > 0.02 else (14 if width > 0.01 else 15))
        
        found = await self.search(session, keyword, center_lat, center_lon, state["seen_ids"], zoom=zoom, max_results=20)
        valid_found = self.filter_results_by_box(found, current_box)
        
        async with state["lock"]:
            for item in valid_found:
                if item["id"] not in state["seen_ids"]:
                    state["seen_ids"].add(item["id"])
                    state["results"].append(item)
                    if len(state["seen_ids"]) >= target_count:
                        break
                        
        if len(state["seen_ids"]) >= target_count:
            return
            
        if len(valid_found) >= trust_threshold and depth < max_depth:
            sub_boxes = self.split_box(current_box)
            tasks =[
                asyncio.create_task(
                    self._recursive_grid_scrape(session, keyword, sb, state, depth + 1, max_depth, target_count, trust_threshold)
                ) for sb in sub_boxes
            ]
            await asyncio.gather(*tasks)