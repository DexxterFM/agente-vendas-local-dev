"""Cliente OpenAI-compatível para o llama.cpp embarcado no produto."""
from __future__ import annotations
import json
import urllib.request


class LocalLlamaClient:
    def __init__(self, base_url: str, model: str = "qwen3-sales") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def chat(self, messages: list[dict], *, format_json: bool = False) -> str:
        payload = {"model": self.model, "messages": messages, "temperature": 0.45, "stream": False}
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
