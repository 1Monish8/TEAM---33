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
_fallback_in_use = False
last_model_used = None  # which model answered the most recent call (written into every transcript line)

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
_recent_completions = []                     # completion sizes actually observed, to reserve realistically
last_usage = None                            # {"prompt_tokens", "completion_tokens", "total_tokens"} of the last call


class ToolCallRejected(Exception):
    """The provider refused the model's tool call because it did not match the tool's schema (Groq: HTTP 400
    'Tool call validation failed'). The agent loop turns this into feedback for the model instead of crashing."""


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


def _is_daily_cap(error):
    # Groq names the exhausted bucket: "tokens per day (TPD)" / "requests per day (RPD)".
    # Waiting cannot fix a daily cap; only a different model or key can.
    text = str(error).lower()
    return "per day" in text or "(tpd)" in text or "(rpd)" in text


def _switch_to_fallback():
    # Called once, when the primary is rate limited beyond its retries. Prints loudly, because the
    # team form must declare every model used and a judge may ask which one answered.
    global _client, _fallback_in_use
    if _fallback_in_use or not config.LLM_API_KEY_FALLBACK:
        return False
    if config.LLM_MODEL_FALLBACK == config.LLM_MODEL and config.LLM_API_KEY_FALLBACK == config.LLM_API_KEY:
        return False  # the "fallback" would be the same quota: switching would not help
    print("  PRIMARY MODEL RATE-LIMITED -> switching to fallback model %s" % config.LLM_MODEL_FALLBACK,
          file=sys.stderr, flush=True)
    _client = OpenAI(api_key=config.LLM_API_KEY_FALLBACK, base_url=config.LLM_BASE_URL_FALLBACK,
                     timeout=90, max_retries=0)
    config.LLM_MODEL = config.LLM_MODEL_FALLBACK
    _recent_usage.clear()  # the fallback has its own per-minute budget
    _fallback_in_use = True
    return True


def _estimate_tokens(request):
    # ~4 characters per token for the prompt, plus a reply reservation based on the replies we have actually seen
    # (reserving the full 2,048-token cap every time made almost every step wait a whole minute)
    recent = _recent_completions[-8:]
    reply_reserve = min(MAX_COMPLETION_TOKENS, max(600, int(1.5 * max(recent)))) if recent else 1200
    return len(json.dumps(request["messages"])) // 4 + len(json.dumps(request.get("tools", []))) // 4 + reply_reserve


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
    global last_model_used
    request = {"messages": messages, "temperature": temperature, "max_completion_tokens": MAX_COMPLETION_TOKENS}
    if tools:
        request["tools"] = tools
        request["tool_choice"] = tool_choice
    for attempt, wait_seconds in enumerate(BACKOFF_SECONDS + [None], start=1):
        request["model"] = config.LLM_MODEL  # re-read every attempt: the fallback may have switched it
        _wait_for_token_budget(_estimate_tokens(request))
        try:
            response = get_client().chat.completions.create(**request)
            usage = getattr(response, "usage", None)
            used = getattr(usage, "total_tokens", None) or _estimate_tokens(request)
            _recent_usage.append((time.time(), used))
            if getattr(usage, "completion_tokens", None):
                _recent_completions.append(usage.completion_tokens)
            global last_usage
            last_usage = {"prompt_tokens": getattr(usage, "prompt_tokens", None),
                          "completion_tokens": getattr(usage, "completion_tokens", None), "total_tokens": used}
            last_model_used = getattr(response, "model", None) or request["model"]
            return response.choices[0].message
        except openai.BadRequestError as error:
            text = str(error)
            if "tool call validation failed" in text.lower() or "failed_generation" in text:
                raise ToolCallRejected(text[:1500]) from error
            raise
        except TRANSIENT_ERRORS as error:
            if isinstance(error, openai.RateLimitError):
                _recent_usage.append((time.time(), TOKEN_BUDGET))  # treat the minute as full
                # a daily cap, or a limit that survived two waits, will not clear by waiting: change model
                if (_is_daily_cap(error) or attempt >= 2) and _switch_to_fallback():
                    continue
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
