import os
import json
import serpapi

from enum import Enum
from dotenv import load_dotenv
from utils.flight_helpers import (
    get_flights,
    extract_flight_data,
)

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

client = serpapi.Client(
    api_key=SERPAPI_API_KEY
)


class TravelClass(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


travel_class_map = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4,
}

def search_multi_city(
    segments: list[dict],
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    bags: int | None = None,
):
    """
    Search multi-city flights using SerpApi.
    """
    if not segments:
        raise ValueError("At least one segment is required.")

    print(f"[TOOL] search_multi_city({len(segments)} segments)")

    multi_city_json = json.dumps(segments)

    params = {
        "engine": "google_flights",
        "type": "3",
        "currency": currency if currency is not None else "MYR",
        "multi_city_json": multi_city_json,
    }

    if travel_class is not None:
        params["travel_class"] = travel_class_map[travel_class.value]

    if bags is not None:
        params["bags"] = bags

    print(f"[DEBUG] Initial API params = {params}")

    results = client.search(params)
    print("[DEBUG] First multi-city API call completed.")

    current_flights = get_flights(results)

    if not current_flights:
        print("[DEBUG] No multi-city flights found.")
        return []

    # 🔥 第一航段按价格排序，取最便宜的
    current_flights.sort(key=lambda x: x.get("price", 999999))
    MAX_FIRST_FLIGHTS = 3
    current_flights = current_flights[:MAX_FIRST_FLIGHTS]
    print(f"[DEBUG] Limited to {len(current_flights)} cheapest first flights")

    itinerary_results = []

    for first_flight in current_flights:
        selected_segments = []
        first_segment_data = extract_flight_data(first_flight, include_price=False)
        selected_segments.append(first_segment_data)

        total_price = first_flight.get("price", 0)
        current_flight = first_flight
        is_complete = True

        for segment_index in range(1, len(segments)):
            departure_token = current_flight.get("departure_token")
            if not departure_token:
                print("[DEBUG] No departure_token found.")
                is_complete = False
                break

            next_params = params.copy()
            next_params["departure_token"] = departure_token

            print(f"[DEBUG] Next segment API params = {next_params}")
            next_results = client.search(next_params)
            print("[DEBUG] Next segment API call completed.")

            next_flights = get_flights(next_results)

            if not next_flights:
                print("[DEBUG] No flights found for next segment.")
                is_complete = False
                break

            # 🔥 按价格排序，取最便宜的 2 个
            next_flights.sort(key=lambda x: x.get("price", 999999))
            MAX_FLIGHTS_PER_SEGMENT = 2
            next_flights = next_flights[:MAX_FLIGHTS_PER_SEGMENT]
            print(f"[DEBUG] Limited to {len(next_flights)} cheapest flights for segment {segment_index + 1}")

            # 🔥 取最便宜的那个
            next_flight = next_flights[0]

            next_segment_data = extract_flight_data(next_flight, include_price=False)
            selected_segments.append(next_segment_data)

            if "price" in next_flight:
                total_price = next_flight["price"]

            current_flight = next_flight

        if is_complete and len(selected_segments) == len(segments):
            itinerary_results.append({
                "segments": selected_segments,
                "total_price": total_price,
            })

            # 🔥 找到 3 个就停止
            if len(itinerary_results) >= 3:
                print("[DEBUG] Reached 3 complete itineraries, stopping")
                break

    # 🔥 按总价排序
    itinerary_results.sort(key=lambda x: x.get("total_price", 999999))

    print(f"[DEBUG] Total multi-city itineraries = {len(itinerary_results)}")
    return itinerary_results