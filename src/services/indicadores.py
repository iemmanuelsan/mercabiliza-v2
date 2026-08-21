"""Indicadores macroeconômicos do BACEN (SGS) e localidades do IBGE."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import (
    BACEN_SGS,
    IBGE_MUNICIPIOS,
    IPCA_FALLBACK_AA,
    SELIC_FALLBACK_AA,
    SGS_IPCA_MENSAL,
    SGS_SELIC_MENSAL,
)
from .http import criar_sessao, get_json

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Indicadores:
    selic_acumulada_12m: float
    ipca_acumulado_12m: float
    ao_vivo: bool


def _acumular_composto(valores: list[float]) -> float | None:
    """Acumula taxas mensais compostas: ``(Π(1+i) − 1) × 100``.

    [CORRIGIDO] O código original fazia ``sum(...)`` das 12 taxas mensais.
    Somar taxas percentuais subestima o acumulado (ignora juros sobre juros) e
    a série 4390 é justamente "Selic acumulada NO MÊS". O erro se propagava
    direto para os encargos de mora do cálculo retroativo do MEI.
    """
    if not valores:
        return None
    fator = 1.0
    for taxa in valores:
        fator *= 1 + taxa / 100.0
    return (fator - 1) * 100.0


def _serie_ultimos_12(sessao, serie: int, rotulo: str) -> float | None:
    dados = get_json(sessao, BACEN_SGS.format(serie=serie, n=12), rotulo=rotulo)
    if not dados:
        return None
    itens = dados.get("_lista", dados if isinstance(dados, list) else [])
    valores: list[float] = []
    for item in itens:
        try:
            valores.append(float(str(item["valor"]).replace(",", ".")))
        except (KeyError, TypeError, ValueError):
            continue
    if len(valores) < 12:
        logger.info("[%s] série incompleta (%d/12 pontos).", rotulo, len(valores))
    return _acumular_composto(valores)


def obter_indicadores() -> Indicadores:
    """Selic e IPCA acumulados em 12 meses. Nunca levanta exceção."""
    with criar_sessao() as sessao:
        selic = _serie_ultimos_12(sessao, SGS_SELIC_MENSAL, "BACEN/Selic")
        ipca = _serie_ultimos_12(sessao, SGS_IPCA_MENSAL, "BACEN/IPCA")

    ao_vivo = selic is not None and ipca is not None
    return Indicadores(
        selic_acumulada_12m=round(selic if selic is not None else SELIC_FALLBACK_AA, 2),
        ipca_acumulado_12m=round(ipca if ipca is not None else IPCA_FALLBACK_AA, 2),
        ao_vivo=ao_vivo,
    )


def consultar_municipio_ibge(nome_municipio: str, uf: str) -> tuple[str, str]:
    """Devolve ``(codigo_ibge, regiao)``."""
    if not nome_municipio or not uf:
        return "N/A", "Brasil"

    with criar_sessao() as sessao:
        dados = get_json(sessao, IBGE_MUNICIPIOS.format(uf=uf), rotulo="IBGE")

    municipios = (dados or {}).get("_lista", [])
    alvo = nome_municipio.strip().casefold()
    for municipio in municipios:
        if str(municipio.get("nome", "")).strip().casefold() == alvo:
            regiao = (
                municipio.get("microrregiao", {})
                .get("mesorregiao", {})
                .get("UF", {})
                .get("regiao", {})
                .get("nome")
            ) or "Brasil"
            return str(municipio.get("id", "N/A")), regiao
    return "N/A", "Brasil"
