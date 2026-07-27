import os
import serpapi

from enum import Enum
from dotenv import load_dotenv


load_dotenv()

SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")

client = serpapi.Client(
    api_key=SERPAPI_API_KEY
)


class FlightType(str, Enum):
    ROUND_TRIP = "round_trip"
    ONE_WAY = "one_way"
    MULTI_CITY = "multi_city"


class TravelClass(str, Enum):
    ECONOMY = "economy"
    PREMIUM_ECONOMY = "premium_economy"
    BUSINESS = "business"
    FIRST = "first"


travel_class_map = {
    "economy": 1,
    "premium_economy": 2,
    "business": 3,
    "first": 4
}


flight_type_map = {
    "round_trip": 1,
    "one_way": 2,
    "multi_city": 3,
}


def search_flights(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    flight_type: FlightType | None = None,
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    return_date: str | None = None,
    bags: int | None = None
):
    """
    Search Google Flights using SerpApi.

    Args:
        departure_id:
            IATA airport code for departure airport.
            Example: "SBW"

        arrival_id:
            IATA airport code for destination airport.
            Example: "KUL"

        outbound_date:
            Departure date in YYYY-MM-DD format.
            Example: "2026-08-24"

        flight_type:
            Flight type.
            Allowed values:
            - "round_trip"
            - "one_way"
            - "multi_city"

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

        return_date:
            Return date in YYYY-MM-DD format.
            Required for round-trip searches.

        bags:
            Number of checked bags.
    """

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
    }

    # Flight type
    if flight_type is not None:
        params["type"] = flight_type_map[flight_type.value]

    # Return date
    if return_date is not None:
        params["return_date"] = return_date

    # Currency
    if currency is not None:
        params["currency"] = currency
    else:
        params["currency"] = "MYR"

    # Travel class
    if travel_class is not None:
        params["travel_class"] = travel_class_map[travel_class.value]

    # Number of bags
    if bags is not None:
        params["bags"] = bags

    results = client.search(params)

    flights = results.get("best_flights", [])

    if not flights:
        flights = results.get("other_flights", [])

    flight_results = []

    for flight in flights:

        first_leg = flight["flights"][0]

        flight_results.append({
            "airline": first_leg["airline"],
            "flight_number": first_leg["flight_number"],
            "departure": first_leg["departure_airport"]["name"],
            "departure_time": first_leg["departure_airport"]["time"],
            "arrival": first_leg["arrival_airport"]["name"],
            "arrival_time": first_leg["arrival_airport"]["time"],
            "duration_minutes": flight["total_duration"],
            "price": flight["price"],
            "travel_class": first_leg["travel_class"]
        })

    return flight_results