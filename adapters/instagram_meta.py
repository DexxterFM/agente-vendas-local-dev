"""Verificação de conexão com Instagram/Meta Graph API.

Somente consulta identidade da conta. Não envia mensagens nem publica conteúdo.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


class InstagramMetaError(RuntimeError):
    pass


def check_connection(timeout: float = 10.0, memory=None) -> dict:
    if memory is not None:
        from core.meta_credentials import values
        account_id, token, version = values(memory)
    else:
        token = os.getenv("INSTAGRAM_ACCESS_TOKEN", "").strip() or os.getenv("PAGE_ACCESS_TOKEN", "").strip()
        account_id = os.getenv("IG_BUSINESS_ACCOUNT_ID", "").strip() or os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "").strip()
        version = os.getenv("META_GRAPH_VERSION", "v23.0").strip()
    metadata={"credential_present":bool(token),"account_configured":bool(account_id),"account_suffix":str(account_id)[-4:] if account_id else "","credential_source":"vault/local memory" if memory is not None else "environment"}
    if not token:
        return {"status": "attention", "detail": "Credencial Meta ausente no cofre/memória local.","meta":metadata}
    if not account_id:
        return {"status": "attention", "detail": "ID da conta Instagram ausente no cofre/memória local.","meta":metadata}
    mode = (memory.get_setting("meta.login_mode", "") if memory is not None else "") or os.getenv("META_LOGIN_MODE", "facebook")
    mode = mode.strip().lower()
    host = "graph.instagram.com" if mode == "instagram" else "graph.facebook.com"
    fields = "user_id,username,account_type,media_count" if mode == "instagram" else "id,username,name"
    target = "me" if mode == "instagram" else urllib.parse.quote(account_id, safe='')
    query = urllib.parse.urlencode({"fields": fields, "access_token": token})
    url = f"https://{host}/{version}/{target}?{query}"
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail=''
        try: detail=json.loads(exc.read().decode('utf-8')).get('error',{}).get('message','')
        except Exception: pass
        return {"status": "unavailable", "detail": f"Meta recusou a conexão (HTTP {exc.code}): {detail[:220]}","meta":metadata}
    except (urllib.error.URLError, TimeoutError) as exc:
        return {"status": "unavailable", "detail": f"Não foi possível conectar à Meta: {str(exc)[:120]}","meta":metadata}
    except (json.JSONDecodeError, OSError):
        return {"status": "unavailable", "detail": "Resposta inválida da Meta Graph API.","meta":metadata}
    returned = payload.get("user_id") if mode == "instagram" else payload.get("id", account_id)
    username = payload.get("username") or payload.get("name") or account_id
    if mode == "instagram" and str(returned) != str(account_id):
        return {"status": "attention", "detail": "A conta Meta autorizada não corresponde ao ID configurado.","meta":metadata}
    return {"status": "connected", "detail": f"Conta Instagram conectada: @{username}.", "meta": {"id": returned, "username": username}}
