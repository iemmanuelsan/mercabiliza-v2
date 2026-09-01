import pytest

from src.core.cpf import (
    CPFInvalidoError,
    calcular_digitos,
    eh_valido,
    formatar,
    normalizar,
    validar,
)


@pytest.mark.parametrize("valor", [
    "529.982.247-25",
    "52998224725",
    "111.444.777-35",
    "123.456.789-09",
    "  529.982.247-25  ",
])
def test_cpf_valido(valor):
    assert len(validar(valor)) == 11


@pytest.mark.parametrize("valor", [
    "529.982.247-26",   # DV errado
    "5299822472",       # curto
    "529982247255",     # longo
    "11111111111",      # repetido
    "00000000000",
    "",
    None,
    "abc.def.ghi-jk",
])
def test_cpf_invalido(valor):
    assert not eh_valido(valor)
    with pytest.raises(CPFInvalidoError):
        validar(valor)


def test_digitos_conferem_com_valores_conhecidos():
    assert calcular_digitos("529982247") == "25"
    assert calcular_digitos("111444777") == "35"
    assert calcular_digitos("123456789") == "09"


def test_base_de_tamanho_errado():
    with pytest.raises(CPFInvalidoError):
        calcular_digitos("12345")


def test_formatacao():
    assert formatar("52998224725") == "529.982.247-25"
    assert formatar("123") == "123"          # devolve como veio se inválido


def test_normalizar_remove_mascara():
    assert normalizar(" 529.982.247-25 ") == "52998224725"


def test_mensagem_de_erro_e_acionavel():
    """A mensagem vai direto para a tela — precisa dizer o que fazer."""
    with pytest.raises(CPFInvalidoError, match="11 dígitos"):
        validar("123")
    with pytest.raises(CPFInvalidoError, match=r"[Dd]ígito verificador"):
        validar("52998224726")
