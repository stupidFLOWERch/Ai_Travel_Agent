import sys
import os
import json
import asyncio
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastmcp import FastMCP, Client

from tools.search_flights import search_flights, FlightType
from tools.search_multi_city import search_multi_city
from tools.cheapest_date_range import cheapest_date_range
from tools.search_airport import search_airport
from tools.price_advisor import analyze_price_insights

logging.basicConfig(level=logging.WARNING)

load_dotenv()

mcp = FastMCP("Travel Agent MCP")


# ==================== Flight Tools ====================

@mcp.tool()
def search_flights_tool(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    flight_type: str = "one_way",
    return_date: str = None,
    currency: str = "MYR"
) -> str:
    """Search for flights on a specific date (one-way or round-trip)."""
    try:
        if flight_type == "one_way":
            flight_type_enum = FlightType.ONE_WAY
        elif flight_type == "round_trip":
            flight_type_enum = FlightType.ROUND_TRIP
        else:
            flight_type_enum = FlightType.ONE_WAY

        if return_date:
            result = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                return_date=return_date,
                currency=currency
            )
        else:
            result = search_flights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                currency=currency
            )

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


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
    """Find the cheapest flight within a date range."""
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
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def search_multi_city_tool(segments: list, currency: str = "MYR") -> str:
    """Search multi-city flights with multiple segments."""
    try:
        result = search_multi_city(segments=segments, currency=currency)
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def search_airport_tool(location: str) -> str:
    """Search for airport IATA codes by city or airport name."""
    try:
        result = search_airport(location=location)
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


@mcp.tool()
def analyze_price_insights_tool(
    departure_id: str,
    arrival_id: str,
    outbound_date: str,
    flight_type: str = "one_way",
    return_date: str = None,
    currency: str = "MYR"
) -> str:
    """Analyze if a flight price is good to buy based on historical price data."""
    try:
        if flight_type == "one_way":
            flight_type_enum = FlightType.ONE_WAY
        elif flight_type == "round_trip":
            flight_type_enum = FlightType.ROUND_TRIP
        else:
            flight_type_enum = FlightType.ONE_WAY

        if return_date:
            result = analyze_price_insights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                return_date=return_date,
                currency=currency
            )
        else:
            result = analyze_price_insights(
                departure_id=departure_id,
                arrival_id=arrival_id,
                outbound_date=outbound_date,
                flight_type=flight_type_enum,
                currency=currency
            )

        return json.dumps(result, indent=2, ensure_ascii=False, default=str)

    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


# ==================== Hotel Tools ====================

async def _async_search_hotels(
    query: str,
    arrival: str,
    departure: str,
    adults: int,
    currency: str
):
    """Internal async helper: call Trivago MCP via fastmcp.Client."""
    try:
        async with Client("https://mcp.trivago.com/mcp") as client:
            result = await client.call_tool(
                "trivago-accommodation-search",
                {
                    "query": query,
                    "arrival": arrival,
                    "departure": departure,
                    "adults": adults,
                    "currency": currency
                }
            )

            # Extract text content from CallToolResult
            if hasattr(result, "content") and result.content:
                for content_item in result.content:
                    if hasattr(content_item, "text"):
                        try:
                            data = json.loads(content_item.text)
                            # Extract the actual hotel data from the "output" field
                            if isinstance(data, dict) and "output" in data:
                                return data["output"]
                            return data
                        except json.JSONDecodeError:
                            return content_item.text
                return {"error": "No text content found in result"}

            return {"error": "Invalid result structure"}

    except Exception as e:
        logging.error(f"Trivago search failed: {e}", exc_info=True)
        return {"error": str(e)}


@mcp.tool()
async def search_hotels_tool(
    query: str,
    arrival: str,
    departure: str,
    adults: int = 2,
    currency: str = "MYR"
) -> str:
    """Search for hotels and accommodations via Trivago."""
    result = await _async_search_hotels(
        query=query,
        arrival=arrival,
        departure=departure,
        adults=adults,
        currency=currency
    )

    return json.dumps(
        result,
        indent=2,
        ensure_ascii=False,
        default=str
    )


if __name__ == "__main__":
    mcp.run()