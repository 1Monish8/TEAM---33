# smoke_test_llm.py — Checkpoint 0: prove the key, the SDK and tool-call parsing all work.
# One tool, get_time, that returns a fixed string. Pass = the model calls it and uses the result.
import json

import llm

GET_TIME_TOOL = {
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "Returns the current time as a string.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def get_time():
    return "12:34:56 (fixed value from the smoke test)"


def main():
    messages = [{"role": "user", "content": "What time is it? Use the tool, then answer in one sentence."}]
    first_reply = llm.chat(messages, tools=[GET_TIME_TOOL])
    tool_calls = first_reply.tool_calls or []
    if not tool_calls:
        print("FAIL: the model did not call get_time. It said:", first_reply.content)
        return
    print("model called:", tool_calls[0].function.name, tool_calls[0].function.arguments)
    messages.append(llm.assistant_message_to_dict(first_reply))
    messages.append({"role": "tool", "tool_call_id": tool_calls[0].id, "content": json.dumps(get_time())})
    second_reply = llm.chat(messages, tools=[GET_TIME_TOOL])
    print("model answered:", second_reply.content)
    print("PASS" if "12:34" in (second_reply.content or "") else "FAIL: answer did not use the tool result")


if __name__ == "__main__":
    main()
