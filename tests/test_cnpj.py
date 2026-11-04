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


@pytest.mark.parametrize(
    "valor",
    [
        "11.222.333/0001-81",
        "11222333000181",
        "00.000.000/0001-91",
        "19.131.243/0001-97",
        "34.028.316/0001-03",
        "  11222333000181  ",
    ],
)
def test_cnpj_numerico_valido(valor):
    assert len(validar(valor)) == 14


@pytest.mark.parametrize(
    "valor",
    [
        "11222333000180",  # DV errado
        "1122233300018",  # curto demais
        "112223330001811",  # longo demais
        "11111111111111",  # sequência repetida
        "",
        None,
        "11.222.333/0001-8X",  # DV não numérico
    ],
)
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
    assert antigo == "123450135"  # letras sumiram
    assert len(antigo) != 14  # logo, era rejeitado como inválido
    assert validar("12ABC34501DE35") == "12ABC34501DE35"


# --------------------------------------------------------------------------- #
# Detecção de MEI — ausente não é o mesmo que negativo                         #
# --------------------------------------------------------------------------- #
# O defeito real: um MEI foi classificado como Simples Nacional / Anexo I / 4%
# da receita. A causa foi `bool(None) is False` — o código lia a AUSÊNCIA de
# informação como NEGATIVA. É a mesma família do bug da inscrição estadual.
from src.services.cnpj_providers import _booleano_ou_nulo, _consolidar  # noqa: E402


def test_none_nao_vira_false():
    assert _booleano_ou_nulo(None) is None


def test_ausencia_de_chave_e_desconhecida():
    assert _booleano_ou_nulo({}.get("opcao_pelo_mei")) is None


def test_sim_e_nao_da_cnpjws():
    assert _booleano_ou_nulo("Sim") is True
    assert _booleano_ou_nulo("Não") is False
    assert _booleano_ou_nulo("nao") is False


def test_booleano_puro_continua_funcionando():
    assert _booleano_ou_nulo(True) is True
    assert _booleano_ou_nulo(False) is False


def test_valor_inesperado_e_desconhecido_e_nao_false():
    assert _booleano_ou_nulo("talvez") is None


def test_consolidar_um_sim_vence():
    fontes = [{"optante_mei": None}, {"optante_mei": True}, {"optante_mei": False}]
    assert _consolidar(fontes, "optante_mei") is True


def test_consolidar_nao_afirmativo_vence_o_desconhecido():
    assert _consolidar([{"optante_mei": None}, {"optante_mei": False}], "optante_mei") is False


def test_consolidar_ninguem_informou_devolve_none():
    """O `any()` anterior devolvia False aqui — indistinguível de "todos
    disseram que não"."""
    assert _consolidar([{"optante_mei": None}, {"optante_mei": None}], "optante_mei") is None
    assert _consolidar([{}, {}], "optante_mei") is None


# --------------------------------------------------------------------------- #
# Datas de opção pelo Simples / MEI                                            #
# --------------------------------------------------------------------------- #
# Os três provedores guardam isto em lugares diferentes. Os nomes de campo da
# BrasilAPI e da CNPJ.ws foram conferidos na documentação de cada uma; os da
# ReceitaWS seguem o formato documentado dela. Se algum mudar, estes testes
# acusam — e, em produção, o campo vem vazio e a linha não é impressa, nunca
# com valor errado.


def test_brasilapi_le_as_datas_de_opcao_e_exclusao():
    from src.services.cnpj_providers import _de_brasilapi

    d = _de_brasilapi(
        {
            "opcao_pelo_simples": True,
            "data_opcao_pelo_simples": "2021-03-15",
            "data_exclusao_do_simples": None,
            "opcao_pelo_mei": False,
            "data_opcao_pelo_mei": "2019-01-10",
            "data_exclusao_do_mei": "2021-03-14",
        }
    )

    assert d["simples_desde"] == "2021-03-15"
    assert d["simples_ate"] == ""
    assert d["mei_desde"] == "2019-01-10"
    assert d["mei_ate"] == "2021-03-14"


def test_cnpjws_guarda_as_datas_do_mei_dentro_de_simples():
    """Detalhe que engana: na CNPJ.ws os campos do MEI ficam dentro do
    objeto `simples`, e não no primeiro nível como na BrasilAPI."""
    from src.services.cnpj_providers import _de_cnpjws

    d = _de_cnpjws(
        {
            "estabelecimento": {},
            "simples": {
                "simples": "Sim",
                "data_opcao_simples": "2021-03-15",
                "data_exclusao_simples": None,
                "mei": "Não",
                "data_opcao_mei": "2019-01-10",
                "data_exclusao_mei": "2021-03-14",
            },
        }
    )

    assert d["simples_desde"] == "2021-03-15"
    assert d["mei_desde"] == "2019-01-10"
    assert d["mei_ate"] == "2021-03-14"


def test_receitaws_separa_mei_em_simei():
    from src.services.cnpj_providers import _de_receitaws

    d = _de_receitaws(
        {
            "atividade_principal": [{}],
            "simples": {"optante": True, "data_opcao": "15/03/2021", "data_exclusao": None},
            "simei": {
                "optante": False,
                "data_opcao": "10/01/2019",
                "data_exclusao": "14/03/2021",
            },
        }
    )

    assert d["simples_desde"] == "15/03/2021"
    assert d["mei_ate"] == "14/03/2021"


def test_provedor_sem_as_datas_devolve_vazio_e_nao_quebra():
    """Provedor que não manda os campos não pode derrubar a consulta."""
    from src.services.cnpj_providers import _de_brasilapi, _de_cnpjws, _de_receitaws

    assert _de_brasilapi({})["simples_desde"] == ""
    assert _de_cnpjws({"estabelecimento": {}, "simples": None})["mei_ate"] == ""
    assert _de_receitaws({"atividade_principal": [{}]})["mei_desde"] == ""
