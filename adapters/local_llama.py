"""Cliente OpenAI-compatível para o llama.cpp embarcado no produto."""
from __future__ import annotations
import json
import urllib.request


class LocalLlamaClient:
    def __init__(self, base_url: str, model: str = "qwen3-sales") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict], *, format_json: bool = False) -> str:
        # Qwen3 defaults to an internal thinking channel.  The desktop agent
        # needs the concise visible reply, so use the model's no-think mode.
        prepared = [dict(message) for message in messages]
        for message in reversed(prepared):
            if message.get("role") == "user":
                content = str(message.get("content") or "")
                if not content.lstrip().startswith("/no_think"):
                    message["content"] = "/no_think\n" + content
                break
        payload = {"model": self.model, "messages": prepared, "temperature": 0.45, "stream": False}
        if format_json:
            payload["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=75) as response:
            body = json.load(response)
        return str(body["choices"][0]["message"]["content"]).strip()
