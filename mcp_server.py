import sys
import os
import json

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from fastmcp import FastMCP

from tools.search_flights import search_flights, FlightType 
from tools.search_multi_city import search_multi_city
from tools.cheapest_date_range import cheapest_date_range
from tools.search_airport import search_airport

mcp = FastMCP("Flight Search MCP")


@mcp.tool()
def search_flights_tool(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    flight_type: str = "one_way",
    return_date: str = None,
    currency: str = "MYR"
) -> str:
    """search specific date flights (one-way/round-trip)"""
    try:
        # 🔥 convert str to Enum
        if flight_type == "one_way":
            flight_type_enum = FlightType.ONE_WAY
        elif flight_type == "round_trip":
            flight_type_enum = FlightType.ROUND_TRIP
        else:
            flight_type_enum = FlightType.ONE_WAY
            
        if return_date:
            # has return date: pass return_date
            result = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                return_date=return_date,
                currency=currency
            )
        else:
            # no return date: do not pass return_date
            result = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                currency=currency
                # 注意：这里没有 return_date 参数
            )
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cheapest_date_range_tool(
    departure_id: str,
    arrival_id: str,
    start_date: str,
    end_date: str,
    flight_type: str = "one_way",
    duration: int = 0,
    currency: str = "MYR"
) -> str:
    """find the cheapest flights in the date range"""
    try:
        if flight_type == "one_way":
            flight_type_enum = FlightType.ONE_WAY
        elif flight_type == "round_trip":
            flight_type_enum = FlightType.ROUND_TRIP
        else:
            flight_type_enum = FlightType.ONE_WAY

        if duration > 0:
            result = cheapest_date_range(
                departure_id=departure_id,
                arrival_id=arrival_id,
                start_date=start_date,
                end_date=end_date,
                flight_type=flight_type_enum,
                duration=duration,
                currency=currency
            )

        else:
            result = cheapest_date_range(
                departure_id=departure_id,
                arrival_id=arrival_id,
                start_date=start_date,
                end_date=end_date,
                flight_type=flight_type_enum,
                currency=currency
            )

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_multi_city_tool(segments: list, currency: str = "MYR") -> str:
    """search multi-city flights"""
    try:
        result = search_multi_city(segments=segments, currency=currency)
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_airport_tool(location: str) -> str:
    """search airport IATA code"""
    try:
        result = search_airport(location=location)
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()