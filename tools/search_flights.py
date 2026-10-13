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
    ...
    """
    print(
        f"[DEBUG] Client type={type(client)}",
        file=sys.stderr
    )
    print(
        f"[TOOL] search_flights("
        f"{departure_id} -> {arrival_id}, "
        f"{outbound_date})",
        file=sys.stderr
    )

    print(f"[DEBUG] return_date = {return_date}", file=sys.stderr)
    print(f"[DEBUG] original flight_type = {flight_type}", file=sys.stderr)

    # 1. Determine the actual flight type
    if return_date is not None:
        flight_type = FlightType.ROUND_TRIP
    elif flight_type is None:
        flight_type = FlightType.ONE_WAY

    if flight_type == FlightType.ROUND_TRIP and return_date is None:
        raise ValueError("return_date is required for round-trip flights.")

    print(f"[DEBUG] final flight_type = {flight_type}", file=sys.stderr)
    print(f"[DEBUG] SerpApi type = {flight_type_map[flight_type.value]}", file=sys.stderr)

    # 2. Build the initial SerpApi request parameters
    currency_code = currency if currency is not None else "MYR"

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "type": flight_type_map[flight_type.value],
        "currency": currency_code,
    }

    if return_date is not None:
        params["return_date"] = return_date

    if travel_class is not None:
        params["travel_class"] = travel_class_map[travel_class.value]

    if bags is not None:
        params["bags"] = bags

    print(f"[DEBUG] Initial API params = {params}", file=sys.stderr)

    # 3. First API call
    outbound_results = client.search(params)

    print("[DEBUG] First API call completed.", file=sys.stderr)

    outbound_flights = get_flights(outbound_results)

    if not outbound_flights:
        print("[DEBUG] No outbound flights found.", file=sys.stderr)
        return []

    # 4. Process outbound flights
    flight_results = []

    for outbound_flight in outbound_flights:

        # 5. Round-trip handling
        if flight_type == FlightType.ROUND_TRIP:

            print("[DEBUG] ROUND TRIP detected.", file=sys.stderr)

            outbound_data = extract_flight_data(
                outbound_flight,
                include_price=False
            )

            total_price = outbound_flight["price"]
            departure_token = outbound_flight.get("departure_token")

            print(f"[DEBUG] departure_token = {departure_token}", file=sys.stderr)

            if not departure_token:
                print("[DEBUG] No departure_token found for this outbound flight.", file=sys.stderr)
                continue

            # 6. Second API call
            return_params = params.copy()
            return_params["departure_token"] = departure_token

            print(f"[DEBUG] Second API params = {return_params}", file=sys.stderr)

            return_results = client.search(return_params)

            print("[DEBUG] Return API call completed.", file=sys.stderr)

            # 7. Extract return flight options
            return_flights = get_flights(return_results)

            return_options = []

            for return_flight in return_flights:
                return_data = extract_flight_data(
                    return_flight,
                    include_price=False
                )
                return_options.append(return_data)

            # 8. Combine outbound + return (with currency)
            flight_results.append(
                {
                    "outbound": outbound_data,
                    "return": return_options,
                    "total_price": total_price,
                    "currency": currency_code,
                }
            )

        # 9. One-way / other flight types
        else:
            outbound_data = extract_flight_data(
                outbound_flight,
                include_price=True
            )
            outbound_data["currency"] = currency_code
            flight_results.append(outbound_data)

    # 10. Return final results
    print(f"[DEBUG] Total flight results = {len(flight_results)}", file=sys.stderr)

    return flight_results