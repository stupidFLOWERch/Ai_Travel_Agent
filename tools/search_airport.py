def main():

    user_input = input("You: ")

    # First request
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite",
        contents=user_input,
        config=config
    )

    # Tool calling loop
    while response.function_calls:

        print("\nAgent is using a tool...")

        tool_results = []

        for function_call in response.function_calls:

            function_name = function_call.name
            function_args = function_call.args

            print(
                f"Calling tool: {function_name}"
            )

            print(
                f"Arguments: {function_args}"
            )

            # Find the corresponding Python function
            tool_function = available_tools.get(function_name)

            if tool_function is None:
                raise ValueError(
                    f"Unknown tool: {function_name}"
                )

            # Execute the Python function
            result = tool_function(
                **function_args
            )

            print(
                f"Tool result: {result}"
            )

            # Store tool result
            tool_results.append(
                types.Part.from_function_response(
                    name=function_name,
                    response={
                        "result": result
                    }
                )
            )

        # Send tool results back to Gemini
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[
                response.candidates[0].content,
                types.Content(
                    role="user",
                    parts=tool_results
                )
            ],
            config=config
        )

    # Final response
    print("\nAgent:")
    print(response.text)


if __name__ == "__main__":
    main()
