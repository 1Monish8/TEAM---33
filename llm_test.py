import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["API_KEY"],
    base_url=os.environ["BASE_URL"],
)

tool_descriptions = [{
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Returns the current time as a string.",
        "parameters": {"type": "object", "properties": {}},
    },
}]

first_response = client.chat.completions.create(
    model=os.environ["MODEL_NAME"],
    messages=[{"role": "user", "content": "What time is it? Use the tool."}],
    tools=tool_descriptions,
)

requested_calls = first_response.choices[0].message.tool_calls
print("tool calls:", requested_calls)

if requested_calls:
    print("TOOL CALLING WORKS")
else:
    print("NO TOOL CALL -- model replied with text instead")
