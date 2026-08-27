import os
import serpapi
import sys

from enum import Enum
from dotenv import load_dotenv
from utils.flight_helpers import (
    get_flights,
    extract_flight_data,
)

load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

# Debug: Verify that the SerpApi API key is available when this module
# is initialized. This helps diagnose environment variable issues,
# especially when the MCP server is running as a subprocess.
# print(
#     f"[DEBUG] SERPAPI KEY exists={bool(SERPAPI_API_KEY)}, "
#     f"length={len(SERPAPI_API_KEY) if SERPAPI_API_KEY else 0}",
#     file=sys.stderr
# )

client = serpapi.Client(
    api_key=SERPAPI_API_KEY
)

class FlightType(str, Enum):
    ROUND_TRIP = "round_trip"
    ONE_WAY = "one_way"


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

flight_type_map = {
    "round_trip": 1,
    "one_way": 2,
}


def search_flights(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    flight_type: FlightType | None = None,
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    return_date: str | None = None,
    bags: int | None = None,
):
    """
    This tool is for SPECIFIC DATE searches ONLY!
    
    If the user asks for:
    - "cheapest flight in a range of date, did not clearly specific the exact outbound and return date"
    DO NOT use this tool! Use cheapest_date_range instead!
    
    Args:
        departure_id: IATA airport code for departure airport (e.g., "SBW")
        arrival_id: IATA airport code for destination airport (e.g., "KUL")
        outbound_date: Departure date in YYYY-MM-DD format (e.g., "2026-08-24")
        flight_type: "round_trip" or "one_way"
        currency: Currency code (e.g., "MYR", "USD")
        travel_class: "economy", "premium_economy", "business", "first"
        return_date: Return date in YYYY-MM-DD format (required for round_trip)
        bags: Number of checked bags

    Returns:
        A list of flight results with currency information included.
    """
    # Debug: Verify that the API key is still available at runtime.
    # This confirms that the MCP server subprocess has access to the environment variables passed from the MCP client.
    # print(
    #     f"[DEBUG] Runtime key exists={bool(os.getenv('SERPAPI_API_KEY'))}, "
    #     f"length={len(os.getenv('SERPAPI_API_KEY', ''))}",
    #     file=sys.stderr
    # )

    print(
        f"[DEBUG] Client type={type(client)}",
        file=sys.stderr
    )
    print(
        f"[TOOL] search_flights("
        f"{departure_id} -> {arrival_id}, "
        f"{outbound_date})"
    )

    print(f"[DEBUG] return_date = {return_date}")
    print(f"[DEBUG] original flight_type = {flight_type}")

    # ---------------------------------------------------------
    # 1. Determine the actual flight type
    # ---------------------------------------------------------

    # If return_date is provided, treat the search as round trip.
    if return_date is not None:
        flight_type = FlightType.ROUND_TRIP

    # If no flight type is provided and there is no return date,
    # default to one-way.
    elif flight_type is None:
        flight_type = FlightType.ONE_WAY

    # If the user explicitly requested round trip but did not
    # provide a return date, reject the request.
    if flight_type == FlightType.ROUND_TRIP and return_date is None:
        raise ValueError("return_date is required for round-trip flights.")

    print(f"[DEBUG] final flight_type = {flight_type}")
    print(f"[DEBUG] SerpApi type = {flight_type_map[flight_type.value]}")

    # ---------------------------------------------------------
    # 2. Build the initial SerpApi request parameters
    # ---------------------------------------------------------
    currency_code = currency if currency is not None else "MYR"

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "type": flight_type_map[flight_type.value],
        "currency": currency_code,  # ← 修复拼写错误
    }

    # Add return date for round-trip searches.
    if return_date is not None:
        params["return_date"] = return_date

    # Add travel class if provided.
    if travel_class is not None:
        params["travel_class"] = travel_class_map[travel_class.value]

    # Add checked baggage count if provided.
    if bags is not None:
        params["bags"] = bags

    print(f"[DEBUG] Initial API params = {params}")

    # ---------------------------------------------------------
    # 3. First API call
    # ---------------------------------------------------------

    outbound_results = client.search(params)

    print("[DEBUG] First API call completed.")

    outbound_flights = get_flights(outbound_results)

    if not outbound_flights:
        print("[DEBUG] No outbound flights found.")
        return []

    # ---------------------------------------------------------
    # 4. Process outbound flights
    # ---------------------------------------------------------

    flight_results = []

    for outbound_flight in outbound_flights:

        # -----------------------------------------------------
        # 5. Round-trip handling
        # -----------------------------------------------------

        if flight_type == FlightType.ROUND_TRIP:

            print("[DEBUG] ROUND TRIP detected.")

            outbound_data = extract_flight_data(
                outbound_flight,
                include_price=False
            )

            total_price = outbound_flight["price"]
            departure_token = outbound_flight.get("departure_token")

            print(f"[DEBUG] departure_token = {departure_token}")

            if not departure_token:
                print("[DEBUG] No departure_token found for this outbound flight.")
                continue

            # -------------------------------------------------
            # 6. Second API call
            # -------------------------------------------------

            return_params = params.copy()
            return_params["departure_token"] = departure_token

            print(f"[DEBUG] Second API params = {return_params}")

            return_results = client.search(return_params)

            print("[DEBUG] Return API call completed.")

            # -------------------------------------------------
            # 7. Extract return flight options
            # -------------------------------------------------

            return_flights = get_flights(return_results)

            return_options = []

            for return_flight in return_flights:
                return_data = extract_flight_data(
                    return_flight,
                    include_price=False
                )
                return_options.append(return_data)

            # -------------------------------------------------
            # 8. Combine outbound + return (with currency)
            # -------------------------------------------------

            flight_results.append(
                {
                    "outbound": outbound_data,
                    "return": return_options,
                    "total_price": total_price,
                    "currency": currency_code,  
                }
            )

        # -----------------------------------------------------
        # 9. One-way / other flight types
        # -----------------------------------------------------

        else:
            outbound_data = extract_flight_data(
                outbound_flight,
                include_price=True
            )
            outbound_data["currency"] = currency_code  
            flight_results.append(outbound_data)

    # ---------------------------------------------------------
    # 10. Return final results
    # ---------------------------------------------------------

    print(f"[DEBUG] Total flight results = {len(flight_results)}")

    return flight_results