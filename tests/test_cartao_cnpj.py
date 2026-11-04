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
from src.exporters.pdf_cartao import (
    _cep_br,
    _telefone_br,
    data_br_cartao,
    gerar_cartao_cnpj,
)

warnings.filterwarnings("ignore")


def _cnae(codigo: str, descricao: str) -> AtividadeCNAE:
    return AtividadeCNAE(
        codigo=codigo, descricao=descricao, diagnostico=classificar_cnae(codigo)
    )


def _empresa(**troca) -> Empresa:
    base = {
        "cnpj": "62350925000110",
        "razao_social": "MERCABILIZA SOLUCOES FISCAIS E CONTABEIS LTDA",
        "nome_fantasia": "MERCABILIZA",
        "matriz_filial": "MATRIZ",
        "data_abertura": "2025-08-22",
        "natureza_juridica": "206-2 - Sociedade Empresária Limitada",
        "porte": "DEMAIS",
        "emails": ("contato@mercabiliza.com.br",),
        "telefones": ("1933270038",),
        "endereco": Endereco(
            logradouro="RUA ANCHIETA",
            numero="204",
            complemento="SALA 102",
            bairro="VILA BOAVENTURA",
            municipio="JUNDIAI",
            uf="SP",
            cep="13201804",
        ),
        "situacao": SituacaoCadastral(situacao_receita="ATIVA", data_situacao="2025-08-22"),
        "atividade_principal": _cnae("6920601", "Atividades de contabilidade"),
        "fontes": ("BrasilAPI", "CNPJ.ws"),
    }
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
    assert data_br_cartao("2025-08-22") == "22/08/2025"
    assert data_br_cartao("2025-08-22T10:30:00") == "22/08/2025"
    assert data_br_cartao("22/08/2025") == "22/08/2025"
    texto = _texto(gerar_cartao_cnpj(_empresa()))
    assert "22/08/2025" in texto
    assert "2025-08-22" not in texto


def test_data_ausente_vira_asteriscos_como_no_original():
    assert data_br_cartao("") == "********"


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


# --------------------------------------------------------------------------- #
# Opção pelo Simples / MEI                                                     #
# --------------------------------------------------------------------------- #
# Estes campos NÃO constam do comprovante oficial da Receita — lá a opção pelo
# Simples é consulta separada. Entram aqui para o fluxo interno, sob rótulo
# próprio, e é isso que os testes abaixo travam.


def test_optante_nao_informado_nao_vira_nao():
    """``None`` é "ninguém informou", não "não é optante".

    É a mesma confusão que já classificou MEI como Simples Nacional neste
    sistema. Num documento que o cliente lê, "NÃO" é uma afirmação que a
    Mercabiliza não tem base para fazer.
    """
    from src.exporters.pdf_cartao import _optante_br

    assert _optante_br(True) == "SIM"
    assert _optante_br(False) == "NÃO"
    assert _optante_br(None) == "NÃO INFORMADO"
    assert _optante_br(None) != _optante_br(False)


def test_cartao_traz_opcao_e_datas_do_simples_e_do_mei():
    pdf = gerar_cartao_cnpj(
        _empresa(
            optante_simples=True,
            optante_mei=False,
            simples_desde="2021-03-15",
            simples_ate="",
            mei_desde="2019-01-10",
            mei_ate="2021-03-14",
        )
    )
    texto = _texto(pdf)

    assert "OPÇÃO PELO SIMPLES NACIONAL" in texto
    assert "OPÇÃO PELO MEI" in texto
    # Datas em formato brasileiro, não o ISO que a API devolve.
    assert "15/03/2021" in texto
    assert "10/01/2019" in texto
    assert "14/03/2021" in texto
    assert "2021-03-15" not in texto


def test_cartao_avisa_que_esses_campos_nao_sao_do_comprovante_oficial():
    """Sem este rótulo, quem comparar com um comprovante de verdade conclui
    que o documento foi adulterado — ou pior, que o oficial está incompleto."""
    texto = _texto(gerar_cartao_cnpj(_empresa(optante_simples=True)))

    assert "NÃO CONSTAM DO COMPROVANTE OFICIAL" in texto


def test_cartao_sem_data_nao_inventa_data():
    """Provedor que não informou a data: o campo fica vazio, não com hoje."""
    from datetime import date

    texto = _texto(
        gerar_cartao_cnpj(
            _empresa(optante_simples=None, optante_mei=None, simples_desde="", mei_desde="")
        )
    )
    hoje = date.today().strftime("%d/%m/%Y")

    bloco = texto.split("NÃO CONSTAM DO COMPROVANTE OFICIAL", 1)[-1]
    bloco = bloco.split("Documento gerado pela Mercabiliza", 1)[0]
    assert hoje not in bloco, "data de hoje vazou para um campo sem informação"
    assert "NÃO INFORMADO" in bloco


def test_cartao_indica_onde_confirmar_quando_a_base_nao_informou():
    """"NÃO INFORMADO" sem saída é beco; com o endereço da consulta, é passo.

    Foi o caso real de um Empresário Individual aberto em fev/2026: os três
    provedores responderam e nenhum trouxe a marcação do Simples/SIMEI, que
    vem do dump mensal da Receita e demora em cadastro novo e em MEI.
    """
    texto = _texto(gerar_cartao_cnpj(_empresa(optante_simples=None, optante_mei=None)))

    assert "Opção não informada pelas bases consultadas" in texto
    assert "aplicacoes.aspx?id=21" in texto


def test_cartao_completo_nao_recebe_a_instrucao():
    """Quem já tem a resposta não precisa ler onde buscá-la."""
    texto = _texto(
        gerar_cartao_cnpj(_empresa(optante_simples=True, optante_mei=False))
    )

    assert "Opção não informada pelas bases consultadas" not in texto
    assert "aplicacoes.aspx" not in texto


def test_instrucao_aparece_se_faltar_so_o_mei():
    """Simples confirmado e MEI em aberto é o formato que um MEI assume
    quando a base está atrasada — justamente quando confirmar importa mais."""
    texto = _texto(gerar_cartao_cnpj(_empresa(optante_simples=True, optante_mei=None)))

    assert "aplicacoes.aspx?id=21" in texto


def test_qsa_nao_pendura_placeholder_de_faixa_etaria():
    """`Socio.faixa_etaria` tem default "N/A", não vazio.

    Um teste ingênuo (`if s.faixa_etaria`) considera isso preenchido e o
    documento sai com "— N/A" pendurado no nome do sócio: ruído com cara de
    dado, num papel que o cliente lê.
    """
    from src.core.models import Socio

    texto = _texto(
        gerar_cartao_cnpj(
            _empresa(socios=(Socio(nome="FULANA DE TAL", qualificacao="Sócia"),))
        )
    )

    assert "FULANA DE TAL — Sócia" in texto
    assert "N/A" not in texto


def test_qsa_mostra_a_faixa_etaria_quando_existe():
    from src.core.models import Socio

    texto = _texto(
        gerar_cartao_cnpj(
            _empresa(
                socios=(
                    Socio(nome="FULANA", qualificacao="Sócia", faixa_etaria="41 a 50 anos"),
                )
            )
        )
    )

    assert "41 a 50 anos" in texto
