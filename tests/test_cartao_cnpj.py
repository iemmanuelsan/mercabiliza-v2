"""Cartão CNPJ — leiaute do comprovante da Receita.

O que estes testes protegem não é estética: é a **procedência**. Um
documento que reproduz a grade do comprovante oficial e não diz de onde veio
é um documento que circula como se fosse o oficial. A tarja e a nota de
origem são requisito, não enfeite.
"""

import io
import warnings

import pypdf
import pytest

from src.core.models import AtividadeCNAE, Empresa, Endereco, SituacaoCadastral
from src.core.tributario import classificar_cnae
from src.exporters.pdf_cartao import _cep_br, _data_br, _telefone_br, gerar_cartao_cnpj

warnings.filterwarnings("ignore")


def _cnae(codigo: str, descricao: str) -> AtividadeCNAE:
    return AtividadeCNAE(
        codigo=codigo, descricao=descricao, diagnostico=classificar_cnae(codigo)
    )


def _empresa(**troca) -> Empresa:
    base = dict(
        cnpj="62350925000110",
        razao_social="MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA",
        nome_fantasia="MERCABILIZA",
        matriz_filial="MATRIZ",
        data_abertura="2025-08-22",
        natureza_juridica="206-2 - Sociedade Empresária Limitada",
        porte="DEMAIS",
        emails=("contato@mercabiliza.com.br",),
        telefones=("1933270038",),
        endereco=Endereco(
            logradouro="RUA ANCHIETA",
            numero="204",
            complemento="SALA 102",
            bairro="VILA BOAVENTURA",
            municipio="JUNDIAI",
            uf="SP",
            cep="13201804",
        ),
        situacao=SituacaoCadastral(situacao_receita="ATIVA", data_situacao="2025-08-22"),
        atividade_principal=_cnae("6920601", "Atividades de contabilidade"),
        fontes=("BrasilAPI", "CNPJ.ws"),
    )
    base.update(troca)
    return Empresa(**base)


def _texto(pdf: bytes) -> str:
    return "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)


# --------------------------------------------------------------------------- #
# Procedência — o que impede o documento de passar por oficial                 #
# --------------------------------------------------------------------------- #
def test_traz_a_tarja_de_reproducao():
    texto = _texto(gerar_cartao_cnpj(_empresa()))
    assert "NÃO É O COMPROVANTE OFICIAL DA RECEITA FEDERAL" in texto


def test_nao_afirma_aprovacao_normativa():
    """O comprovante oficial traz 'Aprovado pela Instrução Normativa RFB nº
    2.119'. Reproduzir essa linha seria afirmar uma aprovação que este papel
    não tem — e é justamente ela que faria a reprodução passar por original."""
    texto = _texto(gerar_cartao_cnpj(_empresa()))
    assert "Instrução Normativa" not in texto
    assert "2.119" not in texto


def test_nomeia_as_fontes_consultadas():
    texto = _texto(gerar_cartao_cnpj(_empresa(fontes=("BrasilAPI", "ReceitaWS"))))
    assert "BrasilAPI" in texto and "ReceitaWS" in texto
    assert "Receita Federal" in texto  # a orientação de onde tirar o oficial


# --------------------------------------------------------------------------- #
# Fidelidade da grade                                                          #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "rotulo",
    [
        "NÚMERO DE INSCRIÇÃO",
        "DATA DE ABERTURA",
        "NOME EMPRESARIAL",
        "TÍTULO DO ESTABELECIMENTO (NOME DE FANTASIA)",
        "PORTE",
        "CÓDIGO E DESCRIÇÃO DA ATIVIDADE ECONÔMICA PRINCIPAL",
        "CÓDIGO E DESCRIÇÃO DAS ATIVIDADES ECONÔMICAS SECUNDÁRIAS",
        "CÓDIGO E DESCRIÇÃO DA NATUREZA JURÍDICA",
        "LOGRADOURO",
        "NÚMERO",
        "COMPLEMENTO",
        "CEP",
        "BAIRRO/DISTRITO",
        "MUNICÍPIO",
        "UF",
        "ENDEREÇO ELETRÔNICO",
        "TELEFONE",
        "ENTE FEDERATIVO RESPONSÁVEL (EFR)",
        "SITUAÇÃO CADASTRAL",
        "DATA DA SITUAÇÃO CADASTRAL",
        "MOTIVO DE SITUAÇÃO CADASTRAL",
        "SITUAÇÃO ESPECIAL",
    ],
)
def test_todos_os_rotulos_do_comprovante(rotulo: str):
    assert rotulo in _texto(gerar_cartao_cnpj(_empresa()))


