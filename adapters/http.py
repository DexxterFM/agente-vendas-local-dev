"""HTTP local mínimo, com timeouts e sem vazamento de cabeçalhos sensíveis."""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class HttpError(RuntimeError):
    pass


def _request(url: str, payload: dict | None, headers: dict[str, str] | None, timeout: float) -> tuple[dict[str, str], str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    method = "POST" if payload is not None else "GET"
    request = urllib.request.Request(url, data=data, method=method)
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return response_headers, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        raise HttpError(f"Serviço local respondeu HTTP {exc.code}.") from exc
    except urllib.error.URLError as exc:
        raise HttpError(f"Não foi possível conectar ao serviço local: {exc.reason}.") from exc
    except TimeoutError as exc:
        raise HttpError("O serviço local excedeu o tempo limite.") from exc


def post_json(
    url: str,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
) -> tuple[dict[str, str], str]:
    return _request(url, payload, headers, timeout)


def get_json(url: str, timeout: float = 10.0) -> dict:
    _, body = _request(url, None, {"Accept": "application/json"}, timeout)
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise HttpError("Resposta JSON inválida do serviço local.") from exc
