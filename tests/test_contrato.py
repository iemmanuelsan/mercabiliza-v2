from datetime import date

import pytest

from src.core.contrato import (
    OBJETO_PADRAO,
    ParametrosContrato,
    data_extenso,
    numero_extenso,
    renderizar_minuta,
    valor_extenso,
)
from src.core.models import Endereco
from src.core.pessoas import (
    ContratantePF,
    ContratantePJ,
    RepresentanteLegal,
    contratada_padrao,
)

END = Endereco(logradouro="Rua Anchieta", numero="204", bairro="Vila Boaventura",
               municipio="Jundiaí", uf="SP", cep="13201804")


# --------------------------------------------------------------------------- #
# Números e datas por extenso                                                  #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n,esperado", [
    (0, "zero"), (1, "um"), (15, "quinze"), (21, "vinte e um"),
    (30, "trinta"), (100, "cem"), (101, "cento e um"), (200, "duzentos"),
    (350, "trezentos e cinquenta"), (999, "novecentos e noventa e nove"),
    (1000, "mil"), (1001, "mil e um"), (2000, "dois mil"),
    (15000, "quinze mil"), (100000, "cem mil"),
])
def test_numero_extenso(n, esperado):
    assert numero_extenso(n) == esperado


@pytest.mark.parametrize("valor,esperado", [
    (350.0, "trezentos e cinquenta reais"),
    (1.0, "um real"),
    (2.50, "dois reais e cinquenta centavos"),
    (0.99, "noventa e nove centavos"),
    (1600.0, "mil e seiscentos reais"),
    (0.0, "zero reais"),
])
def test_valor_extenso(valor, esperado):
    assert valor_extenso(valor) == esperado


def test_valor_extenso_arredonda_centavos():
    """0,999 não pode virar '100 centavos'."""
    assert valor_extenso(1.999) == "dois reais"


def test_data_extenso():
    assert data_extenso(date(2026, 8, 17)) == "17 de agosto de 2026"
    assert data_extenso(date(2026, 3, 1)) == "1 de março de 2026"


# --------------------------------------------------------------------------- #
# Parâmetros                                                                   #
# --------------------------------------------------------------------------- #
def test_parametros_vazios_listam_pendencias():
    pend = ParametrosContrato().pendencias
    assert any("valor mensal" in p for p in pend)
    assert any("foro" in p for p in pend)


def test_parametros_completos_sem_pendencias():
    p = ParametrosContrato(valor_mensal=550.0, foro="Jundiaí/SP")
    assert p.pendencias == ()


def test_dia_de_vencimento_fora_da_faixa_e_pendencia():
    assert any("vencimento" in p for p in
               ParametrosContrato(valor_mensal=1, foro="X",
                                  dia_vencimento=45).pendencias)


def test_dict_template_formata_em_pt_br():
    p = ParametrosContrato(valor_mensal=550.0, foro="Jundiaí/SP",
                           data_inicio=date(2026, 9, 1))
    d = p.como_dict_template()
    assert d["valor_mensal_fmt"] == "R$ 550,00"
    assert d["honorarios_extenso"] == "quinhentos e cinquenta reais"
    assert d["data_inicio_fmt"] == "1 de setembro de 2026"


def test_implantacao_zero_nao_gera_texto():
    """Cláusula de implantação só deve existir se houver valor."""
    p = ParametrosContrato(valor_mensal=350.0, foro="X", valor_implantacao=0.0)
    assert p.como_dict_template()["valor_implantacao_fmt"] == ""


def test_clausulas_particulares_vazias_sao_descartadas():
    p = ParametrosContrato(valor_mensal=1, foro="X",
                           clausulas_particulares=("  ", "", "válida"))
    assert p.como_dict_template()["clausulas_particulares"] == ["válida"]


# --------------------------------------------------------------------------- #
# Renderização da minuta                                                       #
# --------------------------------------------------------------------------- #
def _pj() -> ContratantePJ:
    return ContratantePJ(
        razao_social="Mercadinho São João Ltda", cnpj="11222333000181",
        endereco=END, email="a@b.com",
        representante=RepresentanteLegal(nome="Ana Costa", cpf="52998224725",
                                         qualificacao="sócia administradora",
                                         genero_feminino=True),
    )


def _params(**kw) -> ParametrosContrato:
    base = {"valor_mensal": 550.0, "foro": "Jundiaí/SP",
            "cidade_assinatura": "Jundiaí", "data_inicio": date(2026, 9, 1),
            "data_assinatura": date(2026, 9, 1)}
    return ParametrosContrato(**{**base, **kw})


def test_minuta_renderiza_com_as_partes():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "MERCADINHO SÃO JOÃO LTDA" in texto
    assert "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA" in texto
    assert "CLÁUSULA 1 - DO OBJETO" in texto
    assert "[[ASSINATURAS]]" in texto


