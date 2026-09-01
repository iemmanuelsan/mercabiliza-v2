"""Validação e formatação de CPF (módulo 11).

Espelha a interface de ``core/cnpj.py`` de propósito: mesma nomenclatura
(``validar``, ``eh_valido``, ``formatar``, ``normalizar``) e mesmo estilo de
exceção com mensagem acionável, para que a UI trate PF e PJ do mesmo jeito.
"""

from __future__ import annotations

import re

TAMANHO_CPF = 11
_NAO_DIGITO = re.compile(r"\D")


class CPFInvalidoError(ValueError):
    """CPF que não passa na validação estrutural ou de dígito verificador."""


def normalizar(bruto: object) -> str:
    """Remove máscara e qualquer caractere não numérico."""
    return _NAO_DIGITO.sub("", str(bruto or ""))


def _digito(base: str) -> int:
    """Módulo 11 com pesos decrescentes a partir de ``len(base) + 1``."""
    peso_inicial = len(base) + 1
    soma = sum(int(d) * (peso_inicial - i) for i, d in enumerate(base))
    resto = soma % 11
    return 0 if resto < 2 else 11 - resto


def calcular_digitos(base9: str) -> str:
    """Calcula os dois dígitos verificadores a partir dos 9 primeiros."""
    base9 = normalizar(base9)
    if len(base9) != 9:
        raise CPFInvalidoError("A base do CPF precisa ter exatamente 9 dígitos.")
    dv1 = _digito(base9)
    dv2 = _digito(f"{base9}{dv1}")
    return f"{dv1}{dv2}"


def validar(bruto: object) -> str:
    """Devolve o CPF limpo e válido ou levanta :class:`CPFInvalidoError`."""
    cpf = normalizar(bruto)

    if not cpf:
        raise CPFInvalidoError("Informe o CPF.")
    if len(cpf) != TAMANHO_CPF:
        raise CPFInvalidoError(
            f"CPF deve ter {TAMANHO_CPF} dígitos (recebidos {len(cpf)})."
        )
    if len(set(cpf)) == 1:
        raise CPFInvalidoError("Sequência repetida não é um CPF válido.")
    if calcular_digitos(cpf[:9]) != cpf[9:]:
        raise CPFInvalidoError("Dígito verificador inválido — confira a digitação.")
    return cpf


def eh_valido(bruto: object) -> bool:
    try:
        validar(bruto)
    except CPFInvalidoError:
        return False
    return True


def formatar(cpf: str) -> str:
    """``12345678909`` -> ``123.456.789-09``."""
    c = normalizar(cpf)
    if len(c) != TAMANHO_CPF:
        return str(cpf)
    return f"{c[:3]}.{c[3:6]}.{c[6:9]}-{c[9:]}"
