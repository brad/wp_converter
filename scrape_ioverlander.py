#!/usr/bin/env python3
"""
iOverlander POI Scraper
Scrapes POIs for a specified region/country from iOverlander and outputs a CSV file
that can be processed by wp_converter into a GPX file.
"""

import argparse
import concurrent.futures
import csv
import html
import re
import sys
import time
import urllib.request
from typing import Dict, List, Optional, Set

BASE_URL = "https://ioverlander.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

CSV_FIELDS = [
    "Id", "Location", "Name", "Category", "Description", "Latitude", "Longitude", "Altitude",
    "Date verified", "Open", "Electricity", "Wifi", "Kitchen", "Parking", "Restaurant",
    "Showers", "Water", "Toilets", "Big rig friendly", "Tent friendly", "Pet friendly",
    "Sanitation dump station", "Outdoor gear", "Groceries", "Artisan goods", "Bakery",
    "Rarity in this area", "Repairs vehicles", "Repairs motorcycles", "Repairs bicycles",
    "Sells parts", "Recycles batteries", "Recycles oil", "Bio fuel", "Electric vehicle charging",
    "Composting sawdust", "Recycling center"
]

DEFAULT_COUNTRY_MAP = {
    "CANADA": "CAN",
    "UNITED STATES": "USA",
    "USA": "USA",
    "US": "USA",
    "MEXICO": "MEX",
    "ALBANIA": "ALB",
    "GERMANY": "DEU",
    "DEUTSCHLAND": "DEU",
    "FRANCE": "FRA",
    "SPAIN": "ESP",
    "ITALY": "ITA",
    "ARGENTINA": "ARG",
    "CHILE": "CHL",
    "BRAZIL": "BRA",
    "PERU": "PER",
    "COLOMBIA": "COL",
    "AUSTRALIA": "AUS",
    "SOUTH AFRICA": "ZAF",
    "KENYA": "KEN",
    "MOROCCO": "MAR",
    "UNITED KINGDOM": "GBR",
    "UK": "GBR",
    "GREAT BRITAIN": "GBR",
}


