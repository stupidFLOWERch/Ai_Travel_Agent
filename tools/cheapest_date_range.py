import os
import serpapi

from enum import Enum
from dotenv import load_dotenv
from datetime import datetime, timedelta
from tools.search_flights import search_flights

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

class FlightType(str, Enum):
    ROUND_TRIP = "round_trip"
    ONE_WAY = "one_way"

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

def cheapest_date_range(
    departure_id: str,
    arrival_id: str,
    start_date: str,
    end_date: str,
    flight_type: FlightType | None = None,
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    duration: int | None = None,
    bags: int | None = None
):  
    """
    MUST USE THIS TOOL FOR DATE RANGE SEARCHES 
    
    Use this when user says:
    - "cheapest flight between DATE1 and DATE2"
    - "cheapest round trip between DATE1 and DATE2, stay N days"
    - "find cheapest date from DATE1 to DATE2"
    - "find cheapest flight in MONTH"
    
    DO NOT use search_flights for date range searches!
    
    Args:
        departure_id: IATA code for departure airport
        arrival_id: IATA code for destination airport
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        flight_type: "one_way" or "round_trip"
        currency: Currency code (default: MYR)
        travel_class: Travel class
        duration: Number of days for round trip (required for round_trip)
        bags: Number of checked bags
    
    Returns:
        The cheapest flight option found in between the date range
    """
    if duration is not None and duration > 0:
        flight_type = FlightType.ROUND_TRIP

    # Default to one-way if not specified
    if flight_type is None:
        flight_type = FlightType.ONE_WAY
    
    # For round trip, duration is required
    if flight_type == FlightType.ROUND_TRIP and duration is None:
        return {
            "error": "duration is required for round-trip cheapest date search"
        }

    if flight_type == FlightType.ONE_WAY:
        return search_cheapest_one_way(
            departure_id=departure_id,
            arrival_id=arrival_id,
            start_date=start_date,
            end_date=end_date,
            currency=currency,
            travel_class=travel_class,
            bags=bags,
        )

    elif flight_type == FlightType.ROUND_TRIP:
        return search_cheapest_round_trip(
        departure_id=departure_id,
        arrival_id=arrival_id,
        start_date=start_date,
        end_date=end_date,
        duration=duration,          # ← 第5个参数
        currency=currency,          # ← 第6个参数
        travel_class=travel_class,  # ← 第7个参数
        bags=bags,                  # ← 第8个参数
    )


    return {
        "error": "Unsupported or missing flight type"
    }

def generate_dates(
    start_date: str,
    end_date: str,
) -> list[str]:

    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")

    dates = []

    current = start

    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)

    return dates

def search_cheapest_one_way(
    departure_id: str,
    arrival_id: str,
    start_date: str,
    end_date: str,
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    bags: int | None = None
    ):
    cheapest = None
    cheapest_date = None
    dates = generate_dates(start_date, end_date)
    print(f"[TOOL] search_cheapest_oneway checking {len(dates)} outbound dates...")
    for date in dates:
        results = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=date,
                flight_type=FlightType.ONE_WAY,
                currency=currency,
                travel_class=travel_class,
                bags=bags,
            )

        for flight in results:
            price = flight.get("price")

            if price is None:
                continue

            if cheapest is None or price < cheapest["price"]:
                cheapest = flight
                cheapest_date = date

    if cheapest is None:
        return {
            "error": f"No flights found between {start_date} and {end_date}"
        }

    cheapest["cheapest_date"] = cheapest_date

    return [cheapest]
        
def search_cheapest_round_trip(
    departure_id: str,
    arrival_id: str,
    start_date: str,
    end_date: str,
    duration: int,
    currency: str | None = None,
    travel_class: TravelClass | None = None,
    bags: int | None = None
):
   
    
    cheapest = None
    cheapest_outbound_date = None
    cheapest_return_date = None
    
    outbound_dates = generate_dates(start_date, end_date)
    
    print(f"[TOOL] search_cheapest_round_trip checking {len(outbound_dates)} outbound dates...")
    
    for outbound_date in outbound_dates:
        # Calculate return date based on duration
        outbound_datetime = datetime.strptime(outbound_date, "%Y-%m-%d")
        return_datetime = outbound_datetime + timedelta(days=duration)
        return_date = return_datetime.strftime("%Y-%m-%d")
        
        # Skip if return date is beyond end_date
        if return_datetime > datetime.strptime(end_date, "%Y-%m-%d"):
            continue
        
        print(
            f"[DEBUG] Calling search_flights: "
            f"{outbound_date} -> {return_date}"
        )

        try:
            results = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=FlightType.ROUND_TRIP,
                currency=currency,
                travel_class=travel_class,
                return_date=return_date,
                bags=bags,
            )
            
            for flight in results:
                price = flight.get("total_price")
                
                if price is None:
                    continue
                
                if cheapest is None or price < cheapest.get("total_price"):
                    cheapest = flight
                    cheapest_outbound_date = outbound_date
                    cheapest_return_date = return_date
                    
        except Exception as e:
            print(f"[DEBUG] Error searching dates {outbound_date}->{return_date}: {e}")
            continue
    
    if cheapest is None:
        return {"error": f"No round-trip flights found between {start_date} and {end_date}"}
    
    # Extract outbound and return data separately
    cheapest["cheapest_outbound_date"] = (cheapest_outbound_date)

    cheapest["cheapest_return_date"] = (cheapest_return_date)

    return [cheapest]
