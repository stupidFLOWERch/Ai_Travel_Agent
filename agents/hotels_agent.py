import json

from google.genai import types


class HotelAgent:
    """
    Specialist agent responsible for hotel-related tasks.

    The Hotel Agent only knows about hotel tools.
    It does not know about flight or weather tools.
    """

    ALLOWED_TOOLS = {
        "search_hotels_tool"
    }

    def __init__(self, gemini_client, hotel_tools, call_tool):
        self.gemini_client = gemini_client
        self.call_tool = call_tool
        self.hotel_tools = [
            tool
            for tool in hotel_tools
            if tool.function_declarations[0].name in self.ALLOWED_TOOLS
        ]
        

    async def run(self, user_request: str) -> str:

        system_instruction = """
        You are a Hotel Specialist Agent.

        Your responsibility is ONLY hotel-related tasks.

        Available tool:

        1. search_hotels_tool
           Call search_hotels_tool with query, arrival, departure, adults

        Rules:

        - Handle ONLY hotel-related requests.
        - If the destination is missing and cannot be inferred,
          ask the user for the destination.
        - If important booking information is missing,
          ask the user for it when necessary.
        - Do not answer flight or weather questions.
        - Do not use tools outside your assigned domain.
        - Return a concise natural-language response.
        """

        messages = [
            types.Content(
                role="user",
                parts=[
                    types.Part(text=user_request)
                ]
            )
        ]

        MAX_ITERATIONS = 5

        for iteration in range(MAX_ITERATIONS):

            response = self.gemini_client.models.generate_content(
                model="gemini-3.1-flash-lite",
                contents=messages,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=self.hotel_tools
                )
            )

            function_calls = []

            if (
                response.candidates
                and response.candidates[0].content
                and response.candidates[0].content.parts
            ):
                for part in response.candidates[0].content.parts:

                    if part.function_call:

                        function_calls.append({
                            "name": part.function_call.name,
                            "args": dict(part.function_call.args)
                        })

            # No tool call → final response
            if not function_calls:
                return (
                    response.text
                    or "I could not find suitable accommodations."
                )

            tool_results = []

            for fc in function_calls:

                tool_name = fc["name"]

                # Safety check
                if tool_name not in self.ALLOWED_TOOLS:

                    return (
                        "I can only handle hotel-related requests."
                    )

                print(
                    f"\n🏨 Hotel Agent calling: {tool_name}"
                )

                print(
                    "Parameters:",
                    json.dumps(
                        fc["args"],
                        indent=2,
                        ensure_ascii=False
                    )
                )

                result = await self.call_tool(
                    tool_name,
                    fc["args"]
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

            # Add assistant's tool-call message
            messages.append(
                response.candidates[0].content
            )

            # Add tool results
            messages.append(
                types.Content(
                    role="user",
                    parts=tool_results
                )
            )