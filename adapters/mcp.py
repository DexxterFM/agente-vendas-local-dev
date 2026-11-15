"""Cliente MCP Streamable HTTP mínimo, com parser SSE testável."""
from __future__ import annotations

import json
import threading
from typing import Callable

from adapters.http import post_json

Poster = Callable[..., tuple[dict[str, str], str]]
_PROTOCOL_VERSION = "2025-11-25"
_CLIENT_INFO = {"name": "sales-agent-unified", "version": "0.3"}


class MCPError(RuntimeError):
    pass


def parse_mcp_body(body: str) -> list[dict]:
    """Aceita JSON direto ou um ou mais eventos SSE com linhas data:."""
    text = (body or "").strip()
    if not text:
        return []
    if text.startswith("{"):
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPError("Resposta MCP inválida.") from exc
        return [value] if isinstance(value, dict) else []
    events: list[dict] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        payload = "\n".join(data_lines).strip()
        data_lines = []
        if not payload or payload == "[DONE]":
            return
        try:
            value = json.loads(payload)
        except json.JSONDecodeError:
            return
        if isinstance(value, dict):
            events.append(value)

    for line in text.splitlines():
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif not line.strip():
            flush()
    flush()
    return events


def select_response(messages: list[dict], request_id: int | str) -> dict:
    for message in reversed(messages):
        if "result" in message or "error" in message:
            if str(message.get("id")) == str(request_id):
                return message
    for message in reversed(messages):
        if "result" in message or "error" in message:
            return message
    raise MCPError("O servidor MCP não devolveu uma resposta JSON-RPC.")


class MCPClient:
    """Sessão MCP simples; o servidor continua dono do ciclo de vida da sessão.

    O BrowserOS neo usa o protocolo MCP 2025-11-25, que exige metadados
    `_meta` por requisição e cabeçalhos `Mcp-Method`/`Mcp-Name`. Esses campos
    são enviados sempre; servidores mais antigos simplesmente os ignoram.
    """

    def __init__(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        client_name: str = "sales-agent-unified",
        client_version: str = "0.3",
        protocol_version: str = _PROTOCOL_VERSION,
        require_session: bool = False,
        poster: Poster | None = None,
    ) -> None:
        self.url = url
        self.timeout = timeout
        self.client_name = client_name
        self.client_version = client_version
        self.protocol_version = protocol_version
        self.require_session = require_session
        self._poster = poster or post_json
        self._lock = threading.RLock()
        self._sequence = 0
        self.session_id: str | None = None
        self._initialized = False

    def _next_id(self) -> int:
        with self._lock:
            self._sequence += 1
            return self._sequence

    def _meta(self) -> dict:
        return {
            "io.modelcontextprotocol/protocolVersion": self.protocol_version,
            "io.modelcontextprotocol/clientInfo": {
                "name": self.client_name,
                "version": self.client_version,
            },
            "io.modelcontextprotocol/clientCapabilities": {},
        }

    def _headers(self, method: str, tool_name: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Mcp-Method": method,
        }
        if tool_name:
            headers["Mcp-Name"] = tool_name
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    def _send(self, method: str, params: dict | None = None, tool_name: str | None = None) -> dict:
        request_id = self._next_id()
        payload: dict = {"jsonrpc": "2.0", "id": request_id, "method": method}
        body = dict(params or {})
        body["_meta"] = self._meta()
        payload["params"] = body
        headers, raw = self._poster(
            self.url,
            payload,
            self._headers(method, tool_name),
            self.timeout,
        )
        if not self.session_id:
            self.session_id = headers.get("mcp-session-id")
        messages = parse_mcp_body(raw)
        response = select_response(messages, request_id)
        if "error" in response:
            error = response["error"] if isinstance(response["error"], dict) else {}
            raise MCPError(str(error.get("message") or "Erro MCP."))
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPError("Resposta MCP sem resultado.")
        return result

    def initialize(self) -> dict:
        with self._lock:
            if self._initialized:
                return {}
            result = self._send(
                "initialize",
                {
                    "protocolVersion": self.protocol_version,
                    "capabilities": {},
                    "clientInfo": {"name": self.client_name, "version": self.client_version},
                },
            )
            negotiated = result.get("protocolVersion")
            if isinstance(negotiated, str) and negotiated.strip():
                self.protocol_version = negotiated.strip()
            if self.require_session and not self.session_id:
                raise MCPError("O servidor MCP não devolveu uma sessão.")
            try:
                notification = {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {"_meta": self._meta()},
                }
                self._poster(
                    self.url,
                    notification,
                    self._headers("notifications/initialized"),
                    self.timeout,
                )
            except Exception:
                # A notificação é opcional em vários servidores; a sessão já foi validada.
                pass
            self._initialized = True
            return result

    def call_tool(self, name: str, arguments: dict, timeout: float | None = None) -> dict:
        self.initialize()
        old_timeout = self.timeout
        if timeout is not None:
            self.timeout = timeout
        try:
            result = self._send(
                "tools/call",
                {"name": name, "arguments": arguments},
                tool_name=name,
            )
        finally:
            self.timeout = old_timeout
        if result.get("isError"):
            raise MCPError(_tool_result_text(result) or "A ferramenta MCP retornou erro.")
        return result

    def list_tools(self) -> list[dict]:
        self.initialize()
        result = self._send("tools/list")
        tools = result.get("tools", [])
        return tools if isinstance(tools, list) else []

    def ping(self) -> bool:
        self.initialize()
        return True


def _tool_result_text(result: dict) -> str:
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict) and item.get("type") == "text":
            value = item.get("text")
            if isinstance(value, str):
                parts.append(value)
    return "\n".join(parts)[:1200]
