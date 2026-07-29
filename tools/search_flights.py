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

def _extract_flight_data(flight, include_price=True):
    """
    Extract relevant flight information from a SerpApi flight result.
    """

    legs = flight.get("flights", [])
    layovers = flight.get("layovers", [])

    if not legs:
        return None

    first_leg = legs[0]
    last_leg = legs[-1]

    flight_data = {
        "airline": first_leg.get("airline"),
        "departure": first_leg.get(
            "departure_airport", {}
        ).get("name"),
        "departure_airport_id": first_leg.get(
            "departure_airport", {}
        ).get("id"),
        "departure_time": first_leg.get(
            "departure_airport", {}
        ).get("time"),
        "arrival": last_leg.get(
            "arrival_airport", {}
        ).get("name"),
        "arrival_airport_id": last_leg.get(
            "arrival_airport", {}
        ).get("id"),
        "arrival_time": last_leg.get(
            "arrival_airport", {}
        ).get("time"),
        "duration_minutes": flight.get(
            "total_duration"
        ),
        "travel_class": first_leg.get(
            "travel_class"
        ),
        "number_of_stops": len(legs) - 1,
        "layovers": [
            {
                "airport": layover.get("name"),
                "airport_id": layover.get("id"),
                "duration_minutes": layover.get(
                    "duration"
                ),
            }
            for layover in layovers
        ],
        "segments": [
            {
                "airline": leg.get("airline"),
                "flight_number": leg.get(
                    "flight_number"
                ),
                "departure": leg.get(
                    "departure_airport", {}
                ).get("name"),
                "departure_airport_id": leg.get(
                    "departure_airport", {}
                ).get("id"),
                "departure_time": leg.get(
                    "departure_airport", {}
                ).get("time"),
                "arrival": leg.get(
                    "arrival_airport", {}
                ).get("name"),
                "arrival_airport_id": leg.get(
                    "arrival_airport", {}
                ).get("id"),
                "arrival_time": leg.get(
                    "arrival_airport", {}
                ).get("time"),
                "duration_minutes": leg.get(
                    "duration"
                ),
                "travel_class": leg.get(
                    "travel_class"
                ),
                "overnight": leg.get(
                    "overnight",
                    False
                ),
            }
            for leg in legs
        ],
    }

    if include_price:
        flight_data["price"] = flight.get(
            "price"
        )

    return flight_data
    

def _get_flights(results):
    """
    Get flight results from SerpApi.

    Prefer best_flights.
    If unavailable, fall back to other_flights.
    """

    flights = results.get("best_flights", [])

    if not flights:
        flights = results.get("other_flights", [])

    return flights
    

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

    Returns:
        A list of flight results.

        One-way example:

        [
            {
                "airline": "Batik Air",
                "flight_numbers": ["OD 1907"],
                "departure": "Sibu Airport",
                "departure_time": "2026-08-24 17:20",
                "arrival": "Kuala Lumpur International Airport",
                "arrival_time": "2026-08-24 19:30",
                "duration_minutes": 130,
                "price": 559,
                "travel_class": "Economy"
            }
        ]

        Round-trip example:

        [
            {
                "outbound": {
                    ...
                },
                "return": [
                    {
                        ...
                    }
                ]
            }
        ]
    """

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
    if (
        flight_type == FlightType.ROUND_TRIP
        and return_date is None
    ):
        raise ValueError(
            "return_date is required for round-trip flights."
        )

    print(f"[DEBUG] final flight_type = {flight_type}")
    print(
        f"[DEBUG] SerpApi type = "
        f"{flight_type_map[flight_type.value]}"
    )

    # ---------------------------------------------------------
    # 2. Build the initial SerpApi request parameters
    # ---------------------------------------------------------

    params = {
        "engine": "google_flights",
        "departure_id": departure_id,
        "arrival_id": arrival_id,
        "outbound_date": outbound_date,
        "type": flight_type_map[flight_type.value],
        "currency": currency if currency is not None else "MYR",
    }

    # Add return date for round-trip searches.
    if return_date is not None:
        params["return_date"] = return_date

    # Add travel class if provided.
    if travel_class is not None:
        params["travel_class"] = travel_class_map[
            travel_class.value
        ]

    # Add checked baggage count if provided.
    if bags is not None:
        params["bags"] = bags

    print(f"[DEBUG] Initial API params = {params}")

    # ---------------------------------------------------------
    # 3. First API call
    # ---------------------------------------------------------

    outbound_results = client.search(params)

    print(
        f"[DEBUG] First API call completed. "
        f"Result keys = {outbound_results.keys()}"
    )

    outbound_flights = _get_flights(outbound_results)

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

            outbound_data = _extract_flight_data(
                outbound_flight,
                include_price=False
            )

            total_price = outbound_flight["price"]
            # Get the token associated with this specific
            # outbound flight.
            departure_token = outbound_flight.get(
                "departure_token"
            )

            print(
                f"[DEBUG] departure_token = "
                f"{departure_token}"
            )

            if not departure_token:
                print(
                    "[DEBUG] No departure_token found "
                    "for this outbound flight."
                )
                continue

            # -------------------------------------------------
            # 6. Second API call
            # -------------------------------------------------
            #
            # Keep all original search parameters and add
            # departure_token to select this specific
            # outbound flight.
            #
            # Do NOT modify the original params directly.
            # Use a copy instead.
            # -------------------------------------------------

            return_params = params.copy()

            return_params["departure_token"] = (
                departure_token
            )

            print(
                f"[DEBUG] Second API params = "
                f"{return_params}"
            )

            return_results = client.search(
                return_params
            )

            print(
                "[DEBUG] Return API call completed."
            )

            print(
                f"[DEBUG] Return result keys = "
                f"{return_results.keys()}"
            )

            # -------------------------------------------------
            # 7. Extract return flight options
            # -------------------------------------------------

            return_flights = _get_flights(
                return_results
            )

            return_options = []

            for return_flight in return_flights:

                return_data = _extract_flight_data(
                    return_flight,
                    include_price=False
                )

                return_options.append(
                    return_data
                )

            # -------------------------------------------------
            # 8. Combine outbound + return
            # -------------------------------------------------

            flight_results.append(
                {
                    "outbound": outbound_data,
                    "return": return_options,
                    "total_price": total_price
                }
            )

        # -----------------------------------------------------
        # 9. One-way / other flight types
        # -----------------------------------------------------

        else:
            outbound_data = _extract_flight_data(
                outbound_flight,
                include_price=True
            )

            flight_results.append(
                outbound_data
            )

    # ---------------------------------------------------------
    # 10. Return final results
    # ---------------------------------------------------------

    print(
        f"[DEBUG] Total flight results = "
        f"{len(flight_results)}"
    )

    return flight_results
    
