# llm.py — the only file that talks to the LLM provider.
# Groq exposes an OpenAI-compatible API, so we use the openai SDK with a different base_url.
# Swapping provider = change BASE_URL / MODEL_NAME in .env.local, nothing else.
from openai import OpenAI

import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=90,
            max_retries=3,
        )
    return _client


def chat(messages, tools=None, tool_choice="auto", temperature=0.0):
    # returns the assistant message object (has .content and .tool_calls)
    request = {"model": config.LLM_MODEL, "messages": messages, "temperature": temperature}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = tool_choice
    response = get_client().chat.completions.create(**request)
    return response.choices[0].message


def assistant_message_to_dict(message):
    # the SDK returns an object; the next request needs a plain dict in the history
    as_dict = {"role": "assistant", "content": message.content or ""}
    if message.tool_calls:
        as_dict["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return as_dict
