import asyncio
import json
from shapely.geometry import box, Point
from playwright.async_api import async_playwright

# ==========================================
# CONFIGURATION
# ==========================================
CONFIG = {
    "CLIENT_TARGET": 500,       
    "TRUST_THRESHOLD": 50,      
    "MAX_DEPTH": 4              
}

# Geospatial helpers (Math is instant, so these remain synchronous)
def split_box(parent_box):
    minx, miny, maxx, maxy = parent_box.bounds
    midx = (minx + maxx) / 2.0
    midy = (miny + maxy) / 2.0
    return [
        box(minx, midy, midx, maxy),
        box(midx, midy, maxx, maxy),
        box(minx, miny, midx, midy),
        box(midx, miny, maxx, midy)
    ]

def filter_results_by_box(scraped_results, current_box):
    valid_results = []
    for item in scraped_results:
        lat, lon = item.get('latitude'), item.get('longitude')
        if lat and lon and current_box.contains(Point(lon, lat)):
            valid_results.append(item)
    return valid_results

# ==========================================
# ASYNC SCRAPING ENGINE
# ==========================================
async def scrape_google_maps(context, search_box, keyword):
    """Opens a new tab, scrapes the area, and closes the tab."""
    minx, miny, maxx, maxy = search_box.bounds
    width = maxx - minx
    zoom = 12 if width > 0.05 else (13 if width > 0.02 else (14 if width > 0.01 else 15))
    center_lat, center_lon = search_box.centroid.y, search_box.centroid.x
    
    url = f"https://www.google.com/maps/search/{keyword}/@{center_lat},{center_lon},{zoom}z"
    
    # Open a new tab for this specific concurrent task
    page = await context.new_page()
    print(f"-> [Tab Opened] Navigating to: {url}")
    
    await page.goto(url)
    await page.wait_for_timeout(10000) # Wait for network/DOM

    import re
    from playwright.async_api import TimeoutError

    # ---------------------------------------------------------
    # 1. WAIT FOR THE SIDEBAR TO LOAD
    # ---------------------------------------------------------
    feed_selector = 'div[role="feed"]'
    try:
        # If the feed doesn't load within 10 seconds, it's an empty region
        await page.wait_for_selector(feed_selector, timeout=10000)
    except TimeoutError:
        print(f"<- [Tab Closed] No results found for: {url}")
        await page.close()
        return []

    # ---------------------------------------------------------
    # 2. SCROLL THE SIDEBAR TO THE BOTTOM
    # ---------------------------------------------------------
    # We use page.evaluate to run this JavaScript directly inside the browser.
    # It loops, scrolling down, and waits 1.5s for new results to load.
    # If the scroll height doesn't change after 3 attempts, we've hit the bottom.
    await page.evaluate(f'''
        async () => {{
            const feed = document.querySelector('{feed_selector}');
            if (!feed) return;
            
            let lastHeight = 0;
            let retries = 0;
            
            while (retries < 3) {{
                feed.scrollTo(0, feed.scrollHeight);
                await new Promise(resolve => setTimeout(resolve, 1500)); 
                
                if (feed.scrollHeight === lastHeight) {{
                    retries++; // Height didn't change, maybe it's the end?
                }} else {{
                    retries = 0; // Height changed, reset retries
                    lastHeight = feed.scrollHeight;
                }}
            }}
        }}
    ''')

    # ---------------------------------------------------------
    # 3. EXTRACT THE DATA INSTANTLY
    # ---------------------------------------------------------
    # Instead of pulling elements one by one (which is slow in Playwright), 
    # we grab all data at once in the browser context and return a clean list of dictionaries.
    results = await page.evaluate('''
        () => {
            const extracted = [];
            // Target the main link wrapped around each result card
            const links = document.querySelectorAll('a[href*="/maps/place/"]');
            
            links.forEach(link => {
                const name = link.getAttribute('aria-label');
                const href = link.href;
                
                // Regex to hunt down the exact coordinates and Google ID in the messy URL
                // Example: /maps/place/Name/data=!4m...1s(0x...:0x...)!8m2!3d(LAT)!4d(LON)
                const latMatch = href.match(/!3d(-?\\d+\\.\\d+)/);
                const lonMatch = href.match(/!4d(-?\\d+\\.\\d+)/);
                const idMatch = href.match(/1s(0x[a-f0-9]+:0x[a-f0-9]+)/);
                
                // Only keep results where we successfully found the location math
                if (latMatch && lonMatch && idMatch && name) {
                    extracted.push({
                        name: name.trim(),
                        id: idMatch[1],
                        latitude: parseFloat(latMatch[1]),
                        longitude: parseFloat(lonMatch[1]),
                        url: href
                    });
                }
            });
            return extracted;
        }
    ''')

    print("Running scraper...")
    
    # Clean up to free RAM
    await page.close()
    print(f"<- [Tab Closed] Finished: {url}")
    return results

# ==========================================
# THE CONCURRENT RECURSIVE ALGORITHM
# ==========================================
async def recursive_scrape(context, current_box, keyword, state, depth=0):
    if len(state['final_results']) >= CONFIG['CLIENT_TARGET']:
        return []

    if depth >= CONFIG['MAX_DEPTH']:
        parent_results = await scrape_google_maps(context, current_box, keyword)
        return filter_results_by_box(parent_results, current_box)

    # 1. Scrape Parent
    raw_parent_results = await scrape_google_maps(context, current_box, keyword)
    valid_parent_results = filter_results_by_box(raw_parent_results, current_box)
    unique_parent = {item['id']: item for item in valid_parent_results}

    # 2. Trust Threshold Check
    if len(unique_parent) < CONFIG['TRUST_THRESHOLD']:
        _add_to_global_state(unique_parent.values(), state)
        return list(unique_parent.values())

    # 3. CONCURRENT SPLIT (The Magic Happens Here)
    print(f"[Depth {depth}] Too dense! Splitting into 4 concurrent tasks...")
    sub_boxes = split_box(current_box)
    
    # Create the 4 tasks
    tasks = [
        recursive_scrape(context, sub_box, keyword, state, depth + 1) 
        for sub_box in sub_boxes
    ]
    
    # Run all 4 tasks AT THE EXACT SAME TIME and wait for them all to finish
    children_results_lists = await asyncio.gather(*tasks)
    
    # Flatten the list of lists returned by gather
    children_results = [item for sublist in children_results_lists for item in sublist]
    unique_children = {item['id']: item for item in children_results}
    
    # 4. Verification
    if len(unique_children) > len(unique_parent):
        _add_to_global_state(unique_children.values(), state)
        return list(unique_children.values())
    else:
        _add_to_global_state(unique_parent.values(), state)
        return list(unique_parent.values())

def _add_to_global_state(new_items, state):
    for item in new_items:
        if item['id'] not in state['seen_ids']:
            state['seen_ids'].add(item['id'])
            state['final_results'].append(item)

# ==========================================
# ASYNC MAIN EXECUTION
# ==========================================
async def main():
    initial_bounds = [20.851688, 52.097851, 21.271151, 52.368153] 
    starting_box = box(*initial_bounds)
    keyword = "Restaurants"
    
    state = {"final_results": [], "seen_ids": set()}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        # We create a context so we can spawn multiple pages (tabs) from it
        context = await browser.new_context()
        
        print("Starting Async Grid Scraper...")
        await recursive_scrape(context, starting_box, keyword, state)
        
        await browser.close()

    print(f"\nScraping complete! Successfully extracted {len(state['final_results'])} leads.")
    with open("leads.json", "w", encoding="utf-8") as f:
        json.dump(state['final_results'], f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    asyncio.run(main())