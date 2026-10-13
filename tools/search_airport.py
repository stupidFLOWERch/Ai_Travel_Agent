import os
import requests
import sys

from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY  = os.getenv("RAPIDAPI_KEY")


def search_airport(location: str):
    """
    Search for airports using AeroDataBox.

    Args:
        location:
            City name, airport name, or airport keyword.
            Example: "Japan", "Sibu", "Kuala Lumpur"

    Returns:
        A list of matching airports.
    """
    print(f"[TOOL] search_airport({location})", file=sys.stderr)

    url = "https://aerodatabox.p.rapidapi.com/airports/search/term"

    headers = {
        "Content-Type": "application/json",
        "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY
    }

    params = {
        "q": location,
        "limit": 10
    }

    response = requests.get(
        url,
        headers=headers,
        params=params
    )

    response.raise_for_status()

    return response.json()