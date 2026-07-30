def extract_flight_data(flight, include_price=True):
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
    
def get_flights(results):
    """
    Get flight results from SerpApi.

    Prefer best_flights.
    If unavailable, fall back to other_flights.
    """

    flights = results.get("best_flights", [])

    if not flights:
        flights = results.get("other_flights", [])

    return flights