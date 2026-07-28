import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools.search_flights import search_flights
from tools.search_airport import search_airport


load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# Give Python functions directly to Gemini
tools = [
    search_airport,
    search_flights
]


system_prompt = """
You are an AI Travel Agent.

Your job is to help users search for flights.

When the user asks for a flight:

1. Identify the departure location.
2. Identify the destination.
3. Identify the travel type, such as one_way, round_trip or multi_city.
4. Identify the flight class, such as economy or business.
5. Identify the travel date.

6. If the user provides a city name, airport name,
   or location instead of an IATA airport code,
   use the search_airport tool to find the correct airport.

7. After obtaining the departure and destination airport IATA codes,
   use the search_flights tool to search for available flights.

8. If the user asks for the cheapest flight,
   compare the prices returned by the search_flights tool.

9. Present the most relevant flight options clearly.

10. Do not invent flight information.

Important rules:

- If the user requests a round-trip flight but does not provide a return date,
  do not call the search_flights tool yet.
- Ask the user for the return date first.
- Only call search_flights after the return date is provided.

Available tools:

- search_airport:
  Search for an airport using a city name,
  airport name, or location.

- search_flights:
  Search available flights using airport IATA codes.
"""


config = types.GenerateContentConfig(
    tools=tools,
    system_instruction=system_prompt
)


def main():
    chat = client.chats.create(
        model="gemini-3.1-flash-lite",
        config=config
    )
    while True:

        user_input = input("\nYou: ")

        if user_input.strip().lower() in ["exit", "quit"]:
            break

        response = chat.send_message(
            user_input
        )

        print("\nAgent:")
        print(response.text)


if __name__ == "__main__":
    main()