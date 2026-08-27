import json
from google.genai import types


class FlightAgent:
    """
    Specialist agent responsible for flight-related tasks.

    The Flight Agent only knows about flight tools.
    """

    ALLOWED_TOOLS = {
        "search_flights_tool",
        "search_multi_city_tool",
        "cheapest_date_range_tool",
        "analyze_price_insights_tool",
        "search_airport_tool"
    }

    def __init__(self, gemini_client, flight_tools, call_tool):
        self.gemini_client = gemini_client
        self.call_tool = call_tool

        self.flight_tools = [
            tool
            for tool in flight_tools
            if tool.function_declarations[0].name in self.ALLOWED_TOOLS
        ]

    # ============================================================
    # Get specific tool
    # ============================================================

    def get_tool(self, tool_name: str):
        for tool in self.flight_tools:
            if tool.function_declarations[0].name == tool_name:
                return tool

        return None

    # ============================================================
    # Normal flight tools
    # ============================================================

    async def run(
        self,
        user_request: str,
        allowed_tool_names=None
    ) -> str:
        """
        Handle a flight-related user request.
        """
        if allowed_tool_names is not None:
            allowed_tool_names = set(allowed_tool_names)

        # Multi-city: 强制只允许 search_multi_city_tool
        if allowed_tool_names == {"search_multi_city_tool"}:
            return await self.run_multi_city(user_request)

        # ========================================================
        # Normal flight request
        # ========================================================

        return await self.run_normal(user_request)

    # ============================================================
    # MULTI-CITY HANDLER
    # ============================================================

    async def run_multi_city(self, user_request: str) -> str:

        multi_city_tool = self.get_tool(
            "search_multi_city_tool"
        )

        if multi_city_tool is None:
            return "Multi-city flight search tool is not available."

        system_instruction = """
You are a Flight Specialist Agent handling a MULTI-CITY flight request.

IMPORTANT:

You MUST use ONLY:

search_multi_city_tool

You MUST NOT call:

- search_flights_tool
- search_airport_tool
- cheapest_date_range_tool
- analyze_price_insights_tool

The user request contains multiple flight segments.

You must convert the request into the required structure:

{
    "segments": [
        {
            "departure_id": "KUL",
            "arrival_id": "BKI",
            "outbound_date": "2026-08-29"
        },
        {
            "departure_id": "BKI",
            "arrival_id": "SBW",
            "outbound_date": "2026-09-04"
        }
    ]
}

Important:

- Do NOT search airports separately.
- If the user provides airport codes such as KUL, BKI, SBW, use them directly.
- Do NOT call search_flights_tool for individual segments.
- Do NOT split the multi-city request into separate flight searches.
- Make exactly ONE call to search_multi_city_tool.
- After receiving the tool result, provide a concise natural-language response.

"""

        messages = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=user_request)
                ]
            )
        ]

        # ========================================================
        # IMPORTANT:
        # Only expose search_multi_city_tool to Gemini
        # ========================================================

        response = self.gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,

                # ONLY ONE TOOL
                tools=[multi_city_tool]
            )
        )

        MAX_ITERATIONS = 3

        for iteration in range(MAX_ITERATIONS):

            function_calls = []

            if (
                response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts
            ):

                for part in response.candidates[0].content.parts:

                    if part.function_call:

                        function_calls.append(
                            {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args)
                            }
                        )

            # ====================================================
            # No tool call
            # ====================================================

            if not function_calls:
                return (
                    response.text
                    or "I could not find suitable multi-city flights."
                )

            # ====================================================
            # Safety check
            # ====================================================

            for fc in function_calls:

                if fc["name"] != "search_multi_city_tool":

                    return (
                        "I could not process the multi-city "
                        "flight request correctly."
                    )

            # ====================================================
            # Execute ONLY multi-city tool
            # ====================================================

            tool_results = []

            for fc in function_calls:

                print(
                    f"\n✈️ Flight Agent calling: {fc['name']}"
                )

                print(
                    "Parameters: "
                    f"{json.dumps(fc['args'], indent=2, ensure_ascii=False)}"
                )

                result = await self.call_tool(
                    fc["name"],
                    fc["args"]
                )

                tool_results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc["name"],
                            response={
                                "result": result
                            }
                        )
                    )
                )

            # ====================================================
            # Send tool result back to Gemini
            # ====================================================

            messages.append(
                response.candidates[0].content
            )

            messages.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )

            # ====================================================
            # IMPORTANT:
            # Still expose ONLY multi-city tool
            # ====================================================

            response = self.gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,

                    # STILL ONLY ONE TOOL
                    tools=[multi_city_tool]
                )
            )

        return "I could not complete the multi-city flight search."

    # ============================================================
    # NORMAL FLIGHT HANDLER
    # ============================================================

    async def run_normal(self, user_request: str) -> str:

        system_instruction = """
You are a Flight Specialist Agent.

Your responsibility is ONLY flight-related tasks.

Available tools:

1. search_flights_tool
   Search one-way and round-trip flights.

2. cheapest_date_range_tool
   Find the cheapest flights within a date range.

3. analyze_price_insights_tool
   Analyze whether a flight price is good.

4. search_airport_tool
   Find airport IATA codes.

IMPORTANT:

- For normal one-way or round-trip flight searches,
  use search_flights_tool.

- If the user asks for the cheapest flight within
  a date range, use cheapest_date_range_tool.

- If the user asks whether a flight price is good,
  use analyze_price_insights_tool.

- If the user provides city names instead of IATA codes,
  use search_airport_tool when necessary.

- Multi-city requests are handled separately.
- Do NOT use search_multi_city_tool here.

- Assume current year is 2026 if not provided.

Return a concise natural-language response.
"""

        # Exclude multi-city from normal tools
        normal_tools = [
            tool
            for tool in self.flight_tools
            if tool.function_declarations[0].name
            != "search_multi_city_tool"
        ]

        messages = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=user_request)
                ]
            )
        ]

        response = self.gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=normal_tools
            )
        )

        MAX_ITERATIONS = 5

        for iteration in range(MAX_ITERATIONS):

            function_calls = []

            if (
                response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts
            ):

                for part in response.candidates[0].content.parts:

                    if part.function_call:

                        function_calls.append(
                            {
                                "name": part.function_call.name,
                                "args": dict(part.function_call.args)
                            }
                        )

            # ====================================================
            # No tool call -> final answer
            # ====================================================

            if not function_calls:
                return (
                    response.text
                    or "I could not find suitable flights."
                )

            # ====================================================
            # Execute tools
            # ====================================================

            tool_results = []

            for fc in function_calls:

                print(
                    f"\n✈️ Flight Agent calling: {fc['name']}"
                )

                print(
                    "Parameters: "
                    f"{json.dumps(fc['args'], indent=2, ensure_ascii=False)}"
                )

                result = await self.call_tool(
                    fc["name"],
                    fc["args"]
                )

                tool_results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=fc["name"],
                            response={
                                "result": result
                            }
                        )
                    )
                )

            messages.append(
                response.candidates[0].content
            )

            messages.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )

            response = self.gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=normal_tools
                )
            )

        return "I could not complete the flight search."