def fetch_url(url: str, retries: int = 3, timeout: int = 15) -> str:
    """Fetch URL contents as string with retries."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            if attempt == retries - 1:
                raise e
            time.sleep(1 + attempt)
    return ""


def get_country_mappings() -> Dict[str, str]:
    """Fetch country name -> country code mappings from iOverlander countries page."""
    country_map = dict(DEFAULT_COUNTRY_MAP)
    try:
        html_doc = fetch_url(f"{BASE_URL}/countries")
        matches = re.findall(r"countrycode%5B%5D=([A-Z]{3})[^>]*>[^<]*</a>\s*</td>\s*<td>\s*([^<]+)\s*</td>", html_doc)
        for code, name in matches:
            country_map[name.strip().upper()] = code

        select_matches = re.findall(r"<option\s+value=\"([A-Z]{3})\">\s*([^<]+)\s*</option>", html_doc)
        for code, name in select_matches:
            country_map[name.strip().upper()] = code
    except Exception:
        pass
    return country_map


def resolve_country_code(region_input: str) -> str:
    """Resolve a region/country string or ISO-3 code to an iOverlander country code."""
    cleaned = region_input.strip().upper()
    if len(cleaned) == 3 and cleaned.isalpha():
        return cleaned

    country_map = get_country_mappings()
    if cleaned in country_map:
        return country_map[cleaned]

    for name, code in country_map.items():
        if cleaned in name or name in cleaned:
            return code

    raise ValueError(f"Could not resolve region or country '{region_input}' to a valid 3-letter country code.")


def extract_place_uuids_from_html(html_doc: str) -> List[str]:
    """Extract unique place UUIDs from a search results page HTML."""
    uuids = []
    seen = set()
    matches = re.findall(r"href=\"/places/([a-zA-Z0-9\-]+)\"", html_doc)
    for u in matches:
        if u not in seen and u.lower() not in ("new", "search", "export"):
            seen.add(u)
            uuids.append(u)
    return uuids


def parse_popup_html(poi_id: str, html_doc: str) -> Optional[Dict[str, str]]:
    """Parse place popup HTML returned by /places/{id}/show_popup."""
    if not html_doc or "mapPopup" not in html_doc:
        return None

    m_title = re.search(r"<h1 class=\"h6 ms-2 mb-0\">\s*<a[^>]*>(.*?)</a>\s*\|\s*([^<\n]+)", html_doc, flags=re.DOTALL)
    name = ""
    category = ""
    if m_title:
        name = html.unescape(re.sub(r"<[^>]+>", "", m_title.group(1)).strip())
        category = html.unescape(m_title.group(2).strip())
    else:
        m_fallback_title = re.search(r"<h1[^>]*>(.*?)</h1>", html_doc, flags=re.DOTALL)
        if m_fallback_title:
            name = html.unescape(re.sub(r"<[^>]+>", "", m_fallback_title.group(1)).strip())

    m_gps = re.search(r"GPS:\s*<strong>([^\n<]+)</strong>", html_doc)
    lat, lon = "", ""
    if m_gps:
        gps_str = m_gps.group(1).strip()
        if "," in gps_str:
            parts = [p.strip() for p in gps_str.split(",", 1)]
            lat, lon = parts[0], parts[1]

    m_ele = re.search(r"Elevation:\s*([^\n<]+)", html_doc)
    altitude = ""
    if m_ele:
        ele_str = m_ele.group(1).strip()
        ele_m = re.search(r"([0-9\.\-]+)", ele_str)
        if ele_m:
            altitude = ele_m.group(1)

    m_ver = re.search(r"Verified:\s*([^\n<]+)", html_doc)
    date_verified = m_ver.group(1).strip() if m_ver else ""

    m_desc = re.search(r"<div class=\"prose text-break\"[^>]*>(.*?)</div>", html_doc, flags=re.DOTALL)
    description = ""
    if m_desc:
        desc_text = re.sub(r"<[^>]+>", "", m_desc.group(1)).strip()
        description = html.unescape(desc_text)

    row = {field: "" for field in CSV_FIELDS}
    row["Id"] = poi_id
    row["Name"] = name
    row["Category"] = category
    row["Latitude"] = lat
    row["Longitude"] = lon
    row["Altitude"] = altitude
    row["Date verified"] = date_verified
    row["Description"] = description
    row["Open"] = "Yes"

    return row


def fetch_poi_details(poi_id: str) -> Optional[Dict[str, str]]:
    """Fetch and parse details for a single POI by UUID/id."""
    url = f"{BASE_URL}/places/{poi_id}/show_popup"
    try:
        html_doc = fetch_url(url)
        return parse_popup_html(poi_id, html_doc)
    except Exception as e:
        sys.stderr.write(f"Warning: Failed to fetch POI {poi_id}: {e}\n")
        return None


def is_within_bbox(lat_str: str, lon_str: str,
                   lat_min: Optional[float], lat_max: Optional[float],
                   lon_min: Optional[float], lon_max: Optional[float]) -> bool:
    """Check if lat/lon strings parse to floats and fall within bounding box if specified."""
    try:
        lat = float(lat_str)
        lon = float(lon_str)
    except ValueError:
        return False

    if lat_min is not None and lat < lat_min:
        return False
    if lat_max is not None and lat > lat_max:
        return False
    if lon_min is not None and lon < lon_min:
        return False
    if lon_max is not None and lon > lon_max:
        return False

    return True


def scrape_region(region_input: str,
                  output_csv: str,
                  lat_min: Optional[float] = None,
                  lat_max: Optional[float] = None,
                  lon_min: Optional[float] = None,
                  lon_max: Optional[float] = None,
                  workers: int = 10,
                  max_pages: Optional[int] = None,
                  verbose: bool = False) -> List[Dict[str, str]]:
    """Scrape all POIs for a region/country and write to CSV."""
    country_code = resolve_country_code(region_input)
    print(f"Scraping region '{region_input}' (Country Code: {country_code})...")

    poi_ids: List[str] = []
    seen_ids: Set[str] = set()
    page = 1

    while True:
        if max_pages and page > max_pages:
            print(f"Reached page limit ({max_pages}). Stopping search page collection.")
            break

        url = f"{BASE_URL}/places?countrycode%5B%5D={country_code}&filter=all&page={page}"
        if verbose:
            print(f"Fetching search page {page}: {url}")
        else:
            print(f"Fetching search page {page}...", end="\r", flush=True)

        try:
            html_doc = fetch_url(url)
        except Exception as e:
            print(f"\nError fetching search page {page}: {e}")
            break

        page_uuids = extract_place_uuids_from_html(html_doc)
        new_uuids = [u for u in page_uuids if u not in seen_ids]

        if not new_uuids:
            print(f"\nNo new POIs found on page {page}. Total pages scraped: {page - 1}.")
            break

        for u in new_uuids:
            seen_ids.add(u)
            poi_ids.append(u)

        page += 1

    print(f"\nFound {len(poi_ids)} total POIs. Fetching details concurrently with {workers} workers...")

    scraped_pois: List[Dict[str, str]] = []
    completed = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_id = {executor.submit(fetch_poi_details, poi_id): poi_id for poi_id in poi_ids}
        for future in concurrent.futures.as_completed(future_to_id):
            completed += 1
            if not verbose:
                print(f"Fetching POI details: {completed}/{len(poi_ids)}", end="\r", flush=True)

            poi_data = future.result()
            if poi_data and poi_data.get("Latitude") and poi_data.get("Longitude"):
                if is_within_bbox(poi_data["Latitude"], poi_data["Longitude"], lat_min, lat_max, lon_min, lon_max):
                    scraped_pois.append(poi_data)

    print(f"\nFinished fetching POI details. Valid POIs collected: {len(scraped_pois)}.")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(scraped_pois)

    print(f"Successfully saved {len(scraped_pois)} POIs to '{output_csv}'.")
    return scraped_pois


def main():
    parser = argparse.ArgumentParser(description="Scrape iOverlander POIs for a region into CSV format.")
    parser.add_argument("region", nargs="?", help="Region or country name / 3-letter code (e.g. Canada, CAN, Albania, ALB)")
    parser.add_argument("-r", "--region-name", dest="region_flag", help="Region or country name / code")
    parser.add_argument("-o", "--output", help="Output CSV file path (default: <region>.csv)")
    parser.add_argument("--latMin", type=float, help="Minimum latitude bound")
    parser.add_argument("--latMax", type=float, help="Maximum latitude bound")
    parser.add_argument("--lonMin", type=float, help="Minimum longitude bound")
    parser.add_argument("--lonMax", type=float, help="Maximum longitude bound")
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent worker threads (default: 10)")
    parser.add_argument("--max-pages", type=int, help="Maximum search pages to scrape")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output logging")

    args = parser.parse_args()

    region = args.region or args.region_flag
    if not region:
        parser.error("A region or country must be specified (e.g. `scrape_ioverlander.py Canada` or `-r CAN`).")

    output_csv = args.output
    if not output_csv:
        clean_name = re.sub(r"[^\w\-]", "_", region.lower())
        output_csv = f"{clean_name}.csv"

    scrape_region(
        region_input=region,
        output_csv=output_csv,
        lat_min=args.latMin,
        lat_max=args.latMax,
        lon_min=args.lonMin,
        lon_max=args.lonMax,
        workers=args.workers,
        max_pages=args.max_pages,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
