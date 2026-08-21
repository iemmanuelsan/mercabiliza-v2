"""Cliente HTTP compartilhado.

O código original criava uma conexão TCP+TLS nova a cada ``requests.get``.
Numa análise em lote de 100 CNPJs isso significava 300 handshakes TLS. Uma
``Session`` com pool de conexões e retry exponencial resolve os dois
problemas de uma vez.
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..config import settings

logger = logging.getLogger(__name__)

_STATUS_PARA_RETENTAR = (429, 500, 502, 503, 504)


def criar_sessao() -> requests.Session:
    sessao = requests.Session()
    politica = Retry(
        total=settings.http.total_retries,
        backoff_factor=settings.http.backoff_factor,
        status_forcelist=_STATUS_PARA_RETENTAR,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adaptador = HTTPAdapter(
        max_retries=politica,
        pool_connections=settings.http.max_workers_lote * 3,
        pool_maxsize=settings.http.max_workers_lote * 3,
    )
    sessao.mount("https://", adaptador)
    sessao.mount("http://", adaptador)
    sessao.headers.update({
        "User-Agent": settings.http.user_agent,
        "Accept": "application/json",
    })
    return sessao


def get_json(sessao: requests.Session, url: str, *, rotulo: str) -> dict[str, Any] | None:
    """GET que devolve ``None`` em falha — mas **registra** o motivo.

    [CORRIGIDO] O padrão anterior era ``except Exception: pass``, repetido 8
    vezes. Falhas de rede, JSON malformado e rate limit ficavam todos
    invisíveis: a tela mostrava "CNPJ não localizado" mesmo quando o problema
    era a API fora do ar.
    """
    try:
        resposta = sessao.get(url, timeout=settings.http.timeout)
    except requests.Timeout:
        logger.warning("[%s] timeout após %.1fs em %s", rotulo, settings.http.timeout, url)
        return None
    except requests.RequestException as exc:
        logger.warning("[%s] falha de rede: %s", rotulo, exc)
        return None

    if resposta.status_code == 429:
        logger.warning("[%s] rate limit (429). Reduza a concorrência do lote.", rotulo)
        return None
    if resposta.status_code != 200:
        logger.info("[%s] HTTP %s para %s", rotulo, resposta.status_code, url)
        return None

    try:
        dados = resposta.json()
    except ValueError:
        logger.warning("[%s] resposta não é JSON válido.", rotulo)
        return None

    return dados if isinstance(dados, dict) else {"_lista": dados}
