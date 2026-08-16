import json
from dataclasses import dataclass, field


@dataclass
class ChatStreamState:
    content_parts: list[str] = field(default_factory=list)
    error: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


def consume_sse_line(line: str, state: ChatStreamState) -> None:
    data = line.strip()
    if not data.startswith("data:"):
        return
    payload = data[5:].strip()
    if not payload:
        return
    if payload == "[DONE]":
        return
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return
    if "error" in obj:
        err = obj["error"]
        state.error = err.get("message") if isinstance(err, dict) else str(err)
    usage = obj.get("usage")
    if isinstance(usage, dict):
        state.prompt_tokens = usage.get("prompt_tokens")
        state.completion_tokens = usage.get("completion_tokens")
    for choice in obj.get("choices") or []:
        if not isinstance(choice, dict):
            continue
        delta = choice.get("delta") or {}
        content = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(content, str):
            state.content_parts.append(content)
        message = choice.get("message") or {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            state.content_parts.append(content)


def assistant_content(state: ChatStreamState) -> str:
    if state.error:
        return f"[错误] {state.error}"
    return "".join(state.content_parts)
