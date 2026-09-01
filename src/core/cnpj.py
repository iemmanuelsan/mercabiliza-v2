"""Normalização e validação de CNPJ — numérico e alfanumérico.

Contexto regulatório (IN RFB 2.229/2024): desde julho/2026 a Receita Federal
emite CNPJs **alfanuméricos**. O layout continua com 14 posições:

    posições 1-8   raiz            0-9 e A-Z
    posições 9-12  ordem da filial 0-9 e A-Z
    posições 13-14 dígitos         SOMENTE 0-9

O dígito verificador segue módulo 11, mas o valor de cada caractere passa a
ser ``ord(c) - 48`` ("0"->0 ... "9"->9, "A"->17 ... "Z"->42). Para um CNPJ
totalmente numérico o resultado é idêntico ao algoritmo antigo, então esta
implementação é retrocompatível.
"""

from __future__ import annotations

import re

TAMANHO_CNPJ = 14
# Pesos do módulo 11: ciclo 2..9 aplicado da direita para a esquerda.
_PESOS_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CARACTERES_VALIDOS = re.compile(r"[^0-9A-Z]")


class CNPJInvalidoError(ValueError):
    """CNPJ que não passa na validação estrutural ou de dígito verificador."""


def normalizar(bruto: object) -> str:
    """Remove máscara e devolve o CNPJ em caixa alta, sem validar."""
    return _CARACTERES_VALIDOS.sub("", str(bruto or "").upper())


def _valor(caractere: str) -> int:
    return ord(caractere) - 48


def _digito(base: str, pesos: tuple[int, ...]) -> int:
    soma = sum(_valor(c) * p for c, p in zip(base, pesos, strict=True))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def calcular_digitos(base12: str) -> str:
    """Calcula os dois dígitos verificadores a partir das 12 primeiras posições."""
    base12 = normalizar(base12)
    if len(base12) != 12:
        raise CNPJInvalidoError("A base do CNPJ precisa ter exatamente 12 caracteres.")
    dv1 = _digito(base12, _PESOS_DV1)
    dv2 = _digito(f"{base12}{dv1}", _PESOS_DV2)
    return f"{dv1}{dv2}"


def eh_valido(bruto: object) -> bool:
    try:
        validar(bruto)
    except CNPJInvalidoError:
        return False
    return True


def validar(bruto: object) -> str:
    """Devolve o CNPJ limpo e válido ou levanta :class:`CNPJInvalidoError`.

    Substitui o antigo ``limpar_cnpj``, que apenas conferia o comprimento e
    devolvia ``None`` silenciosamente — mascarando erros de digitação e
    descartando letras de CNPJs alfanuméricos.
    """
    cnpj = normalizar(bruto)

    if len(cnpj) != TAMANHO_CNPJ:
        raise CNPJInvalidoError(
            f"CNPJ deve ter {TAMANHO_CNPJ} caracteres (recebidos {len(cnpj)})."
        )
    if not cnpj[12:].isdigit():
        raise CNPJInvalidoError("As duas últimas posições do CNPJ devem ser numéricas.")
    if cnpj.isdigit() and len(set(cnpj)) == 1:
        raise CNPJInvalidoError("Sequência repetida não é um CNPJ válido.")
    if calcular_digitos(cnpj[:12]) != cnpj[12:]:
        raise CNPJInvalidoError("Dígito verificador inválido — confira a digitação.")
    return cnpj


def formatar(cnpj: str) -> str:
    """``12ABC34501DE35`` -> ``12.ABC.345/01DE-35``."""
    c = normalizar(cnpj)
    if len(c) != TAMANHO_CNPJ:
        return str(cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def eh_alfanumerico(cnpj: str) -> bool:
    return not normalizar(cnpj).isdigit()


def somente_digitos_telefone(texto: object) -> str:
    return re.sub(r"\D", "", str(texto or ""))
