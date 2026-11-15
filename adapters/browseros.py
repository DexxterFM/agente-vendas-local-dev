"""Adaptador para o BrowserOS neo via MCP HTTP local."""
from __future__ import annotations

import json
from dataclasses import dataclass

from adapters.mcp import MCPClient, MCPError
from core.tools import extract_mcp_text, validate_https_url


@dataclass(frozen=True)
class BrowserRead:
    url: str
    text: str


class BrowserOSClient:
    def __init__(
        self,
        url: str,
        *,
        timeout: float = 60.0,
        max_chars: int = 12000,
        mcp: MCPClient | None = None,
    ) -> None:
        self.url = url
        self.max_chars = max_chars
        self.mcp = mcp or MCPClient(
            url,
            timeout=timeout,
            client_name="sales-agent-unified",
            client_version="0.3",
            require_session=True,
        )

    def open_and_read(self, url: str) -> BrowserRead:
        allowed, reason = validate_https_url(url)
        if not allowed:
            raise ValueError(reason)
        code = (
            f"const page = await browser.open({json.dumps(url)});\n"
            "return await page.read();"
        )
        try:
            result = self.mcp.call_tool(
                "run",
                {"code": code, "timeout": 30000, "maxChars": max(self.max_chars, 10000)},
                timeout=max(self.mcp.timeout, 60.0),
            )
        except MCPError as exc:
            raise RuntimeError(f"BrowserOS: {exc}") from exc
        text = extract_mcp_text(result, self.max_chars)
        if not text:
            text = "A página foi aberta, mas não retornou texto legível."
        return BrowserRead(url=url, text=text)

    def health(self) -> None:
        self.mcp.ping()

    def tools(self) -> list[dict]:
        """Lista as ferramentas MCP realmente expostas pelo BrowserOS."""
        try:
            return self.mcp.list_tools()
        except MCPError as exc:
            raise RuntimeError(f"BrowserOS: {exc}") from exc

    def snapshot(self, url: str) -> str:
        """Abre uma página e devolve a árvore de acessibilidade."""
        allowed, reason = validate_https_url(url)
        if not allowed:
            raise ValueError(reason)
        code = (
            f"const page = await browser.open({json.dumps(url)});\n"
            "return await page.snapshot();"
        )
        return self.run(code)

    def act(self, url: str, action: dict) -> str:
        """Executa uma ação BrowserOS (click/type/fields) e verifica o resultado.

        O servidor mantém a sessão, cookies e permissões; o aplicativo só envia
        a ação estruturada devolvida pelo modelo após um snapshot.
        """
        allowed, reason = validate_https_url(url)
        if not allowed:
            raise ValueError(reason)
        if not isinstance(action, dict) or not action:
            raise ValueError("Ação BrowserOS inválida")
        encoded = json.dumps(action, ensure_ascii=False)
        code = (
            f"const page = await browser.open({json.dumps(url)});\n"
            f"await page.act({encoded});\n"
            "return await page.read();"
        )
        return self.run(code)

    def run(self, code: str) -> str:
        """Executa uma rotina BrowserOS fornecida pelo aplicativo.

        O servidor BrowserOS continua controlando a sessão e as permissões;
        este cliente apenas transporta uma rotina curta e retorna o texto
        sanitizado. Não há credenciais ou cookies no processo local.
        """
        if not isinstance(code, str) or not code.strip() or len(code) > 8000:
            raise ValueError("Rotina BrowserOS inválida")
        try:
            result=self.mcp.call_tool("run", {"code": code, "timeout": 30000, "maxChars": max(self.max_chars,10000)}, timeout=max(self.mcp.timeout,60.0))
        except MCPError as exc:
            raise RuntimeError(f"BrowserOS: {exc}") from exc
        return extract_mcp_text(result, self.max_chars) or "O navegador não retornou conteúdo legível."

    def open_instagram_inbox(self) -> str:
        return self.run("const page = await browser.open('https://www.instagram.com/direct/inbox/'); return await page.read();")