def test_cabe_em_uma_pagina():
    pdf = gerar_cartao_cnpj(_empresa())
    assert len(pypdf.PdfReader(io.BytesIO(pdf)).pages) == 1


def test_muitas_atividades_secundarias_nao_estouram_a_pagina():
    """Empresa de minimercado costuma ter uma lista longa. A caixa tem altura
    limitada justamente para a grade não empurrar o rodapé para a página 2."""
    secundarias = tuple(
        _cnae(f"472{i}100", f"Comércio varejista de item número {i} com descrição longa")
        for i in range(12)
    )
    pdf = gerar_cartao_cnpj(_empresa(atividades_secundarias=secundarias))
    assert len(pypdf.PdfReader(io.BytesIO(pdf)).pages) == 1


def test_sem_atividade_secundaria_diz_nao_informada():
    texto = _texto(gerar_cartao_cnpj(_empresa(atividades_secundarias=())))
    assert "Não informada" in texto


# --------------------------------------------------------------------------- #
# Formatação — a diferença que mais salta aos olhos de quem usa o documento    #
# --------------------------------------------------------------------------- #
def test_data_sai_no_formato_brasileiro():
    # A versão anterior imprimia o ISO cru vindo da API.
    assert _data_br("2025-08-22") == "22/08/2025"
    assert _data_br("2025-08-22T10:30:00") == "22/08/2025"
    assert _data_br("22/08/2025") == "22/08/2025"
    texto = _texto(gerar_cartao_cnpj(_empresa()))
    assert "22/08/2025" in texto
    assert "2025-08-22" not in texto


def test_data_ausente_vira_asteriscos_como_no_original():
    assert _data_br("") == "********"


def test_telefone_e_cep_formatados():
    assert _telefone_br("1933270038") == "(19) 3327-0038"
    assert _telefone_br("11987654321") == "(11) 98765-4321"
    assert _cep_br("13201804") == "13.201-804"
    texto = _texto(gerar_cartao_cnpj(_empresa()))
    assert "(19) 3327-0038" in texto
    assert "13.201-804" in texto


def test_empresa_quase_vazia_nao_quebra():
    """CNPJ recém-aberto costuma vir com metade dos campos em branco."""
    pdf = gerar_cartao_cnpj(Empresa(cnpj="62350925000110"))
    assert len(pdf) > 1000
    assert "********" in _texto(pdf)


# --------------------------------------------------------------------------- #
# Transbordo — o defeito que nenhum teste de texto pega                        #
# --------------------------------------------------------------------------- #
def test_lista_longa_avisa_quantas_ficaram_de_fora():
    secundarias = tuple(
        _cnae(f"472{i}100", f"Comércio varejista de item {i}") for i in range(12)
    )
    texto = _texto(gerar_cartao_cnpj(_empresa(atividades_secundarias=secundarias)))
    assert "atividade(s) — lista completa no dossiê" in texto


def test_caixa_de_lista_nunca_passa_da_altura_reservada():
    """A invariante que impede o transbordo.

    ``multi_cell`` NÃO recorta ao chegar na altura reservada: continua
    desenhando por cima das caixas de baixo. Com 12 CNAEs, a lista escorria
    por dentro de "natureza jurídica" e "logradouro" — e o PDF continuava
    tendo uma página só, então nem a contagem de páginas denunciava. Só
    olhando o arquivo renderizado.

    Este teste mede o que o código promete: o cursor desce exatamente a
    altura anunciada, nem um milímetro a mais.
    """
    from src.exporters.pdf_cartao import LARGURA, _Cartao

    pdf = _Cartao()
    pdf.add_page()
    y_inicial = pdf.get_y()
    maximo = 9
    pdf.caixa_lista(
        LARGURA,
        "TESTE",
        [f"{i} - descrição bem longa " + "x" * 200 for i in range(40)],
        maximo=maximo,
    )
    descida = pdf.get_y() - y_inicial

    assert descida == pytest.approx(_Cartao.ROTULO + 3.6 * maximo, abs=0.01)


def test_item_longo_demais_e_cortado_e_nao_quebra_linha():
    """Uma descrição que não cabe vira uma linha com reticências, e não duas."""
    from src.exporters.pdf_cartao import LARGURA, _Cartao

    pdf = _Cartao()
    pdf.add_page()
    y_inicial = pdf.get_y()
    pdf.caixa_lista(LARGURA, "TESTE", ["A" * 400], maximo=4)

    assert pdf.get_y() - y_inicial == pytest.approx(_Cartao.ROTULO + 3.6, abs=0.01)
