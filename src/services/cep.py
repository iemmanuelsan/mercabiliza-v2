"""Consulta de endereço por CEP, com dois provedores em cascata.

ViaCEP é o provedor primário (mais completo, inclui código IBGE). A BrasilAPI
entra como fallback quando o ViaCEP está fora ou devolve ``erro: true``.
Nenhuma das duas exige chave de API.
"""

from __future__ import annotations

import logging
import re

from ..core.models import Endereco
from .http import criar_sessao, get_json

logger = logging.getLogger(__name__)

VIACEP = "https://viacep.com.br/ws/{cep}/json/"
BRASILAPI_CEP = "https://brasilapi.com.br/api/cep/v1/{cep}"

_NAO_DIGITO = re.compile(r"\D")


class CEPInvalidoError(ValueError):
    """CEP fora do formato de 8 dígitos."""


def normalizar(bruto: object) -> str:
    return _NAO_DIGITO.sub("", str(bruto or ""))


def validar(bruto: object) -> str:
    cep = normalizar(bruto)
    if len(cep) != 8:
        raise CEPInvalidoError(
            f"CEP deve ter 8 dígitos (recebidos {len(cep)})."
        )
    if len(set(cep)) == 1:
        raise CEPInvalidoError("Sequência repetida não é um CEP válido.")
    return cep


def formatar(cep: str) -> str:
    c = normalizar(cep)
    return f"{c[:5]}-{c[5:]}" if len(c) == 8 else str(cep)


def _de_viacep(d: dict) -> Endereco | None:
    if d.get("erro") in (True, "true"):
        return None
    return Endereco(
        logradouro=str(d.get("logradouro") or "").strip(),
        bairro=str(d.get("bairro") or "").strip(),
        municipio=str(d.get("localidade") or "").strip(),
        uf=str(d.get("uf") or "").strip().upper(),
        cep=normalizar(d.get("cep")),
        cod_ibge=str(d.get("ibge") or "N/A"),
        complemento=str(d.get("complemento") or "").strip(),
    )


def _de_brasilapi(d: dict) -> Endereco | None:
    if not d.get("city"):
        return None
    return Endereco(
        logradouro=str(d.get("street") or "").strip(),
        bairro=str(d.get("neighborhood") or "").strip(),
        municipio=str(d.get("city") or "").strip(),
        uf=str(d.get("state") or "").strip().upper(),
        cep=normalizar(d.get("cep")),
    )


def consultar_cep(bruto: object) -> Endereco | None:
    """Devolve o :class:`Endereco` do CEP, ou ``None`` se não encontrado.

    Levanta :class:`CEPInvalidoError` apenas para erro de formato — falha de
    rede ou CEP inexistente devolve ``None`` com o motivo registrado no log.
    O número e o complemento sempre ficam em branco: nenhuma base pública
    devolve isso, é digitação do usuário.
    """
    cep = validar(bruto)

    with criar_sessao() as sessao:
        for nome, url, adapter in (
            ("ViaCEP", VIACEP, _de_viacep),
            ("BrasilAPI/CEP", BRASILAPI_CEP, _de_brasilapi),
        ):
            bruto_json = get_json(sessao, url.format(cep=cep), rotulo=nome)
            if not bruto_json:
                continue
            endereco = adapter(bruto_json)
            if endereco:
                return endereco
            logger.info("[%s] CEP %s não localizado.", nome, cep)

    logger.warning("CEP %s não localizado em nenhum provedor.", cep)
    return None
