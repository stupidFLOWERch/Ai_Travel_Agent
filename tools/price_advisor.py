import os
import serpapi
from dotenv import load_dotenv
from enum import Enum
from datetime import datetime

load_dotenv()
SERPAPI_API_KEY = os.getenv("SERPAPI_API_KEY")
client = serpapi.Client(api_key=SERPAPI_API_KEY)


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

# Currency symbol mapping
CURRENCY_SYMBOLS = {
    "MYR": "RM",
    "USD": "$",
    "SGD": "S$",
    "EUR": "€",
    "GBP": "£",
    "JPY": "¥",
    "CNY": "¥",
    "AUD": "A$",
    "THB": "฿",
}


def analyze_price_trend(price_history: list, days: int = 7) -> dict:
    """
    Analyze price trend from historical data.
    
    Args:
        price_history: List of [timestamp, price] pairs from SerpAPI
        days: Number of recent days to analyze (default: 7)
    
    Returns:
        dict: {
            "trend": "rising" | "falling" | "stable" | "insufficient_data",
            "recent_prices": [price1, price2, ...],
            "lowest_recent": lowest_price,
            "highest_recent": highest_price,
            "summary": "Price has been trending ..."
        }
    """
    if not price_history or len(price_history) < 2:
        return {
            "trend": "insufficient_data",
            "recent_prices": [],
            "lowest_recent": None,
            "highest_recent": None,
            "summary": "Not enough historical data to determine price trend."
        }
    
    # Get recent data points (last 'days' days or all if less)
    recent_data = price_history[-days:] if len(price_history) >= days else price_history
    recent_prices = [p[1] for p in recent_data]
    
    # Calculate trend
    if len(recent_prices) >= 3:
        # Compare first half vs second half
        mid = len(recent_prices) // 2
        first_half_avg = sum(recent_prices[:mid]) / mid
        second_half_avg = sum(recent_prices[mid:]) / (len(recent_prices) - mid)
        
        if second_half_avg < first_half_avg * 0.97:  # 3% drop
            trend = "falling"
        elif second_half_avg > first_half_avg * 1.03:  # 3% rise
            trend = "rising"
        else:
            trend = "stable"
    else:
        # Simple comparison for few data points
        if recent_prices[-1] < recent_prices[0]:
            trend = "falling"
        elif recent_prices[-1] > recent_prices[0]:
            trend = "rising"
        else:
            trend = "stable"
    
    # Generate summary
    if trend == "falling":
        summary = f"Price has been trending DOWN recently. Latest: {recent_prices[-1]}, Lowest recent: {min(recent_prices)}"
    elif trend == "rising":
        summary = f"Price has been trending UP recently. Latest: {recent_prices[-1]}, Highest recent: {max(recent_prices)}"
    elif trend == "stable":
        summary = f"Price has been relatively STABLE recently around {recent_prices[-1]}"
    else:
        summary = "Insufficient data for trend analysis."
    
    return {
        "trend": trend,
        "recent_prices": recent_prices,
        "lowest_recent": min(recent_prices) if recent_prices else None,
        "highest_recent": max(recent_prices) if recent_prices else None,
        "summary": summary
    }


