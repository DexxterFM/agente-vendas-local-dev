"""Adaptador Ollama local; nenhuma chamada sai para provedores online."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from adapters.http import HttpError, get_json, post_json


@dataclass
class OllamaHealth:
    api: bool
    models: list[str]
    model_available: bool
    error: str = ""


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout: float = 90.0,
        poster: Callable[..., tuple[dict[str, str], str]] | None = None,
        getter: Callable[..., dict] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._poster = poster or post_json
        self._getter = getter or get_json

    @property
    def chat_url(self) -> str:
        return self.base_url if self.base_url.endswith("/api/chat") else f"{self.base_url}/api/chat"

    @property
    def tags_url(self) -> str:
        base = self.base_url[: -len("/api/chat")] if self.base_url.endswith("/api/chat") else self.base_url
        return base if base.endswith("/api/tags") else f"{base}/api/tags"

    def chat(self, messages: list[dict[str, str]], *, format_json: bool = True) -> str:
        payload: dict = {
            "model": self.model,
            "stream": False,
            "messages": messages,
            "options": {"temperature": 0.2, "top_p": 0.9},
        }
        if format_json:
            payload["format"] = "json"
        if self.model.lower().startswith('qwen3'):
            payload['think'] = False
        if not format_json:
            payload['options']['num_predict'] = 220
        _, body = self._poster(self.chat_url, payload, None, self.timeout)
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("O Ollama devolveu uma resposta inválida.") from exc
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError("O Ollama recusou a solicitação.")
        try:
            content = data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("O Ollama não devolveu conteúdo.") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("O Ollama devolveu uma resposta vazia.")
        return content

    def list_models(self) -> list[str]:
        data = self._getter(self.tags_url, timeout=3.0)
        models = data.get("models", []) if isinstance(data, dict) else []
        names: list[str] = []
        for item in models:
            if isinstance(item, dict):
                name = item.get("name") or item.get("model")
                if isinstance(name, str):
                    names.append(name)
        return names

    def health(self) -> OllamaHealth:
        try:
            models = self.list_models()
        except (HttpError, OSError, TimeoutError) as exc:
            return OllamaHealth(False, [], False, str(exc))
        return OllamaHealth(True, models, self.model in models)
