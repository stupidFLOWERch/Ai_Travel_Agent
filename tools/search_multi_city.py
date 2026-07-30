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

    Args:
        segments:
            List of flight segments.

            Example:

            [
                {
                    "departure_id": "KUL",
                    "arrival_id": "NRT",
                    "date": "2026-08-05"
                },
                {
                    "departure_id": "NRT",
                    "arrival_id": "LAX",
                    "date": "2026-08-12"
                },
                {
                    "departure_id": "LAX",
                    "arrival_id": "AUS",
                    "date": "2026-08-19"
                }
            ]

        currency:
            Currency used for displaying flight prices.
            Example: "MYR", "USD"

        travel_class:
            Travel class.
            Allowed values:
            - "economy"
            - "premium_economy"
            - "business"
            - "first"

        bags:
            Number of checked bags.

    Returns:
        A list of multi-city itinerary results.
    """

    if not segments:
        raise ValueError(
            "At least one segment is required."
        )

    print(
        f"[TOOL] search_multi_city("
        f"{len(segments)} segments)"
    )

    # ---------------------------------------------------------
    # 1. Convert segments into SerpApi multi_city_json format
    # ---------------------------------------------------------

    multi_city_json = json.dumps(segments)

    params = {
        "engine": "google_flights",
        "type": "3",
        "currency": (
            currency
            if currency is not None
            else "MYR"
        ),
        "multi_city_json": multi_city_json,
    }

    # Add travel class if provided.
    if travel_class is not None:
        params["travel_class"] = (
            travel_class_map[
                travel_class.value
            ]
        )

    # Add checked baggage count if provided.
    if bags is not None:
        params["bags"] = bags

    print(
        f"[DEBUG] Initial API params = {params}"
    )

    # ---------------------------------------------------------
    # 2. First API call
    # ---------------------------------------------------------

    results = client.search(params)

    print(
        "[DEBUG] First multi-city API call completed."
    )

    print(
        f"[DEBUG] Result keys = {results.keys()}"
    )

    current_flights = get_flights(results)

    if not current_flights:
        print(
            "[DEBUG] No multi-city flights found."
        )
        return []

    # ---------------------------------------------------------
    # 3. Store final itinerary results
    # ---------------------------------------------------------

    itinerary_results = []

    # ---------------------------------------------------------
    # 4. Process each possible first segment flight
    # ---------------------------------------------------------

    for first_flight in current_flights:

        selected_segments = []

        # Extract the first segment.
        first_segment_data = extract_flight_data(
            first_flight,
            include_price=False,
        )

        selected_segments.append(
            first_segment_data
        )

        # Get the current total price.
        total_price = first_flight.get(
            "price",
            0,
        )

        # Keep track of the current flight.
        # Its departure_token is needed to get the next segment.
        current_flight = first_flight

        # -----------------------------------------------------
        # 5. Get remaining segments using departure_token
        # -----------------------------------------------------

        for segment_index in range(
            1,
            len(segments),
        ):

            departure_token = current_flight.get(
                "departure_token"
            )

            print(
                f"[DEBUG] Segment "
                f"{segment_index + 1}: "
                f"departure_token = "
                f"{departure_token}"
            )

            if not departure_token:
                print(
                    "[DEBUG] No departure_token "
                    "found. Cannot retrieve "
                    "next segment."
                )
                break

            # -------------------------------------------------
            # 6. Request the next segment
            # -------------------------------------------------

            next_params = params.copy()

            next_params[
                "departure_token"
            ] = departure_token

            print(
                f"[DEBUG] Next segment API params = "
                f"{next_params}"
            )

            next_results = client.search(
                next_params
            )

            print(
                "[DEBUG] Next segment API call "
                "completed."
            )

            print(
                f"[DEBUG] Next result keys = "
                f"{next_results.keys()}"
            )

            next_flights = get_flights(
                next_results
            )

            if not next_flights:
                print(
                    "[DEBUG] No flights found "
                    "for next segment."
                )
                break

            # -------------------------------------------------
            # 7. Select the first available flight
            # -------------------------------------------------

            next_flight = next_flights[0]

            next_segment_data = extract_flight_data(
                next_flight,
                include_price=False,
            )

            selected_segments.append(
                next_segment_data
            )

            # Update total price.
            if "price" in next_flight:
                total_price = next_flight["price"]

            # Update current flight.
            # The departure_token from this flight will be used to retrieve the next segment.
            current_flight = next_flight

        # -----------------------------------------------------
        # 8. Only add complete itineraries
        # -----------------------------------------------------

        if len(selected_segments) == len(
            segments
        ):
            itinerary_results.append(
                {
                    "segments": selected_segments,
                    "total_price": total_price,
                }
            )

    # ---------------------------------------------------------
    # 9. Return final results
    # ---------------------------------------------------------

    print(
        f"[DEBUG] Total multi-city itineraries = "
        f"{len(itinerary_results)}"
    )

    return itinerary_results