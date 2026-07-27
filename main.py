import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools.flight_tools import search_airport, search_flights

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Create Gemini client
client = genai.Client(
    api_key=GEMINI_API_KEY
)

# Define tools for Gemini
tools = [
    search_airport,
    search_flights
]

# Agent instructions
system_prompt = """
You are an AI Travel Agent.

Your job is to help users search for flights.

When the user asks for a flight:

1. Identify the departure location.
2. Identify the destination.
3. Identify the travel type, such as one-way or round-trip.
4. Identify the flight class, such as economy or business.
5. Identify the travel date.
6. If the user provides city or airport names instead of IATA codes,
   use the search_airport tool to find the correct airport code.
7. Use the search_flights tool to search for available flights.
8. If the user asks for the cheapest flight, compare the prices of the results.
9. Present the most relevant flight options clearly.
10. Do not invent flight information.

You can use these tools:
- search_airport: Find the airport and IATA code for a location.
- search_flights: Search available flights using airport IATA codes.
"""

# Create model configuration
config = types.GenerateContentConfig(
    tools=tools,
    system_instruction=system_prompt
)

def main():
    user_input = input("You: ")

    response = client.models.generate_content(
        model ="gemini-3.1-flash-lite",
        contents=user_input,
        config=config
    )

    print("\nAgent: ")
    print(response.text)

if __name__ == "__main__":
    main()