def analyze_price_insights(
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
    Analyze if a flight price is good to buy based on historical price data.
    
    IMPORTANT: You MUST call this tool with the SAME flight details from the search.
    Use the departure_id, arrival_id, and outbound_date from the flight you want to analyze.
    
    Args:
        departure_id: IATA code of departure airport (e.g., "SBW")
        arrival_id: IATA code of arrival airport (e.g., "KUL")
        outbound_date: Travel date in YYYY-MM-DD format (e.g., "2026-08-12")
        flight_type: "one_way" or "round_trip" (default: "one_way")
        return_date: Return date in YYYY-MM-DD format (required for round_trip)
        currency: Currency code (default: "MYR")
        travel_class: Travel class (economy, premium_economy, business, first)
        bags: Number of checked bags
    
    Returns:
        Price analysis including:
        - currency: Currency code
        - currency_symbol: Currency symbol (e.g., "RM")
        - price: Current lowest price
        - price_level: "cheap", "typical", "expensive", or "unknown"
        - typical_range: Typical price range [min, max]
        - trend: Price trend analysis
        - advice: Purchase advice with price details
        - is_good_deal: Boolean indicating if it's a good deal
    """
    try:
        # Determine currency and symbol (ensure not None)
        currency_code = currency if currency is not None else "MYR"
        currency_symbol = CURRENCY_SYMBOLS.get(currency_code, currency_code)

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
            return {
                "currency": currency_code,
                "currency_symbol": currency_symbol,
                "error": "return_date is required for round-trip flights."
            }

        # 1. Call SerpAPI
        params = {
            "engine": "google_flights",
            "departure_id": departure_id,
            "arrival_id": arrival_id,
            "outbound_date": outbound_date,
            "type": flight_type_map[flight_type.value],
            "currency": currency_code,
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

        outbound_results = client.search(params)
        price_insights = outbound_results.get("price_insights")

        if not price_insights:
            return {
                "currency": currency_code,
                "currency_symbol": currency_symbol,
                "error": "Unable to retrieve price analysis data. Please try again later."
            }

        # 2. Analyze price
        current_price = price_insights.get("lowest_price")
        typical_range = price_insights.get("typical_price_range", [0, 0])
        price_level = price_insights.get("price_level")  # "cheap", "typical", "expensive"
        price_history = price_insights.get("price_history", [])

        # Handle case where price_level is None
        if price_level is None:
            price_level = "unknown"

        # 3. Analyze price trend
        trend_data = analyze_price_trend(price_history)
        trend = trend_data["trend"]
        trend_summary = trend_data["summary"]

        # 4. Generate advice with trend information
        advice = ""
        is_good_deal = False

        if price_level == "cheap":
            advice = (
                f"✅ Current price {currency_symbol}{current_price} is LOW - good time to buy! "
                f"(Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]}) "
                f"{trend_summary}"
            )
            is_good_deal = True
        elif price_level == "typical":
            if trend == "falling":
                advice = (
                    f"ℹ️ Current price {currency_symbol}{current_price} is in normal range and TRENDING DOWN. "
                    f"Good time to buy if you like the date. "
                    f"(Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]})"
                )
            else:
                advice = (
                    f"ℹ️ Current price {currency_symbol}{current_price} is within normal range. "
                    f"Consider buying if you're satisfied with the date. "
                    f"(Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]}) "
                    f"{trend_summary}"
                )
            is_good_deal = False
        elif price_level == "expensive":
            if trend == "falling":
                advice = (
                    f"⚠️ Current price {currency_symbol}{current_price} is high but TRENDING DOWN. "
                    f"Consider waiting a bit longer if you can. "
                    f"(Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]})"
                )
            else:
                advice = (
                    f"⚠️ Current price {currency_symbol}{current_price} is ABOVE typical range. "
                    f"Consider waiting or choosing another date. "
                    f"(Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]}) "
                    f"{trend_summary}"
                )
            is_good_deal = False
        else:
            advice = (
                f"❓ Current price {currency_symbol}{current_price}. Price level unknown. "
                f"Typical range: {currency_symbol}{typical_range[0]} - {currency_symbol}{typical_range[1]}. "
                f"{trend_summary}"
            )
            is_good_deal = False

        return {
            "currency": currency_code,
            "currency_symbol": currency_symbol,
            "price": current_price,
            "price_level": price_level,
            "typical_range": typical_range,
            "trend": trend,
            "trend_summary": trend_summary,
            "recent_prices": trend_data["recent_prices"][-5:],  # Last 5 prices
            "advice": advice,
            "is_good_deal": is_good_deal,
        }

    except serpapi.SerpApiClientException as e:
        error_msg = str(e)
        # Provide more user-friendly error messages
        if "400" in error_msg:
            return {
                "currency": currency_code if currency else "MYR",
                "currency_symbol": CURRENCY_SYMBOLS.get(currency_code, currency_code) if currency else "RM",
                "error": f"Flight search failed. Please check that: 1) Dates are in the future and return_date is after outbound_date, 2) Airport codes are valid. Error: {error_msg}"
            }
        return {
            "currency": currency_code if currency else "MYR",
            "error": f"SerpAPI call failed: {error_msg}"
        }
    except Exception as e:
        return {
            "currency": currency_code if currency else "MYR",
            "error": f"Analysis failed: {str(e)}"
        }