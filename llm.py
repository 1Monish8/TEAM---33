# llm.py — the only file that talks to the LLM provider.
# Groq exposes an OpenAI-compatible API, so we use the openai SDK with a different base_url.
# Swapping provider = change BASE_URL / MODEL_NAME in .env.local, nothing else.
import json
import os
import re
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

# Our Groq key allows 8,000 tokens per minute. One investigation resends its whole history on every
# step, so without pacing it hits that limit by the third or fourth step. We keep our own record of
# the tokens actually used in the last 60 s and wait BEFORE sending if the next request would cross it.
TOKENS_PER_MINUTE = int(os.environ.get("LLM_TOKENS_PER_MINUTE", "8000"))
TOKEN_BUDGET = int(TOKENS_PER_MINUTE * 0.9)  # headroom for our estimate being a little off
MAX_COMPLETION_TOKENS = 2048                 # bounds the reply (reasoning + answer) so a request's size is predictable
_recent_usage = []                           # [(time.time(), tokens used)] within the last 60 s


def get_client():
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            timeout=90,
            max_retries=0,  # retries are handled below, where we can wait the right amount of time
        )
    return _client


def _estimate_tokens(request):
    # rough but safe: ~4 characters per token for the prompt, plus the most the reply may use
    return len(json.dumps(request["messages"])) // 4 + len(json.dumps(request.get("tools", []))) // 4 + MAX_COMPLETION_TOKENS


def _wait_for_token_budget(needed_tokens):
    while True:
        now = time.time()
        _recent_usage[:] = [(stamp, used) for stamp, used in _recent_usage if now - stamp < 60]
        used_last_minute = sum(used for _, used in _recent_usage)
        if not _recent_usage or used_last_minute + needed_tokens <= TOKEN_BUDGET:
            return
        wait_seconds = 60 - (now - _recent_usage[0][0]) + 0.5  # until the oldest request leaves the window
        print("  pacing: %d tokens used in the last minute, waiting %.0fs" % (used_last_minute, wait_seconds),
              file=sys.stderr, flush=True)
        time.sleep(wait_seconds)


def _retry_after_seconds(error, default_seconds):
    # Groq says how long to wait, e.g. "Please try again in 7.5s" or "in 1m2.3s"
    match = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
    if match:
        return int(match.group(1) or 0) * 60 + float(match.group(2)) + 1
    return default_seconds


def chat(messages, tools=None, tool_choice="auto", temperature=0.0):
    # returns the assistant message object (has .content and .tool_calls)
    request = {"model": config.LLM_MODEL, "messages": messages, "temperature": temperature,
               "max_completion_tokens": MAX_COMPLETION_TOKENS}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = tool_choice
    for attempt, wait_seconds in enumerate(BACKOFF_SECONDS + [None], start=1):
        _wait_for_token_budget(_estimate_tokens(request))
        try:
            response = get_client().chat.completions.create(**request)
            used = getattr(response.usage, "total_tokens", None) or _estimate_tokens(request)
            _recent_usage.append((time.time(), used))
            return response.choices[0].message
        except TRANSIENT_ERRORS as error:
            if isinstance(error, openai.RateLimitError):
                _recent_usage.append((time.time(), TOKEN_BUDGET))  # treat the minute as full
            if wait_seconds is None:
                raise
            wait_seconds = _retry_after_seconds(error, wait_seconds)
            print("  LLM call failed (%s: %s), retry %d in %.0fs"
                  % (type(error).__name__, str(error)[:160], attempt, wait_seconds), file=sys.stderr, flush=True)
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