def test_minuta_tem_todas_as_clausulas_essenciais():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    for termo in ("DO OBJETO", "DOS DEVERES DA CONTRATADA",
                  "DOS DEVERES DA CONTRATANTE", "DOS VALORES",
                  "DA VIGÊNCIA E RESCISÃO", "PROTEÇÃO DE DADOS",
                  "DO FORO"):
        assert termo in texto, f"cláusula ausente: {termo}"


def test_valor_aparece_formatado_e_por_extenso():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "R$ 550,00" in texto
    assert "quinhentos e cinquenta reais" in texto


def test_objeto_nao_duplica_a_palavra_servicos():
    """O template diz 'dos serviços de {objeto}' — o objeto padrão não pode
    começar com 'serviços de', senão sai 'serviços de serviços de'."""
    assert not OBJETO_PADRAO.lower().startswith("serviços de")
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "serviços de serviços" not in texto.lower()


def test_sem_implantacao_nao_menciona_taxa():
    texto = renderizar_minuta(_pj(), contratada_padrao(),
                             _params(valor_implantacao=0.0))
    assert "título de implantação" not in texto


def test_com_implantacao_menciona_taxa():
    texto = renderizar_minuta(_pj(), contratada_padrao(),
                             _params(valor_implantacao=350.0))
    assert "título de implantação" in texto
    assert "R$ 350,00" in texto


def test_vigencia_zero_cai_no_padrao_de_12_meses():
    """O contrato modelo da Mercabiliza é sempre por prazo determinado. Deixar
    a vigência em zero não pode gerar cláusula vazia — assume os 12 meses."""
    texto = renderizar_minuta(_pj(), contratada_padrao(),
                             _params(vigencia_meses=0))
    assert "12 (doze) meses" in texto


def test_vigencia_definida_aparece_por_extenso():
    texto = renderizar_minuta(_pj(), contratada_padrao(),
                             _params(vigencia_meses=12))
    assert "12 (doze) meses" in texto


def test_clausulas_particulares_criam_secao_e_renumeram_o_foro():
    sem = renderizar_minuta(_pj(), contratada_padrao(), _params())
    com = renderizar_minuta(_pj(), contratada_padrao(),
                            _params(clausulas_particulares=("Desconto de 20%.",)))
    assert "DISPOSIÇÕES PARTICULARES" not in sem
    assert "CLÁUSULA 7 - DO FORO" in sem
    assert "DISPOSIÇÕES PARTICULARES" in com
    assert "Desconto de 20%." in com
    assert "CLÁUSULA 8 - DO FORO" in com


def test_minuta_funciona_para_pessoa_fisica():
    pf = ContratantePF(nome="João Souza", cpf="11144477735",
                       estado_civil="solteiro", profissao="comerciante",
                       endereco=END)
    texto = renderizar_minuta(pf, contratada_padrao(), _params())
    assert "JOÃO SOUZA" in texto
    assert "denominado simplesmente CONTRATANTE" in texto


def test_local_e_data_no_fecho():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "Jundiaí, 1 de setembro de 2026." in texto


# --------------------------------------------------------------------------- #
# Bloco fixo da CONTRATADA (duas empresas do grupo)                            #
# --------------------------------------------------------------------------- #
def test_contratada_traz_as_duas_empresas_do_grupo():
    """A qualificação da CONTRATADA é texto fixo definido pela diretoria:
    as duas empresas, sem CRC e sem nomear pessoa física."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA" in texto
    assert "62.350.925/0001-10" in texto
    assert "MERCABILIZA SOLUCOES EM TECNOLOGIA E GESTAO LTDA" in texto
    assert "62.291.063/0001-00" in texto


def test_contratada_nao_menciona_crc_nem_pessoa_fisica():
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    cabecalho = texto[:texto.index("CONTRATANTE:")]
    assert "CRC" not in cabecalho
    assert "Luis Felipe" not in cabecalho


def test_escopo_de_dp_e_monofasico_e_opcional():
    """Cliente sem funcionário não recebe a cláusula trabalhista."""
    com_dp = renderizar_minuta(_pj(), contratada_padrao(),
                               _params(incluir_dp=True))
    sem_dp = renderizar_minuta(_pj(), contratada_padrao(),
                               _params(incluir_dp=False))
    assert "ÁREA TRABALHISTA E PREVIDENCIÁRIA" in com_dp
    assert "ÁREA TRABALHISTA E PREVIDENCIÁRIA" not in sem_dp

    com_mono = renderizar_minuta(_pj(), contratada_padrao(),
                                 _params(incluir_monofasico=True))
    sem_mono = renderizar_minuta(_pj(), contratada_padrao(),
                                 _params(incluir_monofasico=False))
    assert "monofásica" in com_mono
    assert "monofásica" not in sem_mono


def test_nota_de_rodape_cita_o_codigo_civil_correto():
    """O modelo em uso cita 'Lei 10.402/2002'; o Código Civil é a 10.406/2002."""
    texto = renderizar_minuta(_pj(), contratada_padrao(), _params())
    assert "10.406/2002" in texto
    assert "10.402/2002" not in texto
