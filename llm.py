# llm.py — the only file that talks to the LLM provider.
# Groq exposes an OpenAI-compatible API, so we use the openai SDK with a different base_url.
# Swapping provider = change BASE_URL / MODEL_NAME in .env.local, nothing else.
import sys
import time

import openai
from openai import OpenAI

import config

_client = None

# Venue wifi drops for longer than the SDK's own quick retries cover. These errors are transient,
# so wait and try again instead of losing the whole investigation. Anything else (bad request,
# bad key) is a real bug and is raised immediately.
TRANSIENT_ERRORS = (openai.APIConnectionError, openai.APITimeoutError, openai.RateLimitError, openai.InternalServerError)
BACKOFF_SECONDS = [5, 15, 30, 60, 90]


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
    for attempt, wait_seconds in enumerate(BACKOFF_SECONDS + [None], start=1):
        try:
            response = get_client().chat.completions.create(**request)
            return response.choices[0].message
        except TRANSIENT_ERRORS as error:
            if wait_seconds is None:
                raise
            print("  LLM call failed (%s), retry %d in %ds" % (type(error).__name__, attempt, wait_seconds),
                  file=sys.stderr, flush=True)
            time.sleep(wait_seconds)


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
