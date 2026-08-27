import json
from google.genai import types


class FlightAgent:
    """
    Specialist agent responsible for flight-related tasks.

    The Flight Agent only knows about flight tools.

    Dispatcher controls which tools are available for each task.
    Gemini decides which of the allowed tools to call.
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

        # Only keep tools that belong to Flight Agent
        self.flight_tools = [
            tool
            for tool in flight_tools
            if tool.function_declarations[0].name
            in self.ALLOWED_TOOLS
        ]

    # ============================================================
    # Get specific tool
    # ============================================================

    def get_tool(self, tool_name: str):

        for tool in self.flight_tools:

            if (
                tool.function_declarations[0].name
                == tool_name
            ):
                return tool

        return None

    # ============================================================
    # Run Flight Agent
    # ============================================================

    async def run(
        self,
        user_request: str,
        allowed_tool_names=None
    ) -> str:
        """
        Handle a flight-related request.

        allowed_tool_names is provided by the Dispatcher.

        Example:

            [
                "search_multi_city_tool",
                "search_airport_tool"
            ]

        Gemini can ONLY access these tools.
        """

        # ========================================================
        # Determine allowed tools
        # ========================================================

        if allowed_tool_names is not None:

            allowed_tool_names = set(
                allowed_tool_names
            )

            # Safety:
            # Dispatcher should never give FlightAgent
            # tools outside FlightAgent's own allowed tools.

            allowed_tool_names = (
                allowed_tool_names
                & self.ALLOWED_TOOLS
            )

        else:

            # If Dispatcher does not specify permissions,
            # allow all Flight Agent tools.

            allowed_tool_names = set(
                self.ALLOWED_TOOLS
            )

        # ========================================================
        # Filter actual Gemini tools
        # ========================================================

        available_tools = [
            tool
            for tool in self.flight_tools
            if tool.function_declarations[0].name
            in allowed_tool_names
        ]

        if not available_tools:

            return (
                "No suitable flight tools are available "
                "for this task."
            )

        # ========================================================
        # System Instruction
        # ========================================================

        system_instruction = """
        You are a Flight Specialist Agent.

        Your responsibility is ONLY flight-related tasks.

        The Dispatcher has already determined which tools
        you are allowed to use.

        You MUST ONLY use the tools provided to you.

        Available flight tools may include:

        1. search_flights_tool
        Search one-way and round-trip flights.

        2. search_multi_city_tool
        Search a complete multi-city itinerary.

        3. cheapest_date_range_tool
        Find the cheapest flights within a date range.

        4. analyze_price_insights_tool
        Analyze whether a flight price is good.

        5. search_airport_tool
        Find airport IATA codes when the user provides
        city names instead of airport codes.

        IMPORTANT:

        - Decide which available tool is appropriate for the request.
        - You may call multiple available tools if necessary.
        - If airport codes are already provided, do not unnecessarily
        call search_airport_tool.
        - For multi-city requests, use search_multi_city_tool
        instead of splitting the itinerary into separate
        search_flights_tool calls.
        - Do NOT call any tool that is not provided to you.
        - Use the entire user request to determine the correct
        tool and parameters.
        - Assume current year is 2026 if a year is not provided.
        - After receiving tool results, provide a concise
        natural-language response.
        """

        # ========================================================
        # Initial message
        # ========================================================

        messages = [
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=user_request
                    )
                ]
            )
        ]

        # ========================================================
        # First Gemini call
        # ========================================================

        response = self.gemini_client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=messages,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=available_tools
            )
        )

        # ========================================================
        # Tool Calling Loop
        # ========================================================

        MAX_ITERATIONS = 5

        for iteration in range(MAX_ITERATIONS):

            function_calls = []

            # ----------------------------------------------------
            # Extract function calls
            # ----------------------------------------------------

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
                                "args": dict(
                                    part.function_call.args
                                )
                            }
                        )

            # ----------------------------------------------------
            # No tool call
            # ----------------------------------------------------

            if not function_calls:

                return (
                    response.text
                    or "I could not find suitable flights."
                )

            # ----------------------------------------------------
            # Safety check
            # ----------------------------------------------------

            for fc in function_calls:

                tool_name = fc["name"]

                if tool_name not in allowed_tool_names:

                    print(
                        f"\n⚠️ Unauthorized tool call blocked: "
                        f"{tool_name}"
                    )

                    return (
                        "I could not process the flight "
                        "request because an unauthorized "
                        "tool was requested."
                    )

            # ----------------------------------------------------
            # Execute tools
            # ----------------------------------------------------

            tool_results = []

            for fc in function_calls:

                tool_name = fc["name"]
                tool_args = fc["args"]

                print(
                    f"\n✈️ Flight Agent calling: "
                    f"{tool_name}"
                )

                print(
                    "Parameters: "
                    f"{json.dumps(
                        tool_args,
                        indent=2,
                        ensure_ascii=False
                    )}"
                )

                result = await self.call_tool(
                    tool_name,
                    tool_args
                )

                tool_results.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={
                                "result": result
                            }
                        )
                    )
                )

            # ----------------------------------------------------
            # Add Gemini response
            # ----------------------------------------------------

            messages.append(
                response.candidates[0].content
            )

            # ----------------------------------------------------
            # Add tool results
            # ----------------------------------------------------

            messages.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )

            # ----------------------------------------------------
            # Ask Gemini to continue
            # ----------------------------------------------------

            response = self.gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=available_tools
                )
            )

        # ========================================================
        # Max iterations reached
        # ========================================================

        return (
            "I could not complete the flight search."
        )