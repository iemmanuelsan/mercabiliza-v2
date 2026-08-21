"""Ponto de entrada único dos documentos jurídicos.

A UI importa daqui e não precisa saber que a ficha e o contrato moram em
módulos separados — mantém a superfície pública pequena e estável mesmo que a
organização interna mude.

    from src.exporters.pdf_documentos import (
        gerar_ficha_cadastral,   # preenchida, para conferência e assinatura
        gerar_ficha_em_branco,   # vazia, para o cliente preencher (sem CNPJ)
        gerar_contrato,          # minuta com as partes qualificadas
        previa_contrato,         # texto para pré-visualizar em tela
    )
"""

from __future__ import annotations

from ..core.contrato import ParametrosContrato
from ..core.pessoas import Contratada, ContratantePF, ContratantePJ
from .pdf_contrato import gerar_contrato
from .pdf_contrato import previa_texto as previa_contrato
from .pdf_ficha import gerar_ficha_em_branco, gerar_ficha_preenchida

__all__ = [
    "gerar_contrato",
    "gerar_ficha_cadastral",
    "gerar_ficha_em_branco",
    "previa_contrato",
]


def gerar_ficha_cadastral(
    contratante: ContratantePF | ContratantePJ,
    contratada: Contratada | None = None,
    parametros: ParametrosContrato | None = None,
    incluir_pendencias: bool = True,
) -> bytes:
    """Ficha cadastral preenchida, para o cliente conferir e assinar.

    ``parametros`` é opcional: a ficha costuma ser emitida **antes** de fechar
    valores. Quando os valores já estão acordados, informá-los acrescenta a
    seção de condições comerciais no mesmo documento.
    """
    return gerar_ficha_preenchida(
        contratante, contratada, parametros, incluir_pendencias=incluir_pendencias
    )
