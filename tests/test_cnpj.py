import pytest

from src.core.cnpj import (
    CNPJInvalidoError,
    calcular_digitos,
    eh_alfanumerico,
    eh_valido,
    formatar,
    normalizar,
    validar,
)


@pytest.mark.parametrize("valor", [
    "11.222.333/0001-81",
    "11222333000181",
    "00.000.000/0001-91",
    "19.131.243/0001-97",
    "34.028.316/0001-03",
    "  11222333000181  ",
])
def test_cnpj_numerico_valido(valor):
    assert len(validar(valor)) == 14


@pytest.mark.parametrize("valor", [
    "11222333000180",       # DV errado
    "1122233300018",        # curto demais
    "112223330001811",      # longo demais
    "11111111111111",       # sequência repetida
    "",
    None,
    "11.222.333/0001-8X",   # DV não numérico
])
def test_cnpj_invalido(valor):
    assert not eh_valido(valor)
    with pytest.raises(CNPJInvalidoError):
        validar(valor)


def test_exemplo_oficial_alfanumerico_da_receita():
    """A RFB divulgou 12.ABC.345/01DE-35 como exemplo canônico."""
    assert calcular_digitos("12ABC34501DE") == "35"
    assert validar("12.ABC.345/01DE-35") == "12ABC34501DE35"


def test_primeiro_cnpj_alfanumerico_emitido():
    """Agência do Banco do Brasil, primeiro alfanumérico real (ago/2026)."""
    assert calcular_digitos("00000000E08G") == "12"
    assert eh_valido("00.000.000/E08G-12")


def test_letras_minusculas_sao_normalizadas():
    assert validar("12abc34501de35") == "12ABC34501DE35"


def test_deteccao_de_alfanumerico():
    assert eh_alfanumerico("12ABC34501DE35")
    assert not eh_alfanumerico("11222333000181")


def test_formatacao():
    assert formatar("11222333000181") == "11.222.333/0001-81"
    assert formatar("12ABC34501DE35") == "12.ABC.345/01DE-35"


def test_normalizar_remove_mascara_e_ruido():
    assert normalizar(" 11.222.333/0001-81 ") == "11222333000181"


def test_regressao_bug_original_perdia_letras():
    """O ``re.sub(r'\\D','')` original transformava um CNPJ alfanumérico válido
    em 8 dígitos e o descartava como inválido — silenciosamente."""
    import re
    antigo = re.sub(r"\D", "", "12ABC34501DE35")
    assert antigo == "123450135"          # letras sumiram
    assert len(antigo) != 14              # logo, era rejeitado como inválido
    assert validar("12ABC34501DE35") == "12ABC34501DE35"
